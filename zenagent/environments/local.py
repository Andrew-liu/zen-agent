"""Execute bash commands directly on the local machine. Every command runs in a fresh subshell."""

import os
import platform
import signal
import subprocess
from typing import Any

from pydantic import BaseModel

from zenagent.exceptions import Submitted
from zenagent.utils.serialize import recursive_merge

SUBMIT_MARKER = "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"


class LocalEnvironmentConfig(BaseModel):
    cwd: str = ""
    env: dict[str, str] = {}
    timeout: int = 30


def check_finished(output: dict) -> None:
    """Raise Submitted if the first output line is the submit marker (and the command succeeded)."""
    lines = (output.get("output") or "").lstrip().splitlines(keepends=True)
    if lines and lines[0].strip() == SUBMIT_MARKER and output.get("returncode") == 0:
        submission = "".join(lines[1:])
        raise Submitted(
            {
                "role": "exit",
                "content": submission,
                "extra": {"exit_status": "Submitted", "submission": submission},
            }
        )


def error_output(e: Exception) -> dict[str, Any]:
    raw = getattr(e, "output", None)
    raw = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else (raw or "")
    return {
        "output": raw,
        "returncode": -1,
        "exception_info": f"An error occurred while executing the command: {e}",
        "extra": {"exception_type": type(e).__name__, "exception": str(e)},
    }


class LocalEnvironment:
    def __init__(self, *, config_class: type = LocalEnvironmentConfig, **kwargs):
        self.config = config_class(**kwargs)

    def execute(self, action: dict, cwd: str = "", *, timeout: int | None = None) -> dict[str, Any]:
        command = action.get("command", "")
        cwd = cwd or self.config.cwd or os.getcwd()
        try:
            result = _run(command, cwd, os.environ | self.config.env, timeout or self.config.timeout)
            output = {"output": result.stdout, "returncode": result.returncode, "exception_info": ""}
        except Exception as e:
            output = error_output(e)
        check_finished(output)
        return output

    def get_template_vars(self, **kwargs) -> dict[str, Any]:
        return recursive_merge(self.config.model_dump(), platform.uname()._asdict(), dict(os.environ), kwargs)

    def serialize(self) -> dict:
        return {
            "info": {
                "config": {
                    "environment": self.config.model_dump(mode="json"),
                    "environment_type": f"{self.__class__.__module__}.{self.__class__.__name__}",
                }
            }
        }


def _run(command: str, cwd: str, env: dict[str, str], timeout: int) -> subprocess.CompletedProcess:
    """Like subprocess.run, but kills the whole process group on timeout so no children are orphaned."""
    process = subprocess.Popen(
        command,
        shell=True,
        text=True,
        cwd=cwd,
        env=env,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=os.name == "posix",
    )
    try:
        stdout, _ = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        stdout, _ = process.communicate()
        raise subprocess.TimeoutExpired(command, timeout, output=stdout)
    return subprocess.CompletedProcess(command, process.returncode, stdout=stdout)
