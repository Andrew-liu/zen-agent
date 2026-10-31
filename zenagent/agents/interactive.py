"""DefaultAgent with the user in the loop.

Modes:
- human:   commands typed by the user are executed directly
- confirm: LM commands not matching `whitelist_actions` need user confirmation
- yolo:    LM commands are executed without confirmation

Slash commands: /y yolo, /c confirm, /u human, /m multiline input, /h help.
Ctrl+C while the agent works lets you inject a comment.
"""

import re
import sys
from typing import Literal, NoReturn

from rich.console import Console
from rich.rule import Rule

from zenagent.agents.default import AgentConfig, DefaultAgent
from zenagent.exceptions import LimitsExceeded, Submitted, TimeExceeded, UserInterruption
from zenagent.utils.prompt import multiline_prompt, single_line_prompt

console = Console(highlight=False)


class InteractiveAgentConfig(AgentConfig):
    mode: Literal["human", "confirm", "yolo"] = "confirm"
    whitelist_actions: list[str] = []
    """Never confirm actions matching these regular expressions."""
    confirm_exit: bool = True
    """Ask the user before finishing (they can add a follow-up task)."""


def get_content_string(message: dict) -> str:
    """Human readable content of a message, including the bash commands it carries."""
    content = message.get("content") or ""
    if isinstance(content, list):
        content = "\n".join(part.get("text", "") for part in content if isinstance(part, dict))
    if message.get("role") == "assistant":
        for action in message.get("extra", {}).get("actions", []):
            content += f"\n```bash\n{action['command']}\n```"
    return content.strip()


class InteractiveAgent(DefaultAgent):
    _MODE_COMMANDS_MAPPING = {"/u": "human", "/c": "confirm", "/y": "yolo"}

    def __init__(self, *args, config_class=InteractiveAgentConfig, **kwargs):
        super().__init__(*args, config_class=config_class, **kwargs)

    def _interrupt(self, content: str, *, itype: str = "UserInterruption") -> NoReturn:
        raise UserInterruption({"role": "user", "content": content, "extra": {"interrupt_type": itype}})

    def add_messages(self, *messages: dict) -> list[dict]:
        for msg in messages:
            role = msg.get("role", "unknown")
            if role == "assistant":
                console.print(
                    f"\n[red][bold]zen-agent[/bold] (step [bold]{self.n_calls}[/bold], "
                    f"[bold]${self.cost:.4f}[/bold]):[/red]"
                )
            else:
                console.print(f"\n[bold green]{role.capitalize()}[/bold green]:")
            console.print(get_content_string(msg), markup=False)
        return super().add_messages(*messages)

    def query(self) -> dict:
        if self.config.mode == "human":
            command = self._prompt_and_handle_slash_commands("[bold yellow]>[/bold yellow] ")
            if command not in ("/y", "/c"):
                msg = {
                    "role": "user",
                    "content": f"User command: \n```bash\n{command}\n```",
                    "extra": {"actions": [{"command": command}]},
                }
                self.add_messages(msg)
                return msg
        try:
            with console.status("Waiting for the LM to respond..."):
                return super().query()
        except TimeExceeded:
            raise
        except LimitsExceeded:
            if not self._stdin_is_interactive():
                raise
            console.print(
                f"Limits exceeded. Limits: {self.config.step_limit} steps, ${self.config.cost_limit}.\n"
                f"Current spend: {self.n_calls} steps, ${self.cost:.4f}."
            )
            self.config.step_limit = int(input("New step limit: "))
            self.config.cost_limit = float(input("New cost limit: "))
            return super().query()

    @staticmethod
    def _stdin_is_interactive() -> bool:
        try:
            return sys.stdin is not None and sys.stdin.isatty()
        except (ValueError, OSError):
            return False

    def step(self) -> list[dict]:
        try:
            console.print(Rule())
            return super().step()
        except KeyboardInterrupt:
            message = self._prompt_and_handle_slash_commands(
                "\n\n[bold yellow]Interrupted.[/bold yellow] "
                "[green]Type a comment/command[/green] (/h for available commands)\n[bold yellow]>[/bold yellow] "
            ).strip()
            if not message or message in self._MODE_COMMANDS_MAPPING:
                message = "Temporary interruption caught."
            self._interrupt(f"Interrupted by user: {message}")

    def execute_actions(self, message: dict) -> list[dict]:
        actions = message.get("extra", {}).get("actions", [])
        outputs: list[dict] = []
        try:
            self._ask_confirmation_or_interrupt([a["command"] for a in actions])
            for action in actions:
                outputs.append(self.env.execute(action))
        except Submitted as e:
            self._check_for_new_task_or_submit(e)
        finally:
            # Always record partial outputs so every tool_call gets a tool message.
            result = self.add_messages(
                *self.model.format_observation_messages(message, outputs, self.get_template_vars())
            )
        return result

    def _check_for_new_task_or_submit(self, e: Submitted) -> NoReturn:
        if self.config.confirm_exit:
            user_input = self._prompt_and_handle_slash_commands(
                "[bold yellow]Agent wants to finish.[/bold yellow] [bold green]Type new task[/bold green] "
                "or [bold]Enter[/bold] to quit ([bold]/h[/bold] for commands)\n[bold yellow]>[/bold yellow] "
            ).strip()
            if user_input == "/u":
                self._interrupt("Switched to human mode.")
            elif user_input in self._MODE_COMMANDS_MAPPING:
                return self._check_for_new_task_or_submit(e)
            elif user_input:
                self._interrupt(f"The user added a new task: {user_input}", itype="UserNewTask")
        raise e

    def _should_ask_confirmation(self, action: str) -> bool:
        return self.config.mode == "confirm" and not any(re.match(r, action) for r in self.config.whitelist_actions)

    def _ask_confirmation_or_interrupt(self, commands: list[str]) -> None:
        if not any(self._should_ask_confirmation(c) for c in commands):
            return
        user_input = self._prompt_and_handle_slash_commands(
            f"[bold yellow]Execute {len(commands)} action(s)?[/] [green][bold]Enter[/] to confirm[/], "
            "[red]type [bold]comment[/] to reject[/], or [blue][bold]/h[/] to show available commands[/]\n"
            "[bold yellow]>[/bold yellow] "
        ).strip()
        if user_input in ("", "/y"):
            return
        if user_input == "/u":
            self._interrupt("Commands not executed. Switching to human mode", itype="UserRejection")
        self._interrupt(
            f"Commands not executed. The user rejected your commands with the following message: {user_input}",
            itype="UserRejection",
        )

    def _prompt_and_handle_slash_commands(self, prompt: str, *, _multiline: bool = False) -> str:
        console.print(prompt, end="")
        if _multiline:
            return multiline_prompt()
        user_input = single_line_prompt()
        if user_input == "/m":
            return self._prompt_and_handle_slash_commands(prompt, _multiline=True)
        if user_input == "/h":
            console.print(
                f"Current mode: [bold green]{self.config.mode}[/bold green]\n"
                "[bold green]/y[/bold green] switch to [bold yellow]yolo[/bold yellow] mode "
                "(execute LM commands without confirmation)\n"
                "[bold green]/c[/bold green] switch to [bold yellow]confirm[/bold yellow] mode "
                "(ask before executing LM commands)\n"
                "[bold green]/u[/bold green] switch to [bold yellow]human[/bold yellow] mode "
                "(execute commands issued by you)\n"
                "[bold green]/m[/bold green] enter multiline input"
            )
            return self._prompt_and_handle_slash_commands(prompt)
        if user_input in self._MODE_COMMANDS_MAPPING:
            if self.config.mode == self._MODE_COMMANDS_MAPPING[user_input]:
                return self._prompt_and_handle_slash_commands(
                    f"[bold red]Already in {self.config.mode} mode.[/bold red]\n{prompt}"
                )
            self.config.mode = self._MODE_COMMANDS_MAPPING[user_input]
            console.print(f"Switched to [bold green]{self.config.mode}[/bold green] mode.")
        return user_input
