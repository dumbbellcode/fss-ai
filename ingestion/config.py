"""Central configuration for the ingestion pipeline."""

from dataclasses import dataclass


@dataclass(frozen=True)
class IngestionConfig:
    """Runtime settings for chunking, embeddings, and vector storage."""

    chunk_size_tokens: int = 500
    chunk_overlap_tokens: int = 50
    split_separators: tuple[str, ...] = ("\n\n", "\n", ". ", " ")
    base_url: str = "https://openrouter.ai/api/v1"
    embedding_model: str = "openai/text-embedding-3-large"
    embedding_batch_size: int = 32
    collection_name: str = "fssai_regulations"
    persist_dir: str = "db"


DEFAULT_CONFIG = IngestionConfig()
