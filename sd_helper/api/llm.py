"""LLM service client for ModelArts and Pangu models."""

from dataclasses import dataclass
from typing import Generator

import httpx


@dataclass
class ModelConfig:
    """Configuration for an LLM model."""
    name: str
    endpoint: str
    type: str = "modelarts"  # modelarts | pangu
    temperature: float = 0.7
    max_tokens: int = 2048
    system: str | None = None
    verify_ssl: bool = True

    @classmethod
    def from_dict(cls, name: str, data: dict) -> "ModelConfig":
        return cls(
            name=name,
            endpoint=data["endpoint"],
            type=data.get("type", "modelarts"),
            temperature=data.get("temperature", 0.7),
            max_tokens=data.get("max_tokens", 2048),
            system=data.get("system"),
            verify_ssl=data.get("verify_ssl", True),
        )


def get_llm_config(config: dict) -> dict:
    """Extract LLM config section from profile config."""
    return config.get("llm", {})


def get_default_model(config: dict) -> str | None:
    """Get default model name from config."""
    llm_config = get_llm_config(config)
    return llm_config.get("default_model")


def list_models(config: dict) -> list[str]:
    """List available model names."""
    llm_config = get_llm_config(config)
    return list(llm_config.get("models", {}).keys())


def get_model_config(config: dict, model_name: str | None = None) -> ModelConfig | None:
    """
    Get model configuration by name.

    If model_name is None, returns the default model config.
    """
    llm_config = get_llm_config(config)
    models = llm_config.get("models", {})

    if not models:
        return None

    if model_name is None:
        model_name = llm_config.get("default_model")
        if model_name is None:
            # Use first model as default
            model_name = next(iter(models.keys()))

    if model_name not in models:
        return None

    return ModelConfig.from_dict(model_name, models[model_name])


class LLMClient:
    """Client for interacting with LLM endpoints."""

    def __init__(
        self,
        endpoint: str,
        token: str,
        model_type: str = "modelarts",
        timeout: float = 60.0,
        verify_ssl: bool = True,
    ):
        """
        Initialize LLM client.

        Args:
            endpoint: LLM inference endpoint URL
            token: IAM token for authentication
            model_type: Type of model (modelarts or pangu)
            timeout: Request timeout in seconds
            verify_ssl: Whether to verify SSL certificates
        """
        self.endpoint = endpoint.rstrip("/")
        self.token = token
        self.model_type = model_type
        self.timeout = timeout
        self.verify_ssl = verify_ssl

    @classmethod
    def from_config(cls, model_config: ModelConfig, token: str, verify_ssl: bool = True) -> "LLMClient":
        """Create client from ModelConfig."""
        return cls(
            endpoint=model_config.endpoint,
            verify_ssl=verify_ssl,
            token=token,
            model_type=model_config.type,
        )

    def _get_headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "X-Auth-Token": self.token,
        }

    def chat(
        self,
        messages: list[dict],
        stream: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs,
    ) -> dict | Generator[str, None, None]:
        """
        Send chat completion request.

        Args:
            messages: List of message dicts with 'role' and 'content'
            stream: Whether to stream the response
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Additional parameters passed to the model

        Returns:
            Response dict or generator of text chunks if streaming
        """
        payload = self._build_payload(messages, stream, temperature, max_tokens, **kwargs)

        if stream:
            return self._stream_chat(payload)
        return self._sync_chat(payload)

    def _build_payload(
        self,
        messages: list[dict],
        stream: bool,
        temperature: float,
        max_tokens: int,
        **kwargs,
    ) -> dict:
        """Build request payload based on model type."""
        if self.model_type == "pangu":
            # Pangu API format
            return {
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": stream,
                **kwargs,
            }
        else:
            # ModelArts default format
            return {
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": stream,
                **kwargs,
            }

    def _sync_chat(self, payload: dict) -> dict:
        with httpx.Client(timeout=self.timeout, verify=self.verify_ssl) as client:
            response = client.post(
                self.endpoint,
                headers=self._get_headers(),
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    def _stream_chat(self, payload: dict) -> Generator[str, None, None]:
        with httpx.Client(timeout=self.timeout, verify=self.verify_ssl) as client:
            with client.stream(
                "POST",
                self.endpoint,
                headers=self._get_headers(),
                json=payload,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:
                        continue
                    # Handle SSE format: "data: {...}"
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        yield data
