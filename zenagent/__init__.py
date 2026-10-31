"""zen-agent: a minimal bash-only software engineering agent.

Architecture is aligned with mini-swe-agent (https://github.com/SWE-agent/mini-swe-agent):

- Agent: a linear message history + a loop of `query -> execute -> observe`.
- Model: talks to an LLM, returns an assistant message whose `extra.actions` holds bash commands.
- Environment: executes bash commands (each command in a fresh subshell).

This file provides path settings, version numbering and the protocols of the core components.
"""

__version__ = "0.1.0"

import logging
import os
from pathlib import Path
from typing import Any, Protocol

package_dir = Path(__file__).resolve().parent

global_config_dir = Path(os.getenv("ZEN_GLOBAL_CONFIG_DIR") or Path.home() / ".config" / "zen-agent")
global_config_file = global_config_dir / ".env"

logger = logging.getLogger("zenagent")


def load_env_file(path: Path) -> None:
    """Load KEY=VALUE lines from a dotenv-style file without overriding existing env vars."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export ") :].strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


load_env_file(global_config_file)


# === Protocols ===
# Duck typing is enough at runtime; these only help static type checking.


class Model(Protocol):
    config: Any

    def query(self, messages: list[dict], **kwargs) -> dict: ...

    def format_message(self, **kwargs) -> dict: ...

    def format_observation_messages(
        self, message: dict, outputs: list[dict], template_vars: dict | None = None
    ) -> list[dict]: ...

    def get_template_vars(self, **kwargs) -> dict[str, Any]: ...

    def serialize(self) -> dict: ...


class Environment(Protocol):
    config: Any

    def execute(self, action: dict, cwd: str = "") -> dict[str, Any]: ...

    def get_template_vars(self, **kwargs) -> dict[str, Any]: ...

    def serialize(self) -> dict: ...


class Agent(Protocol):
    config: Any

    def run(self, task: str, **kwargs) -> dict: ...

    def save(self, path: Path | None, *extra_dicts) -> dict: ...


__all__ = [
    "Agent",
    "Model",
    "Environment",
    "package_dir",
    "__version__",
    "global_config_file",
    "global_config_dir",
    "load_env_file",
    "logger",
]
