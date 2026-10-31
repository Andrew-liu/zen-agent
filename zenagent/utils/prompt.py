"""Terminal input helpers (stdlib only; readline gives history & line editing when available)."""

import sys

try:
    import readline  # noqa: F401
except ImportError:  # pragma: no cover - Windows
    pass


def single_line_prompt() -> str:
    return input("")


def multiline_prompt() -> str:
    """Read lines until EOF (Ctrl+D on macOS/Linux, Ctrl+Z+Enter on Windows)."""
    eof_hint = "Ctrl+Z then Enter" if sys.platform == "win32" else "Ctrl+D"
    print(f"(multiline input, finish with {eof_hint} on an empty line)")
    lines: list[str] = []
    while True:
        try:
            lines.append(input(""))
        except EOFError:
            break
    return "\n".join(lines)
