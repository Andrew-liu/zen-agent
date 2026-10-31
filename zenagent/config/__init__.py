"""Config files (YAML) and `key.path=value` specs, merged recursively."""

import json
import os
from pathlib import Path

import yaml

builtin_config_dir = Path(__file__).parent


def get_config_path(config_spec: str | Path) -> Path:
    config_spec = Path(config_spec)
    if config_spec.suffix != ".yaml":
        config_spec = config_spec.with_suffix(".yaml")
    candidates = [
        config_spec,
        Path(os.getenv("ZEN_CONFIG_DIR", ".")) / config_spec,
        builtin_config_dir / config_spec,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"Could not find config file for {config_spec} (tried: {[str(c) for c in candidates]})")


def key_value_spec_to_nested_dict(config_spec: str) -> dict:
    """'model.model_kwargs.temperature=0.5' -> {'model': {'model_kwargs': {'temperature': 0.5}}}"""
    key, value = config_spec.split("=", 1)
    try:
        value = json.loads(value)
    except json.JSONDecodeError:
        pass
    keys = key.split(".")
    if any(k == "" for k in keys):
        raise ValueError(f"Invalid config spec {config_spec!r}: empty config key")
    result: dict = {}
    current = result
    for k in keys[:-1]:
        current[k] = {}
        current = current[k]
    current[keys[-1]] = value
    return result


def get_config_from_spec(config_spec: str | Path) -> dict:
    if isinstance(config_spec, str) and "=" in config_spec:
        return key_value_spec_to_nested_dict(config_spec)
    return yaml.safe_load(get_config_path(config_spec).read_text(encoding="utf-8")) or {}


__all__ = ["builtin_config_dir", "get_config_path", "get_config_from_spec", "key_value_spec_to_nested_dict"]
