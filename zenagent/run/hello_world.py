"""Minimal Python API example: no CLI, no config files."""

import os
import sys

from zenagent.agents.default import DefaultAgent
from zenagent.environments.local import LocalEnvironment
from zenagent.models.openai_model import OpenAIModel

SYSTEM = "You are a helpful assistant that can do anything."
INSTANCE = (
    "Your task: {{task}}. Use the bash tool to run shell commands. "
    "To finish, run `echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT` as a separate command."
)

if __name__ == "__main__":
    task = sys.argv[1] if len(sys.argv) > 1 else "Write a haiku about bash into haiku.txt, then submit."
    agent = DefaultAgent(
        OpenAIModel(model_name=os.getenv("ZEN_MODEL_NAME", "deepseek-v4-flash")),
        LocalEnvironment(),
        system_template=SYSTEM,
        instance_template=INSTANCE,
    )
    print(agent.run(task))
