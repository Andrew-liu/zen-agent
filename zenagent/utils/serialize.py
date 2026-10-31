from typing import Any

UNSET = object()
"""Sentinel for 'not provided on the command line'; skipped by recursive_merge."""


def recursive_merge(*dictionaries: dict | None) -> dict:
    """Merge dictionaries recursively. Later ones take precedence; UNSET values are skipped."""
    result: dict[str, Any] = {}
    for d in dictionaries:
        if d is None:
            continue
        for key, value in d.items():
            if value is UNSET:
                continue
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = recursive_merge(result[key], value)
            elif isinstance(value, dict):
                result[key] = recursive_merge(value)
            else:
                result[key] = value
    return result
