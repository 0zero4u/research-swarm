# Research Swarm

Academic research-writing pipeline with citation lineage tracking.

## Mission

Build grounded academic content where every sentence is traceable to its source.

## Architecture

See [roadmap](https://github.com/0zero4u/research-swarm/blob/main/research_swarm_roadmap.md) for full implementation plan.

## Stack

- **Embedding:** `intfloat/multilingual-e5-large` (OpenRouter)
- **Reranker:** `cross-encoder/ms-marco-MiniLM-L-6-v2` (HuggingFace)
- **Writer:** `qwen/qwen3-72B-Instruct` (OpenRouter)
- **RAG:** LightRAG (HKUDS)

## Setup

```bash
export OPENROUTER_API_KEY="your-key-here"
```
