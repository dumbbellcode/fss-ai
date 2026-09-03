#!/usr/bin/env python3
"""Create vector embeddings for text chunks using OpenAI embeddings via OpenRouter."""

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings

from ingestion.chunks_creator import Chunk
from ingestion.config import EMBEDDING_BATCH_SIZE, EMBEDDING_MODEL, OPENROUTER_BASE_URL

DEFAULT_EMBEDDING_MODEL = EMBEDDING_MODEL

load_dotenv()


def build_embeddings(model: str = DEFAULT_EMBEDDING_MODEL) -> OpenAIEmbeddings:
    return OpenAIEmbeddings(
        model=model,
        base_url=OPENROUTER_BASE_URL,
        api_key=os.environ["OPENROUTER_API_KEY"],
        chunk_size=EMBEDDING_BATCH_SIZE,
        check_embedding_ctx_length=False,
    )


def create_embeddings(chunks: list[Chunk], model: str = DEFAULT_EMBEDDING_MODEL) -> list[list[float]]:
    """Embed the text of ``chunks`` into a list of vectors, one per chunk."""
    embedder = build_embeddings(model)
    return embedder.embed_documents([chunk.text for chunk in chunks])


def main() -> None:
    parser = argparse.ArgumentParser(description="Create embeddings for text chunks.")
    parser.add_argument("chunks_json_path", type=Path)
    parser.add_argument("output_json_path", type=Path)
    parser.add_argument("--model", default=DEFAULT_EMBEDDING_MODEL, help="Embedding model id (OpenRouter format).")
    args = parser.parse_args()

    chunks_data = json.loads(args.chunks_json_path.read_text(encoding="utf-8"))
    chunks = [Chunk(text=item["text"], metadata=item.get("metadata", {})) for item in chunks_data]
    embeddings = create_embeddings(chunks, model=args.model)

    args.output_json_path.parent.mkdir(parents=True, exist_ok=True)
    args.output_json_path.write_text(json.dumps(embeddings) + "\n", encoding="utf-8")
    print(f"Wrote {len(embeddings)} embeddings (dim {len(embeddings[0])}) to: {args.output_json_path}")


if __name__ == "__main__":
    main()
