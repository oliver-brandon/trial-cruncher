"""Normalize the user-confirmed PRL Med-PC programs; no behavioral metrics."""

import logging
import math
from collections import Counter
from collections.abc import Mapping
from decimal import Decimal, DecimalException, localcontext
from pathlib import Path
from typing import Any

from trial_cruncher.models import Event, Session

logger = logging.getLogger(__name__)
NORMALIZER_VERSION = "2"
CHOICE_STORAGE_POLICY = "validated-zero-tail-v1"
SUPPORTED_PROGRAMS = frozenset({"PRL_BO", "PRL_OPTO", "PRL_OPTO_CORSTIM"})
_OUTCOMES = {1: (True, True), 2: (True, False), 6: (False, True), 7: (False, False)}
# Exact terminator in the supplied programs. Other negative values are not guessed.
_TERMINATOR = Decimal("-987.987")


def _decode_choice(value: Decimal) -> tuple[Decimal, int] | None:
    """Use exact decimal arithmetic so binary rounding cannot change event codes."""
    if value < 0 or not math.isfinite(float(value)):
        return None
    try:
        with localcontext() as context:
            context.prec = max(28, len(value.as_tuple().digits) + 2)
            hundredths = value * 100
            if hundredths != hundredths.to_integral_value():
                return None
            code = int(hundredths % 10)
            if code not in _OUTCOMES:
                return None
            return value - Decimal(code) / 100, code
    except DecimalException:
        return None


def choice_storage_info(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Recognize only fully corroborated unused zero tails; never change raw values."""
    arrays = raw.get("arrays", {})
    choices = arrays.get("C")
    unused: tuple[int, ...] = ()
    if choices and raw.get("headers", {}).get("MSN") in SUPPORTED_PROGRAMS:
        total = arrays.get("A", {}).get(2)
        indices = sorted(choices)
        if (
            isinstance(total, Decimal)
            and total.is_finite()
            and total == total.to_integral_value()
            and 0 <= total < len(choices)
            and all(index == expected for expected, index in enumerate(indices))
        ):
            boundary = int(total)
            prefix = [_decode_choice(choices[i]) for i in range(boundary)]
            if all(item is not None for item in prefix) and all(
                choices[i] == 0 for i in range(boundary, len(choices))
            ):
                counts = Counter(item[1] for item in prefix if item is not None)
                expected = {
                    "A": {0: counts[1] + counts[2], 1: counts[6] + counts[7], 2: boundary},
                    "B": {i: counts[code] for i, code in enumerate((1, 2, 6, 7))},
                }
                if all(
                    arrays.get(name, {}).get(i) == value
                    for name, values in expected.items()
                    for i, value in values.items()
                ):
                    unused = tuple(range(boundary, len(choices)))
    return {
        "policy": CHOICE_STORAGE_POLICY,
        "raw_c_entry_count": len(choices) if choices is not None else None,
        "unused_slot_count": len(unused) if choices is not None else None,
        "unused_slot_indices": unused,
    }


class PRLNormalizer:
    def normalize(self, raw: Mapping[str, Any], source_file: Path) -> tuple[Session, ...]:
        """Decode C into choice events, preserving every raw field and source index.

        Input is a mapping returned by MedPCReader. Unknown programs are rejected.
        Invalid C observations remain events with unavailable decoded values and a
        warning; their presence prevents misleading count comparisons.
        """
        source = source_file.expanduser().resolve()
        if raw.get("format") != "medpc-text":
            raise ValueError("PRL normalization requires MedPCReader output.")
        if source != raw["source_file"]:
            raise ValueError("Source path does not match the Med-PC reader's provenance.")
        headers, scalars, arrays = raw["headers"], raw["scalars"], raw["arrays"]
        program = headers.get("MSN")
        if program not in SUPPORTED_PROGRAMS:
            raise ValueError(
                f"Unsupported PRL program {program!r}; raw extraction remains available."
            )
        warnings = list(raw["warnings"])

        def warn(message: str) -> None:
            warnings.append(message)
            logger.warning(message, extra={"path": source, "operation": "normalize_prl"})

        duration = scalars.get("S")
        if duration is None or duration < 0 or not math.isfinite(float(duration)):
            warn("S: task duration is missing or invalid; header elapsed time was not substituted.")
            duration = None
        subject = headers.get("Subject") or None
        if subject is None:
            warn("Subject: identifier is missing; none was generated.")

        storage = choice_storage_info(raw)
        unused_indices = set(storage["unused_slot_indices"])
        choices = arrays.get("C")
        comparable = choices is not None
        if choices is None:
            warn("C: choice array is missing; no choice count or outcomes can be inferred.")
            choices = {}
        if any(index != expected for expected, index in enumerate(sorted(choices))):
            comparable = False
        events: list[Event] = []
        counts: Counter[int] = Counter()
        previous_time: Decimal | None = None
        terminated = False
        for index, value in sorted(choices.items()):
            if index in unused_indices:
                continue
            if terminated:
                warn(f"C[{index}]: value after the terminator retained raw and not interpreted.")
                comparable = False
                continue
            if value == _TERMINATOR:
                terminated = True
                continue
            timestamp: Decimal | None = None
            code: int | None = None
            correct: bool | None = None
            rewarded: bool | None = None
            decoded = _decode_choice(value)
            if decoded is None:
                warn(
                    f"C[{index}]: invalid or unknown encoded choice {value}; "
                    "decoded fields unavailable."
                )
                comparable = False
            else:
                timestamp, code = decoded
                correct, rewarded = _OUTCOMES[code]
                counts[code] += 1
                if previous_time is not None and timestamp < previous_time:
                    warn(f"C[{index}]: timestamp precedes the previous choice; order retained.")
                if duration is not None and timestamp > duration:
                    warn(f"C[{index}]: timestamp exceeds task duration S.")
                previous_time = timestamp
            events.append(
                Event(
                    name="choice",
                    timestamp_s=float(timestamp) if timestamp is not None else None,
                    raw_values={
                        "array": "C",
                        "index": index,
                        "value": value,
                        "line_number": raw["line_numbers"][f"C[{index}]"],
                    },
                    attributes={"outcome_code": code, "correct": correct, "rewarded": rewarded},
                )
            )

        expected = {
            "A": {0: counts[1] + counts[2], 1: counts[6] + counts[7], 2: len(events)},
            "B": {index: counts[code] for index, code in enumerate((1, 2, 6, 7))},
        }
        checks: dict[str, bool | None] = {}
        if not comparable:
            warn("C: incomplete or invalid choices; summary count comparisons are unavailable.")
        for name, values in expected.items():
            for index, expected_count in values.items():
                label = f"{name}[{index}]"
                actual = arrays.get(name, {}).get(index)
                checks[label] = None
                if actual is None:
                    warn(f"{label}: saved count is missing; comparison unavailable.")
                elif actual < 0 or actual != actual.to_integral_value():
                    warn(
                        f"{label}: saved count must be a nonnegative integer; "
                        "comparison unavailable."
                    )
                elif comparable:
                    checks[label] = actual == expected_count
                    if not checks[label]:
                        warn(
                            f"{label}: saved count {actual} differs from "
                            f"decoded C count {expected_count}."
                        )

        return (
            Session(
                source_file=source,
                subject_id=subject,
                events=tuple(events),
                duration_s=float(duration) if duration is not None else None,
                metadata={
                    "program": program,
                    "normalizer_version": NORMALIZER_VERSION,
                    "time_origin": "task_start",
                    "time_unit": "seconds",
                    "head_entries_recorded": False,
                    "latency_available": False,
                    "raw_only_fields": ("A[4]", "F", "J"),
                    "summary_checks": checks,
                    "choice_storage": storage,
                    "raw_medpc": raw,
                },
                warnings=tuple(warnings),
            ),
        )
