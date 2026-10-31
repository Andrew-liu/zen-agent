from zenagent import Environment
from zenagent.utils import import_class

_ENVIRONMENT_MAPPING = {
    "local": "zenagent.environments.local.LocalEnvironment",
    "docker": "zenagent.environments.docker.DockerEnvironment",
}


def get_environment(config: dict, *, default_type: str = "local") -> Environment:
    config = dict(config)
    env_class = import_class(config.pop("environment_class", None) or default_type, _ENVIRONMENT_MAPPING, "environment")
    return env_class(**config)
