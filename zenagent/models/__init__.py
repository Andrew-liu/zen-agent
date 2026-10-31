import copy
import os

from zenagent import Model
from zenagent.utils import import_class

DEFAULT_MODEL_NAME = "deepseek-v4-flash"

_MODEL_MAPPING = {
    "openai": "zenagent.models.openai_model.OpenAIModel",
    "deterministic": "zenagent.models.test_models.DeterministicModel",
}


def get_model_name(input_model_name: str | None = None, config: dict | None = None) -> str:
    """Priority: explicit arg > config > $ZEN_MODEL_NAME > $OPENAI_MODEL > default."""
    return (
        input_model_name
        or (config or {}).get("model_name")
        or os.getenv("ZEN_MODEL_NAME")
        or os.getenv("OPENAI_MODEL")
        or DEFAULT_MODEL_NAME
    )


def get_model(input_model_name: str | None = None, config: dict | None = None) -> Model:
    config = copy.deepcopy(config or {})
    config["model_name"] = get_model_name(input_model_name, config)
    model_class = import_class(config.pop("model_class", None) or "openai", _MODEL_MAPPING, "model")
    return model_class(**config)
