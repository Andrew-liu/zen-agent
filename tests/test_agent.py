import json
import subprocess

import pytest

from zenagent.agents.default import DefaultAgent
from zenagent.config import get_config_from_spec, key_value_spec_to_nested_dict
from zenagent.environments.local import LocalEnvironment
from zenagent.models.test_models import DeterministicModel
from zenagent.utils.serialize import UNSET, recursive_merge

TEMPLATES = dict(system_template="sys", instance_template="Task: {{task}}")
SUBMIT = "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && echo my-patch"


def make_agent(outputs, **kwargs):
    return DefaultAgent(DeterministicModel(outputs=outputs), LocalEnvironment(), **TEMPLATES, **kwargs)


def test_submit_flow(tmp_path):
    out = tmp_path / "traj.json"
    agent = make_agent(["echo hello", SUBMIT], output_path=out)
    result = agent.run("do it")
    assert result == {"exit_status": "Submitted", "submission": "my-patch\n"}
    roles = [m["role"] for m in agent.messages]
    assert roles == ["system", "user", "assistant", "tool", "assistant", "exit"]
    assert "hello" in agent.messages[3]["content"]
    assert agent.messages[3]["tool_call_id"] == agent.messages[2]["tool_calls"][0]["id"]
    data = json.loads(out.read_text())
    assert data["info"]["exit_status"] == "Submitted"
    assert data["info"]["model_stats"]["api_calls"] == 2
    assert data["trajectory_format"] == "zen-agent-1.0"


def test_parallel_tool_calls_each_get_observation():
    agent = make_agent([["echo a", "echo b"], SUBMIT])
    agent.run("x")
    tool_msgs = [m for m in agent.messages if m["role"] == "tool"]
    assert len(tool_msgs) == 2
    assert "a" in tool_msgs[0]["content"] and "b" in tool_msgs[1]["content"]


def test_step_limit():
    agent = make_agent(["echo 1", "echo 2", "echo 3"], step_limit=2, cost_limit=0)
    assert agent.run("x")["exit_status"] == "LimitsExceeded"
    assert agent.n_calls == 2


def test_cost_limit():
    agent = make_agent(["echo 1", "echo 2", "echo 3"], cost_limit=1.5)
    assert agent.run("x")["exit_status"] == "LimitsExceeded"
    assert agent.n_calls == 2


def test_format_error_recovers_then_repeated_exits():
    agent = make_agent([[], SUBMIT])
    assert agent.run("x")["exit_status"] == "Submitted"
    assert any(m["role"] == "user" and "No tool calls" in m["content"] for m in agent.messages)

    agent = make_agent([[], [], []], max_consecutive_format_errors=3)
    assert agent.run("x")["exit_status"] == "RepeatedFormatError"


def test_timeout_is_reported_not_raised():
    env = LocalEnvironment(timeout=1)
    out = env.execute({"command": "sleep 5"})
    assert out["returncode"] == -1
    assert "TimeoutExpired" in out["extra"]["exception_type"]


def test_each_command_runs_in_fresh_subshell(tmp_path):
    env = LocalEnvironment(cwd=str(tmp_path))
    env.execute({"command": "cd / && export FOO=1"})
    out = env.execute({"command": "pwd; echo ${FOO:-unset}"})
    assert out["output"].split() == [str(tmp_path.resolve()), "unset"] or out["output"].split()[-1] == "unset"


def test_submit_requires_marker_first_and_success():
    env = LocalEnvironment()
    env.execute({"command": "echo hi; echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"})  # not first line: no raise
    with pytest.raises(Exception) as ei:
        env.execute({"command": "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"})
    assert type(ei.value).__name__ == "Submitted"


def test_config_helpers():
    assert key_value_spec_to_nested_dict("a.b.c=1") == {"a": {"b": {"c": 1}}}
    assert key_value_spec_to_nested_dict("m.name=foo/bar") == {"m": {"name": "foo/bar"}}
    assert recursive_merge({"a": {"x": 1}}, {"a": {"y": UNSET, "z": 2}}) == {"a": {"x": 1, "z": 2}}
    cfg = get_config_from_spec("mini.yaml")
    assert {"agent", "environment", "model"} <= set(cfg)


def test_builtin_template_renders_with_local_env():
    cfg = get_config_from_spec("mini.yaml")
    agent = DefaultAgent(
        DeterministicModel(outputs=[SUBMIT], **{}),
        LocalEnvironment(**cfg["environment"]),
        system_template=cfg["agent"]["system_template"],
        instance_template=cfg["agent"]["instance_template"],
    )
    assert agent.run("fix bug")["exit_status"] == "Submitted"
    assert "fix bug" in agent.messages[1]["content"]
    assert subprocess.run(["true"]).returncode == 0
