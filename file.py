#!/usr/bin/env python3

import inspect
import re
from pathlib import Path
from typing import Any, Callable

def resolve_abs_path(path_str: str) -> Path:
    path = Path(path_str).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    return path


def read_file_tool(filename: str) -> dict[str, Any]:
    """
    Gets the full content of a file provided by the user.
    :param filename: The name of the file to read.
    :return: The full content of the file.
    """
    full_path = resolve_abs_path(filename)
    print(full_path)
    with open(str(full_path), "r") as f:
        content = f.read()
    return {
        "file_path": str(full_path),
        "content": content
    }

def list_files_tool(path: str) -> dict[str, Any]:
    """
    Lists the files in a directory provided by the user.
    :param path: The path to a directory to list files from.
    :return: A list of files in the directory.
    """
    full_path = resolve_abs_path(path)
    all_files = []
    for item in full_path.iterdir():
        all_files.append({
            "filename": item.name,
            "type": "file" if item.is_file() else "dir"
        })
    return {
        "path": str(full_path),
        "files": all_files
    }

def edit_file_tool(path: str, old_str: str, new_str: str) -> dict[str, Any]:
    """
    Replaces first occurrence of old_str with new_str in file. If old_str is empty,
    create/overwrite file with new_str.
    :param path: The path to the file to edit.
    :param old_str: The string to replace.
    :param new_str: The string to replace with.
    :return: A dictionary with the path to the file and the action taken.
    """
    full_path = resolve_abs_path(path)
    if old_str == "":
        full_path.write_text(new_str, encoding="utf-8")
        return {
            "path": str(full_path),
            "action": "created_file"
        }
    original = full_path.read_text(encoding="utf-8")
    if original.find(old_str) == -1:
        return {
            "path": str(full_path),
            "action": "old_str not found"
        }
    edited = original.replace(old_str, new_str, 1)
    full_path.write_text(edited, encoding="utf-8")
    return {
        "path": str(full_path),
        "action": "edited"
    }

TOOL_REGISTRY: dict[str, Callable[..., dict[str, Any]]] = {
    "read_file": read_file_tool,
    "list_files": list_files_tool,
    "edit_file": edit_file_tool,
}

# Python 类型注解 -> JSON Schema 类型。
_PYTHON_TO_JSON_TYPE = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


def _parse_docstring(doc: str) -> tuple[str, dict[str, str]]:
    """从 docstring 解析出（整体描述, {参数名: 参数描述}）。

    整体描述取第一段非 `:param:` 文本；参数描述来自 `:param name: text` 行。
    """
    doc = inspect.cleandoc(doc or "")
    summary_lines: list[str] = []
    param_docs: dict[str, str] = {}

    param_pattern = re.compile(r":param\s+(\w+)\s*:\s*(.+)")
    for line in doc.splitlines():
        match = param_pattern.match(line.strip())
        if match:
            param_docs[match.group(1)] = match.group(2).strip()
        elif line.strip().startswith(":return"):
            continue
        elif not param_docs:
            # 只在遇到第一个 :param: 之前累积整体描述。
            summary_lines.append(line.strip())

    summary = " ".join(part for part in summary_lines if part).strip()
    return summary, param_docs


def build_tool_schema(name: str, func: Callable[..., Any]) -> dict[str, Any]:
    """根据函数签名、类型注解和 docstring 自动生成 OpenAI 工具 schema。"""
    summary, param_docs = _parse_docstring(func.__doc__ or "")
    signature = inspect.signature(func)

    properties: dict[str, Any] = {}
    required: list[str] = []
    for param_name, param in signature.parameters.items():
        json_type = _PYTHON_TO_JSON_TYPE.get(param.annotation, "string")
        properties[param_name] = {
            "type": json_type,
            "description": param_docs.get(param_name, param_name),
        }
        if param.default is inspect.Parameter.empty:
            required.append(param_name)

    return {
        "type": "function",
        "function": {
            "name": name,
            "description": summary,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


# 模型看到的是自动生成的 JSON Schema，而不是 Python 函数本身。
TOOL_SCHEMAS = [build_tool_schema(name, func) for name, func in TOOL_REGISTRY.items()]

if __name__ == "__main__":
    print(TOOL_SCHEMAS)
    # import json

    # print(json.dumps(TOOL_SCHEMAS, ensure_ascii=False, indent=2))
    # print(edit_file_tool("test.md", "123", "456"))