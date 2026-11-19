"""Table identities and ordered preview preferences stored in project files."""

from typing import Any

SHEETS = {
    "analysis_audit.csv": "Analysis audit",
    "animal_metrics.csv": "Animal metrics",
    "condition_comparison.csv": "Condition comparison",
    "pooled_metrics.csv": "Pooled metrics",
}


def validate_analysis_sorts(value: object) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(value, dict) or not set(value).issubset(SHEETS):
        raise ValueError("Invalid animal analysis sorting tables.")
    result = {}
    for table, rules in value.items():
        if not isinstance(rules, list):
            raise ValueError("Invalid animal analysis sorting rules.")
        seen = set()
        for rule in rules:
            if (
                not isinstance(rule, dict)
                or set(rule) != {"column", "descending"}
                or not isinstance(rule["column"], str)
                or not rule["column"]
                or type(rule["descending"]) is not bool
                or rule["column"] in seen
            ):
                raise ValueError("Invalid animal analysis sorting rule.")
            seen.add(rule["column"])
        result[table] = [dict(rule) for rule in rules]
    return result
