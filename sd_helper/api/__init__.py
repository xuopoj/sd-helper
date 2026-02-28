"""API wrappers for Huawei Cloud services."""

from .llm import (
    LLMClient,
    ModelConfig,
    build_vision_message,
    bytes_to_data_url,
    image_to_data_url,
    get_default_model,
    get_llm_config,
    get_model_config,
    list_models,
)

__all__ = [
    "LLMClient",
    "ModelConfig",
    "build_vision_message",
    "bytes_to_data_url",
    "image_to_data_url",
    "get_default_model",
    "get_llm_config",
    "get_model_config",
    "list_models",
]
