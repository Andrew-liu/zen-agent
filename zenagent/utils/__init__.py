import importlib


def import_class(spec: str, mapping: dict[str, str], kind: str) -> type:
    """Resolve a shortcut name (e.g. 'local') or a full import path to a class."""
    full_path = mapping.get(spec, spec)
    try:
        module_name, class_name = full_path.rsplit(".", 1)
        return getattr(importlib.import_module(module_name), class_name)
    except (ValueError, ImportError, AttributeError) as e:
        raise ValueError(f"Unknown {kind} class: {spec} (resolved to {full_path}, available: {list(mapping)})") from e
