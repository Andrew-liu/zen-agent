"""Run zen-agent in your local environment. This is the default executable `zen`."""

import os
from pathlib import Path
from typing import Any

import typer
from rich.console import Console

from zenagent import global_config_dir
from zenagent.agents import get_agent
from zenagent.config import builtin_config_dir, get_config_from_spec
from zenagent.environments import get_environment
from zenagent.models import get_model
from zenagent.utils.prompt import multiline_prompt
from zenagent.utils.serialize import UNSET, recursive_merge

DEFAULT_CONFIG_FILE = Path(os.getenv("ZEN_CONFIG_PATH", builtin_config_dir / "mini.yaml"))
DEFAULT_OUTPUT_FILE = global_config_dir / "last_run.traj.json"

_CONFIG_SPEC_HELP = (
    "Config files, names or key=value pairs, merged recursively. "
    "If you set this option the default config is NOT used, so add `-c mini.yaml` explicitly, "
    "e.g. `-c mini.yaml -c model.model_kwargs.temperature=0.5`."
)

console = Console(highlight=False)
app = typer.Typer(rich_markup_mode="rich", add_completion=False, help="Run zen-agent in your local environment.")


@app.command()
def main(
    model_name: str | None = typer.Option(None, "-m", "--model", help="Model to use"),
    model_class: str | None = typer.Option(None, "--model-class", help="Model class ('openai' or import path)"),
    agent_class: str | None = typer.Option(None, "--agent-class", help="Agent class ('default', 'interactive' or import path)"),
    environment_class: str | None = typer.Option(None, "--environment-class", help="Environment ('local', 'docker' or import path)"),
    task: str | None = typer.Option(None, "-t", "--task", help="Task/problem statement", show_default=False),
    yolo: bool = typer.Option(False, "-y", "--yolo", help="Run without confirmation"),
    cost_limit: float | None = typer.Option(None, "-l", "--cost-limit", help="Cost limit in USD. 0 disables."),
    config_spec: list[str] = typer.Option([str(DEFAULT_CONFIG_FILE)], "-c", "--config", help=_CONFIG_SPEC_HELP),
    output: Path | None = typer.Option(DEFAULT_OUTPUT_FILE, "-o", "--output", help="Output trajectory file"),
    exit_immediately: bool = typer.Option(False, "--exit-immediately", help="Exit immediately when the agent finishes instead of prompting."),
) -> Any:
    console.print(f"Building agent config from specs: [bold green]{config_spec}[/bold green]")
    configs = [get_config_from_spec(spec) for spec in config_spec]
    configs.append(
        {
            "run": {"task": task or UNSET},
            "agent": {
                "agent_class": agent_class or UNSET,
                "mode": "yolo" if yolo else UNSET,
                "cost_limit": cost_limit if cost_limit is not None else UNSET,
                "confirm_exit": False if exit_immediately else UNSET,
                "output_path": output or UNSET,
            },
            "model": {"model_class": model_class or UNSET, "model_name": model_name or UNSET},
            "environment": {"environment_class": environment_class or UNSET},
        }
    )
    config = recursive_merge(*configs)

    if (run_task := config.get("run", {}).get("task", UNSET)) is UNSET:
        console.print("[bold yellow]What do you want to do?[/bold yellow] (finish with Ctrl+D)")
        run_task = multiline_prompt()
        console.print("[bold green]Got that, thanks![/bold green]")

    model = get_model(config=config.get("model", {}))
    env = get_environment(config.get("environment", {}), default_type="local")
    agent = get_agent(model, env, config.get("agent", {}), default_type="interactive")
    agent.run(run_task)
    if output_path := config.get("agent", {}).get("output_path"):
        console.print(f"Saved trajectory to [bold green]'{output_path}'[/bold green]")
    return agent


if __name__ == "__main__":
    app()
