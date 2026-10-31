"""Any OpenAI-compatible chat completions API (OpenAI, DeepSeek, Qwen, vLLM, Ollama, OpenRouter, ...)."""

import logging
import os
import time
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from zenagent.exceptions import FormatError
from zenagent.models.utils.actions_toolcall import (
    BASH_TOOL,
    format_toolcall_observation_messages,
    parse_toolcall_actions,
)

logger = logging.getLogger("zenagent.openai_model")

DEFAULT_OBSERVATION_TEMPLATE = (
    "{% if output.exception_info %}<exception>{{output.exception_info}}</exception>\n{% endif %}"
    "<returncode>{{output.returncode}}</returncode>\n<output>\n{{output.output}}</output>"
)


class OpenAIModelConfig(BaseModel):
    model_name: str
    base_url: str | None = None
    """API base url. Falls back to $OPENAI_BASE_URL, then https://api.deepseek.com."""
    api_key_env: list[str] = ["ZEN_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY"]
    """Environment variables checked (in order) for the API key."""
    model_kwargs: dict[str, Any] = {}
    """Extra arguments passed to `chat.completions.create` (temperature, max_tokens, ...)."""
    input_cost_per_mtok: float = 0.0
    """USD per 1M prompt tokens, used for cost tracking & cost_limit."""
    output_cost_per_mtok: float = 0.0
    """USD per 1M completion tokens."""
    max_retries: int = 5
    request_timeout: float = 600.0
    format_error_template: str = "{{ error }}"
    observation_template: str = DEFAULT_OBSERVATION_TEMPLATE


class OpenAIModel:
    def __init__(self, *, config_class: Callable = OpenAIModelConfig, **kwargs):
        import openai

        self.config = config_class(**kwargs)
        self._openai = openai
        api_key = next((os.environ[k] for k in self.config.api_key_env if os.getenv(k)), None)
        if not api_key:
            raise RuntimeError(
                f"No API key found. Set one of {self.config.api_key_env} as environment variable "
                f"or in {os.getenv('ZEN_GLOBAL_CONFIG_DIR') or '~/.config/zen-agent'}/.env"
            )
        self.client = openai.OpenAI(
            api_key=api_key,
            base_url=self.config.base_url or os.getenv("OPENAI_BASE_URL") or "https://api.deepseek.com",
            timeout=self.config.request_timeout,
            max_retries=0,  # we retry ourselves
        )
        self.abort_exceptions: tuple[type[BaseException], ...] = (
            openai.AuthenticationError,
            openai.PermissionDeniedError,
            openai.NotFoundError,
            openai.BadRequestError,
            KeyboardInterrupt,
        )

    # --- API -------------------------------------------------------------

    def _query(self, messages: list[dict], **kwargs):
        return self.client.chat.completions.create(
            model=self.config.model_name,
            messages=messages,
            tools=[BASH_TOOL],
            **(self.config.model_kwargs | kwargs),
        )

    def _query_with_retry(self, messages: list[dict], **kwargs):
        for attempt in range(self.config.max_retries + 1):
            try:
                return self._query(messages, **kwargs)
            except self.abort_exceptions:
                raise
            except Exception as e:
                if attempt >= self.config.max_retries:
                    raise
                wait = min(2**attempt, 30)
                logger.warning("LM query failed (%s: %s), retrying in %ss", type(e).__name__, e, wait)
                time.sleep(wait)
        raise AssertionError("unreachable")

    @staticmethod
    def _prepare_messages_for_api(messages: list[dict]) -> list[dict]:
        """Strip our bookkeeping `extra` field before sending."""
        return [{k: v for k, v in msg.items() if k != "extra"} for msg in messages]

    def query(self, messages: list[dict], **kwargs) -> dict:
        response = self._query_with_retry(self._prepare_messages_for_api(messages), **kwargs)
        cost_output = self._calculate_cost(response)
        # The response and its cost must be persisted even if parsing fails.
        try:
            actions = self._parse_actions(response)
        except FormatError as e:
            e.messages[0]["extra"].update(cost_output)
            e.messages[0]["extra"]["response"] = _dump(response)
            raise
        message = response.choices[0].message.model_dump(exclude_none=True)
        message.setdefault("content", "")
        message["extra"] = {
            "actions": actions,
            "response": _dump(response),
            **cost_output,
            "timestamp": time.time(),
        }
        return message

    def _calculate_cost(self, response) -> dict[str, float]:
        usage = getattr(response, "usage", None)
        prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
        completion_tokens = getattr(usage, "completion_tokens", 0) or 0
        cost = (
            prompt_tokens * self.config.input_cost_per_mtok + completion_tokens * self.config.output_cost_per_mtok
        ) / 1_000_000
        return {"cost": cost, "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens}

    def _parse_actions(self, response) -> list[dict]:
        return parse_toolcall_actions(
            response.choices[0].message.tool_calls or [],
            format_error_template=self.config.format_error_template,
            template_kwargs={"finish_reason": response.choices[0].finish_reason},
        )

    # --- protocol helpers -----------------------------------------------

    def format_message(self, **kwargs) -> dict:
        return dict(kwargs)

    def format_observation_messages(
        self, message: dict, outputs: list[dict], template_vars: dict | None = None
    ) -> list[dict]:
        return format_toolcall_observation_messages(
            actions=message.get("extra", {}).get("actions", []),
            outputs=outputs,
            observation_template=self.config.observation_template,
            template_vars=template_vars,
        )

    def get_template_vars(self, **kwargs) -> dict[str, Any]:
        return self.config.model_dump()

    def serialize(self) -> dict:
        return {
            "info": {
                "config": {
                    "model": self.config.model_dump(mode="json"),
                    "model_type": f"{self.__class__.__module__}.{self.__class__.__name__}",
                }
            }
        }


def _dump(response) -> Any:
    try:
        return response.model_dump(mode="json")
    except Exception:
        return repr(response)
