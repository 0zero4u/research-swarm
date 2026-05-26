#!/usr/bin/env python3
"""Phase 6: Relationship-first retrieval."""
import os
import json
import asyncio
import numpy as np
import httpx

WORKING_DIR = "/home/arshhtripathi/research-swarm/lightrag_index"
CHUNKS_FILE = "/home/arshhtripathi/research-swarm/chunks.json"
THEME_INDEX = "/home/arshhtripathi/research-swarm/graphs/theme_index.json"
EMBEDDING_MODEL = "intfloat/multilingual-e5-large"
EMBEDDING_DIM = 1024
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
api_key = os.environ.get("OPENROUTER_API_KEY", "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")

async def embed_func(texts: list[str]) -> np.ndarray:
    prefixed = [f"passage: {t}" for t in texts]
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{OPENROUTER_BASE_URL}/embeddings",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": EMBEDDING_MODEL, "input": prefixed},
        )
        resp.raise_for_status()
        result = resp.json()
        data = result.get("data", [])
        embeddings = [item["embedding"] for item in sorted(data, key=lambda x: x.get("index", 0))]
        return np.array(embeddings, dtype=np.float32)

def cosine_sim(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

async def main():
    with open(THEME_INDEX) as f:
        theme_index = json.load(f)
    with open(CHUNKS_FILE) as f:
        data = json.load(f)
    chunks = data["chunks"]
    print(f"Loaded {len(chunks)} chunks, {len(theme_index)} themes")

    query = "What does the paper say about Gandhi and partition?"
    print(f"\nQuery: {query}")

    query_lower = query.lower()
    query_themes = [t for t in theme_index.keys() if t.lower() in query_lower]
    print(f"Themes detected: {query_themes}")

    candidates = set()
    for theme in query_themes:
        if theme in theme_index:
            candidates.update(theme_index[theme])
    print(f"Candidate chunks: {len(candidates)}")

    candidate_chunks = [c for c in chunks if c["chunk_id"] in candidates]

    query_emb = await embed_func([query])

    scores = []
    for c in candidate_chunks:
        chunk_emb = await embed_func([c["text"][:1500]])
        score = cosine_sim(query_emb[0], chunk_emb[0])
        scores.append((score, c))

    scores.sort(reverse=True)

    print("\n--- Evidence Pack ---")
    for score, c in scores[:3]:
        print(f"\nChunk: {c['chunk_id']}")
        print(f"  Author: {c['author']}")
        print(f"  Page: {c['page']}")
        print(f"  Section: {c['section']}")
        print(f"  Confidence: {score:.3f}")
        print(f"  Text: {c['text'][:300]}...")

if __name__ == "__main__":
    asyncio.run(main())