"""Execute bash commands inside a long-running docker (or podman) container."""

import logging
import os
import shlex
import subprocess
import uuid
from typing import Any

from pydantic import BaseModel

from zenagent.environments.local import check_finished, error_output
from zenagent.utils.serialize import recursive_merge


class DockerEnvironmentConfig(BaseModel):
    image: str
    cwd: str = "/"
    env: dict[str, str] = {}
    """Environment variables set inside the container."""
    forward_env: list[str] = []
    """Host environment variables forwarded into the container."""
    timeout: int = 30
    executable: str = os.getenv("ZEN_DOCKER_EXECUTABLE", "docker")
    run_args: list[str] = ["--rm"]
    container_timeout: str = "2h"
    """Argument of `sleep` that keeps the container alive."""
    pull_timeout: int = 120


class DockerEnvironment:
    def __init__(self, *, config_class: type = DockerEnvironmentConfig, logger: logging.Logger | None = None, **kwargs):
        self.config = config_class(**kwargs)
        self.logger = logger or logging.getLogger("zenagent.docker")
        self.container_id: str | None = None
        self._start_container()

    def _start_container(self) -> None:
        name = f"zenagent-{uuid.uuid4().hex[:8]}"
        cmd = [
            self.config.executable,
            "run",
            "-d",
            "--name",
            name,
            "-w",
            self.config.cwd,
            *self.config.run_args,
            self.config.image,
            "sleep",
            self.config.container_timeout,
        ]
        self.logger.debug("Starting container: %s", shlex.join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=self.config.pull_timeout, check=True)
        self.container_id = result.stdout.strip()

    def execute(self, action: dict, cwd: str = "", *, timeout: int | None = None) -> dict[str, Any]:
        assert self.container_id, "Container not started"
        command = action.get("command", "")
        cmd = [self.config.executable, "exec", "-w", cwd or self.config.cwd]
        for key in self.config.forward_env:
            if (value := os.getenv(key)) is not None:
                cmd += ["-e", f"{key}={value}"]
        for key, value in self.config.env.items():
            cmd += ["-e", f"{key}={value}"]
        cmd += [self.container_id, "bash", "-lc", command]
        try:
            result = subprocess.run(
                cmd,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=timeout or self.config.timeout,
            )
            output = {"output": result.stdout, "returncode": result.returncode, "exception_info": ""}
        except Exception as e:
            output = error_output(e)
        check_finished(output)
        return output

    def cleanup(self) -> None:
        if self.container_id:
            subprocess.Popen(
                f"(timeout 60 {self.config.executable} stop {self.container_id} || "
                f"{self.config.executable} rm -f {self.container_id}) >/dev/null 2>&1 &",
                shell=True,
            )
            self.container_id = None

    def __del__(self):
        self.cleanup()

    def get_template_vars(self, **kwargs) -> dict[str, Any]:
        return recursive_merge(self.config.model_dump(), kwargs)

    def serialize(self) -> dict:
        return {
            "info": {
                "config": {
                    "environment": self.config.model_dump(mode="json"),
                    "environment_type": f"{self.__class__.__module__}.{self.__class__.__name__}",
                }
            }
        }
