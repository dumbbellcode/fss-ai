"""Central configuration for the preprocessing pipeline."""

from dataclasses import dataclass


@dataclass(frozen=True)
class PreprocessingConfig:
    """Runtime settings for LLM-backed preprocessing operations."""

    base_url: str = "https://openrouter.ai/api/v1"
    api_key_env: str = "OPENROUTER_API_KEY"
    temperature: float = 0
    amendment_parser_model: str = "google/gemini-2.5-flash-lite"
    amendment_parser_max_tokens: int = 8_192
    amendment_applier_model: str = "openai/gpt-4o-mini"
    amendment_applier_max_tokens: int = 8_192
    max_amendment_workers: int = 7


DEFAULT_CONFIG = PreprocessingConfig()
