"""Persisted scope and rules for one animal analysis."""

import hashlib
import json
from dataclasses import asdict, dataclass
from functools import cached_property

VERSION = "2"


@dataclass(frozen=True)
class AnalysisPlan:
    design: str
    conditions: tuple[str, ...]
    phases: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.design not in ("within-subjects", "between-subjects"):
            raise ValueError("Choose a within-subjects or between-subjects design.")
        for values in (self.conditions, self.phases):
            if (
                not isinstance(values, tuple)
                or not values
                or not all(isinstance(x, str) and x and x.strip() == x for x in values)
                or len(set(values)) != len(values)
            ):
                raise ValueError("Select distinct, nonempty condition and phase labels.")

    def record(self) -> dict:
        return {
            **asdict(self),
            "definition_version": VERSION,
            "identity": "global exact Subject",
            "selection": "one Included recording per animal/condition/phase",
            "pool": "ratio of eligible sums across animals within condition and phase",
        }

    @cached_property
    def sha256(self) -> str:
        return hashlib.sha256(
            json.dumps(self.record(), ensure_ascii=False, allow_nan=False).encode()
        ).hexdigest()

    @classmethod
    def restore(cls, obj: object) -> "AnalysisPlan":
        if isinstance(obj, dict) and obj.get("definition_version") == "1":
            old = dict(obj)
            if (
                not isinstance(old.get("cohort"), str)
                or not old["cohort"].strip()
                or old["cohort"] != old["cohort"].strip()
            ):
                raise ValueError("Invalid legacy cohort.")
            old.pop("cohort")
            old["definition_version"] = VERSION
            obj = old
        if not isinstance(obj, dict) or set(obj) != {
            "definition_version",
            "design",
            "conditions",
            "phases",
            "identity",
            "selection",
            "pool",
        }:
            raise ValueError("Invalid analysis plan fields.")
        if not all(isinstance(obj[k], list) for k in ("conditions", "phases")):
            raise ValueError("Invalid analysis plan selections.")
        plan = cls(obj["design"], tuple(obj["conditions"]), tuple(obj["phases"]))
        if plan.record() != {**obj, "conditions": plan.conditions, "phases": plan.phases}:
            raise ValueError("Unsupported aggregation plan rules.")
        return plan
