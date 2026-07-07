from __future__ import annotations

import fnmatch

from core.yaml_store import SkipCondition, SkipRule


def _compare(actual, operator: str, expected) -> bool:
    match operator:
        case "equals":
            return str(actual).lower() == str(expected).lower()
        case "not_equals":
            return str(actual).lower() != str(expected).lower()
        case "less_than":
            try:
                return float(actual) < float(expected)
            except (ValueError, TypeError):
                return False
        case "greater_than":
            try:
                return float(actual) > float(expected)
            except (ValueError, TypeError):
                return False
        case "contains":
            return str(expected).lower() in str(actual).lower()
        case _:
            return False


def should_skip(media_info: dict, rules: list[SkipRule]) -> SkipRule | None:
    for rule in rules:
        if not rule.conditions:
            continue
        matched = True
        for cond in rule.conditions:
            value = media_info.get(cond.field)
            if value is None or not _compare(value, cond.operator, cond.value):
                matched = False
                break
        if matched:
            return rule
    return None


def format_rule(rule: SkipRule) -> str:
    parts = [f"{c.field} {c.operator} {c.value}" for c in rule.conditions]
    return " AND ".join(parts)


def match_path_pattern(rel_path: str, patterns: list[str]) -> str | None:
    lower = "/" + rel_path.lower()
    for pattern in patterns:
        if fnmatch.fnmatch(lower, pattern.lower()):
            return pattern
    return None
