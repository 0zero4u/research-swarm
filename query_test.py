#!/usr/bin/env python3
"""Test query script for LightRAG index."""
import os
import json
import httpx
from lightrag import LightRAG

async def embed_texts(texts):
    """Embed texts using OpenRouter e5-large."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://openrouter.ai/api/v1/embeddings",
            headers={
                "Authorization": f"Bearer {os.environ.get('OPENROUTER_API_KEY')}",
                "Content-Type": "application/json"
            },
            json={
                "model": "intfloat/multilingual-e5-large",
                "input": texts
            },
            timeout=60.0
        )
        data = response.json()
        return [item["embedding"] for item in data["data"]]

async def main():
    query = "What does the paper say about Gandhi?"
    
    # Initialize LightRAG
    rag = LightRAG(
        working_dir="/home/arshhtripathi/research-swarm/lightrag_index",
        embedding_func=embed_texts,
    )
    
    # Query
    result = await rag.aquery(query)
    print(f"Query: {query}")
    print(f"Result: {result}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
