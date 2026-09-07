"""Central configuration for the preprocessing pipeline."""

# ---- OpenRouter ------------------------------------------------------------
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
LLM_TEMPERATURE = 0

# Models are configured per LLM-backed preprocessing operation because the
# extraction and amendment-application tasks have different requirements.
AMENDMENT_PARSER_MODEL = "deepseek/deepseek-v4-flash"
AMENDMENT_APPLIER_MODEL = "openai/gpt-4o-mini"

# ---- Amendment application -------------------------------------------------
MAX_AMENDMENT_WORKERS = 7
