from zenagent import Agent, Environment, Model
from zenagent.utils import import_class

_AGENT_MAPPING = {
    "default": "zenagent.agents.default.DefaultAgent",
    "interactive": "zenagent.agents.interactive.InteractiveAgent",
}


def get_agent(model: Model, env: Environment, config: dict, *, default_type: str = "default") -> Agent:
    config = dict(config)
    agent_class = import_class(config.pop("agent_class", None) or default_type, _AGENT_MAPPING, "agent")
    return agent_class(model, env, **config)
