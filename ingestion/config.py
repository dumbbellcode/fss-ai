"""Central configuration for the ingestion pipeline."""

# ---- Chunking -------------------------------------------------------------
# Chunks are sized in tokens (not characters) so they map cleanly to the
# embedding model's token limit and the LLM context window. These are the
# defaults; ``create_chunks`` accepts overrides for benchmarking.
CHUNK_SIZE_TOKENS = 500
CHUNK_OVERLAP_TOKENS = 50
SPLIT_SEPARATORS = ["\n\n", "\n", ". ", " "]

# ---- Embeddings -----------------------------------------------------------
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
EMBEDDING_MODEL = "openai/text-embedding-3-large"
# Keep each embeddings API request below provider prompt-token limits.
EMBEDDING_BATCH_SIZE = 32

# ---- Chroma store ---------------------------------------------------------
COLLECTION_NAME = "fssai_regulations"
PERSIST_DIR = "db"
