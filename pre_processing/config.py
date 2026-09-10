"""Central configuration for the preprocessing pipeline."""

from dataclasses import dataclass


@dataclass(frozen=True)
class PreprocessingConfig:
    """Runtime settings for LLM-backed preprocessing operations."""

    base_url: str = "https://openrouter.ai/api/v1"
    api_key_env: str = "OPENROUTER_API_KEY"
    provider_order: tuple[str, ...] = ("coreweave",)
    allow_provider_fallbacks: bool = False
    require_provider_parameters: bool = False
    temperature: float = 0
    reasoning_effort: str = "low"
    amendment_parser_model: str = "openai/gpt-oss-120b"
    amendment_parser_max_tokens: int = 4_096
    amendment_parser_chunk_tokens: int = 6_000
    amendment_applier_model: str = "openai/gpt-oss-120b"
    amendment_applier_max_tokens: int = 4_096
    max_amendment_workers: int = 7


DEFAULT_CONFIG = PreprocessingConfig()
