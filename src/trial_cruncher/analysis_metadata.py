"""Manual study annotations, independent of raw data and metric validity."""

import hashlib
import json
from dataclasses import asdict, dataclass
from functools import cached_property
from typing import Any

METADATA_VERSION = "2"
ANNOTATION_COLUMNS = (
    "analysis_condition",
    "analysis_included",
    "analysis_inclusion_status",
    "analysis_inclusion_reason",
    "analysis_metadata_version",
    "analysis_metadata_source",
    "analysis_metadata_sha256",
)


@dataclass(frozen=True)
class AnalysisMetadata:
    condition: str | None = None
    included: bool | None = None
    inclusion_reason: str | None = None
    version: str = METADATA_VERSION

    def __post_init__(self) -> None:
        if self.version != METADATA_VERSION:
            raise ValueError("Unsupported analysis metadata version.")
        for name in ("condition", "inclusion_reason"):
            value = getattr(self, name)
            if value is not None and (
                not isinstance(value, str) or not value.strip() or value != value.strip()
            ):
                raise ValueError(f"{name} must be normalized text or null.")
        if self.included is not None and type(self.included) is not bool:
            raise ValueError("Inclusion must be true, false, or null (not reviewed).")
        if self.included is False and self.inclusion_reason is None:
            raise ValueError("An exclusion reason is required.")

    @property
    def is_assigned(self) -> bool:
        return any(
            getattr(self, name) is not None
            for name in ("condition", "included", "inclusion_reason")
        )

    @property
    def inclusion_status(self) -> str:
        return (
            "Included"
            if self.included is True
            else "Excluded"
            if self.included is False
            else "Not reviewed"
        )

    @cached_property
    def sha256(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()

    def export_fields(self) -> dict[str, Any]:
        return dict(
            zip(
                ANNOTATION_COLUMNS,
                (
                    self.condition,
                    self.included,
                    self.inclusion_status,
                    self.inclusion_reason,
                    self.version,
                    "manual" if self.is_assigned else "unassigned",
                    self.sha256,
                ),
                strict=True,
            )
        )


def analysis_metadata_from_dict(value: Any) -> AnalysisMetadata:
    expected = {"condition", "included", "inclusion_reason", "version"}
    legacy = expected | {"cohort", "session_order"}
    if not isinstance(value, dict):
        raise ValueError("Invalid analysis metadata fields.")
    if set(value) == legacy and value["version"] == "1":
        cohort = value["cohort"]
        order = value["session_order"]
        if cohort is not None and (
            not isinstance(cohort, str) or not cohort.strip() or cohort != cohort.strip()
        ):
            raise ValueError("Invalid legacy cohort.")
        if order is not None and (type(order) is not int or not 1 <= order <= 2_147_483_647):
            raise ValueError("Invalid legacy session order.")
        return AnalysisMetadata(value["condition"], value["included"], value["inclusion_reason"])
    if set(value) != expected:
        raise ValueError("Invalid analysis metadata fields.")
    return AnalysisMetadata(**value)
