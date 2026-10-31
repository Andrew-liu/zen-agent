"""Parse bash tool calls into actions & format execution outputs into tool messages."""

import json
import time

from jinja2 import StrictUndefined, Template

from zenagent.exceptions import FormatError

BASH_TOOL = {
    "type": "function",
    "function": {
        "name": "bash",
        "description": "Execute a bash command",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The bash command to execute"},
            },
            "required": ["command"],
        },
    },
}


def _format_error(template: str, **kwargs) -> FormatError:
    return FormatError(
        {
            "role": "user",
            "content": Template(template, undefined=StrictUndefined).render(**kwargs),
            "extra": {"interrupt_type": "FormatError"},
        }
    )


def parse_toolcall_actions(tool_calls: list, *, format_error_template: str, template_kwargs: dict | None = None) -> list[dict]:
    """Turn tool calls into `[{"command": ..., "tool_call_id": ...}]`. Raises FormatError on invalid calls."""
    template_kwargs = template_kwargs or {}
    if not tool_calls:
        raise _format_error(
            format_error_template,
            error="No tool calls found in the response. Every response MUST include at least one tool call.",
            actions=[],
            has_tool_calls=False,
            **template_kwargs,
        )
    actions = []
    for tool_call in tool_calls:
        error_msg = ""
        args = {}
        try:
            args = json.loads(tool_call.function.arguments or "{}")
        except Exception as e:
            error_msg = f"Error parsing tool call arguments: {e}. "
        if tool_call.function.name != "bash":
            error_msg += f"Unknown tool '{tool_call.function.name}'. "
        if not isinstance(args, dict) or "command" not in args:
            error_msg += "Missing 'command' argument in bash tool call."
        if error_msg:
            raise _format_error(
                format_error_template, actions=[], error=error_msg.strip(), has_tool_calls=True, **template_kwargs
            )
        actions.append({"command": args["command"], "tool_call_id": tool_call.id})
    return actions


def format_toolcall_observation_messages(
    *, actions: list[dict], outputs: list[dict], observation_template: str, template_vars: dict | None = None
) -> list[dict]:
    """One message per action. Missing outputs (e.g. rejected/interrupted) are padded as 'not executed'."""
    not_executed = {"output": "", "returncode": -1, "exception_info": "action was not executed"}
    padded = outputs + [not_executed] * (len(actions) - len(outputs))
    results = []
    for action, output in zip(actions, padded):
        content = Template(observation_template, undefined=StrictUndefined).render(
            output=output, **(template_vars or {})
        )
        msg = {
            "content": content,
            "extra": {
                "raw_output": output.get("output", ""),
                "returncode": output.get("returncode"),
                "timestamp": time.time(),
                "exception_info": output.get("exception_info"),
                **output.get("extra", {}),
            },
        }
        if "tool_call_id" in action:
            msg["role"] = "tool"
            msg["tool_call_id"] = action["tool_call_id"]
        else:
            msg["role"] = "user"  # commands issued by a human
        results.append(msg)
    return results
