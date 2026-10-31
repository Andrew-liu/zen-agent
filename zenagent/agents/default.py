"""The default agent: a linear message history and a `query -> execute -> observe` loop.

Control flow (aligned with mini-swe-agent):

    run(task)
      ├─ messages = [system, user(task)]
      └─ loop:
           step() = execute_actions(query())
             ├─ FormatError       -> append error message, retry (up to N times in a row)
             ├─ InterruptAgentFlow -> append its messages (Submitted / LimitsExceeded / ...)
             └─ save trajectory
           stop when last message has role == "exit"
"""

import json
import logging
import time
import traceback
from pathlib import Path

from jinja2 import StrictUndefined, Template
from pydantic import BaseModel

from zenagent import Environment, Model, __version__
from zenagent.exceptions import FormatError, InterruptAgentFlow, LimitsExceeded, TimeExceeded
from zenagent.utils.serialize import recursive_merge


class AgentConfig(BaseModel):
    system_template: str
    """Template for the system message (the first message)."""
    instance_template: str
    """Template for the first user message specifying the task."""
    step_limit: int = 0
    """Maximum number of LM calls (0 = no limit)."""
    cost_limit: float = 3.0
    """Stop after exceeding this cost in USD (0 = no limit)."""
    wall_time_limit_seconds: int = 0
    """Stop after this many seconds of wall-clock time (0 = no limit)."""
    max_consecutive_format_errors: int = 3
    """Exit after this many format errors in a row (0 = no limit)."""
    output_path: Path | None = None
    """Save the trajectory to this path after every step."""


def _exit_message(status: str, submission: str = "", content: str | None = None) -> dict:
    return {
        "role": "exit",
        "content": status if content is None else content,
        "extra": {"exit_status": status, "submission": submission},
    }


class DefaultAgent:
    def __init__(self, model: Model, env: Environment, *, config_class: type = AgentConfig, **kwargs):
        self.config = config_class(**kwargs)
        self.messages: list[dict] = []
        self.model = model
        self.env = env
        self.extra_template_vars: dict = {}
        self.logger = logging.getLogger("agent")
        self.cost = 0.0
        self.n_calls = 0
        self.n_consecutive_format_errors = 0
        self._start_time = time.time()

    # --- templates -------------------------------------------------------

    def get_template_vars(self, **kwargs) -> dict:
        return recursive_merge(
            self.config.model_dump(),
            self.env.get_template_vars(),
            self.model.get_template_vars(),
            {
                "n_model_calls": self.n_calls,
                "model_cost": self.cost,
                "elapsed_seconds": int(time.time() - self._start_time),
            },
            self.extra_template_vars,
            kwargs,
        )

    def _render_template(self, template: str) -> str:
        return Template(template, undefined=StrictUndefined).render(**self.get_template_vars())

    # --- message history -------------------------------------------------

    def add_messages(self, *messages: dict) -> list[dict]:
        self.logger.debug(messages)
        self.messages.extend(messages)
        return list(messages)

    def handle_uncaught_exception(self, e: Exception) -> list[dict]:
        return self.add_messages(
            self.model.format_message(
                role="exit",
                content=str(e),
                extra={
                    "exit_status": type(e).__name__,
                    "submission": "",
                    "exception_str": str(e),
                    "traceback": traceback.format_exc(),
                },
            )
        )

    # --- main loop -------------------------------------------------------

    def run(self, task: str = "", **kwargs) -> dict:
        """Run step() until finished. Returns a dict with `exit_status` and `submission` keys."""
        self.extra_template_vars |= {"task": task, **kwargs}
        self.messages = []
        self._start_time = time.time()
        self.add_messages(
            self.model.format_message(role="system", content=self._render_template(self.config.system_template)),
            self.model.format_message(role="user", content=self._render_template(self.config.instance_template)),
        )
        while True:
            try:
                self.step()
                self.n_consecutive_format_errors = 0
            except FormatError as e:
                # The call was billed before parsing failed, so charge it here.
                self.cost += e.messages[0].get("extra", {}).get("cost", 0.0)
                self.n_consecutive_format_errors += 1
                limit = self.config.max_consecutive_format_errors
                if 0 < limit <= self.n_consecutive_format_errors:
                    self.add_messages(*e.messages, _exit_message("RepeatedFormatError"))
                else:
                    self.add_messages(*e.messages)
            except InterruptAgentFlow as e:
                self.add_messages(*e.messages)
            except Exception as e:
                self.handle_uncaught_exception(e)
                raise
            finally:
                self.save(self.config.output_path)
            if self.messages[-1].get("role") == "exit":
                break
        return self.messages[-1].get("extra", {})

    def step(self) -> list[dict]:
        """Query the LM, execute actions."""
        return self.execute_actions(self.query())

    def query(self) -> dict:
        """Check limits, query the model and append its message."""
        if 0 < self.config.step_limit <= self.n_calls or 0 < self.config.cost_limit <= self.cost:
            raise LimitsExceeded(_exit_message("LimitsExceeded"))
        if 0 < self.config.wall_time_limit_seconds <= int(time.time() - self._start_time):
            raise TimeExceeded(_exit_message("TimeExceeded"))
        self.n_calls += 1
        message = self.model.query(self.messages)
        self.cost += message.get("extra", {}).get("cost", 0.0)
        self.add_messages(message)
        return message

    def execute_actions(self, message: dict) -> list[dict]:
        """Execute actions in message, append observation messages, return them."""
        outputs = [self.env.execute(action) for action in message.get("extra", {}).get("actions", [])]
        return self.add_messages(*self.model.format_observation_messages(message, outputs, self.get_template_vars()))

    # --- persistence -----------------------------------------------------

    def serialize(self, *extra_dicts) -> dict:
        last_extra = (self.messages[-1] if self.messages else {}).get("extra", {})
        agent_data = {
            "info": {
                "model_stats": {"instance_cost": self.cost, "api_calls": self.n_calls},
                "config": {
                    "agent": self.config.model_dump(mode="json"),
                    "agent_type": f"{self.__class__.__module__}.{self.__class__.__name__}",
                },
                "zen_version": __version__,
                "exit_status": last_extra.get("exit_status", ""),
                "submission": last_extra.get("submission", ""),
            },
            "messages": self.messages,
            "trajectory_format": "zen-agent-1.0",
        }
        return recursive_merge(agent_data, self.model.serialize(), self.env.serialize(), *extra_dicts)

    def save(self, path: Path | None, *extra_dicts) -> dict:
        """Save the trajectory to `path` (if given). Returns the serialized data."""
        data = self.serialize(*extra_dicts)
        if path:
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        return data
