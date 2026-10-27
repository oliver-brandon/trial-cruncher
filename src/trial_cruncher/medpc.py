"""Read one Med-PC text session without interpreting behavioral variables."""

import hashlib
import logging
import re
from decimal import Decimal, DecimalException
from pathlib import Path
from typing import NoReturn, TypedDict

logger = logging.getLogger(__name__)
READER_VERSION = "1"
_NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?\Z")
_VARIABLE = re.compile(r"([A-Z]):\s*(.*)")
_ROW = re.compile(r"(\d+):\s*(.*)")


class MedPCReadError(ValueError):
    """An unsupported or malformed export; the message identifies its source."""


class MedPCData(TypedDict):
    format: str
    reader_version: str
    source_file: Path
    source_sha256: str
    source_text: str
    headers: dict[str, str]
    scalars: dict[str, Decimal]
    arrays: dict[str, dict[int, Decimal]]
    line_numbers: dict[str, int]
    warnings: tuple[str, ...]


def _has_session_headers(text: str) -> bool:
    return all(re.search(rf"(?m)^[ \t]*{name}:[ \t]*[^\s\r\n]", text) for name in ("File", "MSN"))


class MedPCReader:
    """UTF-8/ASCII, single-session exports with scalar and indexed numeric arrays.

    Unknown headers/variables are retained. Ambiguous structure is rejected rather
    than overwritten. Missing indices are preserved and reported, never zero-filled.
    """

    def can_read(self, path: Path) -> bool:
        """Recognize session headers, not filename extensions; not a validation pass."""
        if path.name.startswith("._"):
            return False
        try:
            with path.open("rb") as stream:
                prefix = stream.read(65536)
            # A replacement only in this bounded probe avoids cutting a UTF-8 character.
            text = prefix.decode("utf-8-sig", errors="replace")
            return "\x00" not in text and _has_session_headers(text)
        except OSError:
            return False

    def read(self, path: Path) -> MedPCData:
        source = path.expanduser().resolve()

        def fail(message: str, line: int | None = None) -> NoReturn:
            location = f"{source}:{line}" if line is not None else str(source)
            raise MedPCReadError(f"{location}: {message}")

        if path.name.startswith("._"):
            fail("AppleDouble metadata is not a behavioral session export.")
        try:
            content = source.read_bytes()
        except OSError as exc:
            raise MedPCReadError(f"{source}: could not read file: {exc}") from exc
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise MedPCReadError(f"{source}: expected a UTF-8/ASCII Med-PC text export.") from exc
        if "\x00" in text or not _has_session_headers(text):
            fail("Expected a Med-PC session export with nonempty File and MSN headers.")

        headers: dict[str, str] = {}
        scalars: dict[str, Decimal] = {}
        arrays: dict[str, dict[int, Decimal]] = {}
        locations: dict[str, int] = {}
        warnings: list[str] = []
        active: str | None = None

        def number(token: str, line: int) -> Decimal:
            if not _NUMBER.fullmatch(token):
                fail(f"Invalid numeric value {token!r}.", line)
            try:
                value = Decimal(token)
            except DecimalException:
                fail(f"Invalid numeric value {token!r}.", line)
            if not value.is_finite():
                fail("Numeric values must be finite.", line)
            return value

        for line_number, original in enumerate(text.splitlines(), 1):
            line = original.strip()
            if not line:
                continue
            if match := _VARIABLE.fullmatch(line):
                name, value = match.groups()
                if name in scalars or name in arrays:
                    fail(
                        f"Duplicate variable {name}; multiple sessions are not supported.",
                        line_number,
                    )
                locations[name] = line_number
                active = None
                if value:
                    scalars[name] = number(value, line_number)
                else:
                    arrays[name] = {}
                    active = name
            elif match := _ROW.fullmatch(line):
                if active is None:
                    fail("Indexed row has no array heading.", line_number)
                index, tokens = int(match[1]), match[2].split()
                if not tokens:
                    fail("Indexed row contains no values.", line_number)
                for offset, token in enumerate(tokens, index):
                    if offset in arrays[active]:
                        fail(f"Duplicate index {active}[{offset}].", line_number)
                    arrays[active][offset] = number(token, line_number)
                    locations[f"{active}[{offset}]"] = line_number
            elif ":" in line:
                name, value = line.split(":", 1)
                name, value = name.strip(), value.strip()
                if not name or not name[0].isalpha():
                    fail("Unrecognized header or indexed row.", line_number)
                if name in headers:
                    fail(
                        f"Duplicate header {name!r}; multiple sessions are not supported.",
                        line_number,
                    )
                headers[name] = value
                locations[name] = line_number
                active = None
            else:
                fail("Unrecognized line; no source data was discarded.", line_number)

        for name, values in arrays.items():
            if any(index != expected for expected, index in enumerate(sorted(values))):
                warnings.append(
                    f"{name}: indices are not contiguous from zero; no values filled in."
                )
            if list(values) != sorted(values):
                warnings.append(f"{name}: array rows are out of index order; indices retained.")
        for warning in warnings:
            logger.warning(warning, extra={"path": source, "operation": "read_medpc"})
        return MedPCData(
            format="medpc-text",
            reader_version=READER_VERSION,
            source_file=source,
            source_sha256=hashlib.sha256(content).hexdigest(),
            source_text=text,
            headers=headers,
            scalars=scalars,
            arrays=arrays,
            line_numbers=locations,
            warnings=tuple(warnings),
        )
