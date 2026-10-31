"""A scripted model for tests and dry runs: replays a fixed list of bash commands."""

import time
from types import SimpleNamespace
from typing import Any

from pydantic import BaseModel

from zenagent.models.openai_model import DEFAULT_OBSERVATION_TEMPLATE
from zenagent.models.utils.actions_toolcall import format_toolcall_observation_messages, parse_toolcall_actions


class DeterministicModelConfig(BaseModel):
    outputs: list[str | list[str]]
    """Each entry is one LM turn: a command, a list of commands (parallel tool calls), or [] for no tool call."""
    model_name: str = "deterministic"
    cost_per_call: float = 1.0
    format_error_template: str = "{{ error }}"
    observation_template: str = DEFAULT_OBSERVATION_TEMPLATE


class DeterministicModel:
    def __init__(self, **kwargs):
        self.config = DeterministicModelConfig(**kwargs)
        self.current_index = -1

    def query(self, messages: list[dict], **kwargs) -> dict:
        self.current_index += 1
        output = self.config.outputs[self.current_index]
        commands = [output] if isinstance(output, str) else list(output)
        tool_calls = [
            SimpleNamespace(
                id=f"call_{self.current_index}_{i}",
                function=SimpleNamespace(name="bash", arguments=_json({"command": c})),
            )
            for i, c in enumerate(commands)
        ]
        cost = {"cost": self.config.cost_per_call}
        try:
            actions = parse_toolcall_actions(tool_calls, format_error_template=self.config.format_error_template)
        except Exception as e:
            if getattr(e, "messages", None):
                e.messages[0]["extra"].update(cost)
            raise
        return {
            "role": "assistant",
            "content": f"step {self.current_index}",
            "tool_calls": [
                {"id": t.id, "type": "function", "function": {"name": "bash", "arguments": t.function.arguments}}
                for t in tool_calls
            ],
            "extra": {"actions": actions, **cost, "timestamp": time.time()},
        }

    def format_message(self, **kwargs) -> dict:
        return dict(kwargs)

    def format_observation_messages(self, message: dict, outputs: list[dict], template_vars: dict | None = None):
        return format_toolcall_observation_messages(
            actions=message.get("extra", {}).get("actions", []),
            outputs=outputs,
            observation_template=self.config.observation_template,
            template_vars=template_vars,
        )

    def get_template_vars(self, **kwargs) -> dict[str, Any]:
        return self.config.model_dump()

    def serialize(self) -> dict:
        return {"info": {"config": {"model": self.config.model_dump(mode="json"), "model_type": "deterministic"}}}


def _json(obj) -> str:
    import json

    return json.dumps(obj)
