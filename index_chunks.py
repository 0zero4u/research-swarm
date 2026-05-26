#!/usr/bin/env python3
"""
Index research chunks into LightRAG with OpenRouter embedding.
Uses intfloat/multilingual-e5-large for embeddings via OpenRouter.
"""

import asyncio
import json
import os
import sys

import numpy as np

# Set OpenRouter API key
api_key = os.environ.get("OPENROUTER_API_KEY")
if not api_key:
    sys.exit("ERROR: OPENROUTER_API_KEY environment variable not set")

os.environ["OPENROUTER_API_KEY"] = api_key

from lightrag import LightRAG
from lightrag.utils import EmbeddingFunc
from lightrag.llm.openai import openai_complete_if_cache

import httpx


WORKING_DIR = "/home/arshhtripathi/research-swarm/lightrag_index"
CHUNKS_FILE = "/home/arshhtripathi/research-swarm/chunks.json"

# Embedding model config for intfloat/multilingual-e5-large via OpenRouter
EMBEDDING_MODEL = "intfloat/multilingual-e5-large"
EMBEDDING_DIM = 1024
EMBEDDING_MAX_TOKEN = 512
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


async def embedding_func(texts: list[str]) -> np.ndarray:
    """Embed texts using multilingual-e5-large via OpenRouter with raw httpx."""
    prefixed_texts = [f"passage: {t}" for t in texts]

    timeout = httpx.Timeout(30.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{OPENROUTER_BASE_URL}/embeddings",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": EMBEDDING_MODEL,
                "input": prefixed_texts,
            },
        )
        response.raise_for_status()
        result = response.json()

    data = result.get("data", [])
    # Sort by index to maintain order
    data_sorted = sorted(data, key=lambda x: x.get("index", 0))
    embeddings = [np.array(item["embedding"], dtype=np.float32) for item in data_sorted]
    return np.array(embeddings, dtype=np.float32)


async def llm_func(prompt, system_prompt=None, history_messages=None, **kwargs):
    """Minimal LLM function - required by LightRAG but not used for indexing."""
    return await openai_complete_if_cache(
        "openai/gpt-4o-mini",
        prompt,
        system_prompt=system_prompt,
        history_messages=history_messages or [],
        api_key=api_key,
        base_url=OPENROUTER_BASE_URL,
        **kwargs,
    )


async def main():
    # Ensure working directory exists
    os.makedirs(WORKING_DIR, exist_ok=True)

    # Initialize LightRAG
    rag = LightRAG(
        working_dir=WORKING_DIR,
        llm_model_func=llm_func,
        embedding_func=EmbeddingFunc(
            embedding_dim=EMBEDDING_DIM,
            max_token_size=EMBEDDING_MAX_TOKEN,
            func=embedding_func,
        ),
    )

    await rag.initialize_storages()
    print("LightRAG initialized successfully")

    # Load chunks
    with open(CHUNKS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    chunks = data.get("chunks", [])
    print(f"Loaded {len(chunks)} chunks from {CHUNKS_FILE}")

    # Index all chunks concurrently using insert_custom_kg
    async def index_chunk(chunk: dict, idx: int):
        try:
            custom_kg = {
                "chunks": [{
                    "content": chunk["text"],
                    "source_id": chunk["chunk_id"],
                    "file_path": chunk.get("source_id", "") + "#" + chunk["chunk_id"],
                    "chunk_id": chunk["chunk_id"],
                    "author": chunk.get("author", ""),
                    "page": chunk.get("page", ""),
                    "section": chunk.get("section", ""),
                    "themes": chunk.get("themes", []),
                    "citation_refs": chunk.get("citation_refs", []),
                }],
                "entities": [],
                "relationships": []
            }
            await rag.ainsert_custom_kg(custom_kg)
            return (idx, chunk["chunk_id"], True, None)
        except Exception as e:
            return (idx, chunk["chunk_id"], False, str(e))

    # Index all chunks concurrently
    tasks = [index_chunk(c, i) for i, c in enumerate(chunks)]
    results = await asyncio.gather(*tasks)

    success_count = 0
    for idx, chunk_id, ok, err in sorted(results):
        if ok:
            print(f"  [OK] {chunk_id}")
            success_count += 1
        else:
            print(f"  [ERR] {chunk_id}: {err}")

    print(f"\nIndexed {success_count}/{len(chunks)} chunks successfully")
    print(f"Index persisted to: {WORKING_DIR}")

    # Verify persistence
    if os.path.exists(WORKING_DIR):
        files = sorted(os.listdir(WORKING_DIR))
        print(f"Index files: {files}")


if __name__ == "__main__":
    asyncio.run(main())
