#!/usr/bin/env python3
"""
Retriever Agent - Semantic search over FAISS vector index.

Reads the FAISS index and manifest, embeds the query, and returns
relevant chunks as an evidence pack.
"""

import argparse
import json
import os
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import faiss
import numpy as np
import requests

# Constants
EMBEDDING_MODEL = "qwen/qwen3-embedding-8b"
EMBEDDING_DIM = 4096
DEFAULT_TOP_K = 10
_BASE_DIR = Path(__file__).parent
DEFAULT_INDEX_DIR = _BASE_DIR / "vector_index"
DEFAULT_CHUNKS_PATH = _BASE_DIR / "chunks" / "chunks.json"
INDEX_FILE = "index.faiss"
MANIFEST_FILE = "manifest.json"
EVIDENCE_PACKS_DIR = Path("evidence_packs")


@dataclass
class RetrieverConfig:
    """Configuration for the retriever."""
    query: str
    top_k: int = DEFAULT_TOP_K
    index_dir: Path = DEFAULT_INDEX_DIR
    chunks_path: Path = DEFAULT_CHUNKS_PATH
    api_key: Optional[str] = None
    embedding_model: str = EMBEDDING_MODEL
    embedding_dim: int = EMBEDDING_DIM
    save_evidence: bool = True
    min_confidence: float = 0.30


@dataclass
class EvidenceResult:
    """Single retrieval result."""
    chunk_id: str
    source_id: str
    source_filename: str
    page: int
    text: str
    score: float


@dataclass
class EvidencePack:
    """Evidence pack containing retrieval results."""
    query: str
    top_k: int
    results: list[EvidenceResult]
    total_chunks_searched: int

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "query": self.query,
            "top_k": self.top_k,
            "results": [
                {
                    "chunk_id": r.chunk_id,
                    "source_id": r.source_id,
                    "source_filename": r.source_filename,
                    "page": r.page,
                    "text": r.text,
                    "score": round(r.score, 4),
                }
                for r in self.results
            ],
            "total_chunks_searched": self.total_chunks_searched,
        }


class OpenRouterClient:
    """Client for OpenRouter API embeddings."""

    BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(self, api_key: str, model: str = EMBEDDING_MODEL):
        self.api_key = api_key
        self.model = model
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://research-swarm.ai",
            "X-Title": "Research Swarm Retriever",
        })

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        Embed multiple texts using OpenRouter API.

        Args:
            texts: List of text strings to embed

        Returns:
            List of embedding vectors (normalized)
        """
        if not texts:
            return []

        payload = {
            "model": self.model,
            "input": texts,
        }

        max_retries = 3
        retry_delay = 5

        for attempt in range(max_retries):
            try:
                response = self.session.post(
                    f"{self.BASE_URL}/embeddings",
                    json=payload,
                    timeout=120,
                )
                response.raise_for_status()
                data = response.json()

                embeddings = []
                for item in data["data"]:
                    emb = item["embedding"]
                    # Normalize for cosine similarity (same as embedder.py)
                    emb_array = np.array(emb, dtype=np.float32)
                    norm = np.linalg.norm(emb_array)
                    if norm > 0:
                        emb_array = emb_array / norm
                    embeddings.append(emb_array.tolist())

                return embeddings

            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    print(f"API request failed (attempt {attempt + 1}/{max_retries}): {e}", file=sys.stderr)
                    import time
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    raise RuntimeError(f"Failed to get embeddings after {max_retries} attempts: {e}")


class Retriever:
    """Semantic retriever using FAISS index."""

    def __init__(self, config: RetrieverConfig):
        self.config = config
        self.api_key = config.api_key or os.environ.get("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY not found in environment or config")

        self.client = OpenRouterClient(self.api_key, config.embedding_model)
        self.index: Optional[faiss.Index] = None
        self.manifest: dict = {}
        self.chunks_index: dict[str, dict] = {}  # chunk_id -> chunk data
        self.total_vectors = 0

    def load_index(self):
        """Load FAISS index from disk."""
        index_path = self.config.index_dir / INDEX_FILE
        if not index_path.exists():
            raise FileNotFoundError(f"FAISS index not found: {index_path}")

        self.index = faiss.read_index(str(index_path))
        self.total_vectors = self.index.ntotal

        if self.total_vectors == 0:
            raise ValueError("FAISS index is empty")

    def load_manifest(self):
        """Load manifest mapping FAISS indices to chunk IDs."""
        manifest_path = self.config.index_dir / MANIFEST_FILE
        if not manifest_path.exists():
            raise FileNotFoundError(f"Manifest not found: {manifest_path}")

        with open(manifest_path, "r", encoding="utf-8") as f:
            self.manifest = json.load(f)
        
        # Build O(1) lookup index: faiss_idx -> manifest entry
        self._manifest_index = {
            entry["faiss_idx"]: entry
            for entry in self.manifest.get("chunks", [])
            if "faiss_idx" in entry
        }

    def load_chunks_index(self):
        """Load full chunks data for provenance lookup."""
        if not self.config.chunks_path.exists():
            raise FileNotFoundError(f"Chunks file not found: {self.config.chunks_path}")

        with open(self.config.chunks_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        for chunk in data.get("chunks", []):
            self.chunks_index[chunk["chunk_id"]] = chunk

    def normalize_query_vector(self, vector: np.ndarray) -> np.ndarray:
        """
        Normalize query vector for cosine similarity.

        Args:
            vector: Query embedding vector

        Returns:
            L2-normalized vector
        """
        norm = np.linalg.norm(vector)
        if norm > 0:
            return vector / norm
        return vector

    def embed_query(self, query: str) -> np.ndarray:
        """
        Embed query text using OpenRouter API.

        Args:
            query: Query text

        Returns:
            Normalized query embedding vector
        """
        embeddings = self.client.embed_texts([query])
        if not embeddings:
            raise RuntimeError("Failed to embed query")

        vector = np.array(embeddings[0], dtype=np.float32)
        return self.normalize_query_vector(vector).reshape(1, -1)

    def retrieve(self, query: str, top_k: int) -> EvidencePack:
        """
        Retrieve top-k relevant chunks for a query.

        Args:
            query: Search query
            top_k: Number of results to return

        Returns:
            EvidencePack with results
        """
        # Embed query
        query_vector = self.embed_query(query)

        # Search FAISS index
        k = min(top_k, self.total_vectors)
        scores, indices = self.index.search(query_vector, k)

        # Build results
        results = []
        for i, (score, faiss_idx) in enumerate(zip(scores[0], indices[0])):
            if faiss_idx < 0:  # Invalid index
                continue

            # Find chunk_id from manifest via O(1) index
            manifest_entry = self._manifest_index.get(int(faiss_idx))
            if not manifest_entry:
                continue

            chunk_id = manifest_entry.get("chunk_id")
            chunk_data = self.chunks_index.get(chunk_id)

            if not chunk_data:
                continue

            result = EvidenceResult(
                chunk_id=chunk_id,
                source_id=chunk_data.get("source_id", ""),
                source_filename=chunk_data.get("source_filename", ""),
                page=chunk_data.get("page", 1),
                text=chunk_data.get("text", ""),
                score=float(score),
            )
            results.append(result)

        return EvidencePack(
            query=query,
            top_k=top_k,
            results=results,
            total_chunks_searched=self.total_vectors,
        )

    def save_evidence_pack(self, evidence: EvidencePack) -> Path:
        """Save evidence pack to JSON file."""
        EVIDENCE_PACKS_DIR.mkdir(parents=True, exist_ok=True)

        # Create slug from query
        slug = slugify_query(evidence.query)
        output_path = EVIDENCE_PACKS_DIR / f"{slug}.json"

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(evidence.to_dict(), f, indent=2, ensure_ascii=False)

        return output_path


def slugify_query(query: str) -> str:
    """
    Convert query to filesystem-safe slug.

    Args:
        query: Original query string

    Returns:
        Slugified string
    """
    # Normalize unicode
    slug = unicodedata.normalize("NFKD", query)
    # Remove non-alphanumeric except spaces
    slug = re.sub(r"[^\w\s-]", "", slug)
    # Replace spaces with underscores
    slug = re.sub(r"[\s-]+", "_", slug)
    # Limit length and remove trailing underscores
    slug = slug[:100].strip("_")
    return slug or "query"


def parse_args() -> RetrieverConfig:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Retriever - Semantic search over FAISS vector index",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 retriever.py --query "Partition violence in 1947"
  python3 retriever.py --query "Khushwant Singh narrative" --top-k 5
  python3 retriever.py -q "Railway symbolism" -k 20 --no-save
        """,
    )

    parser.add_argument(
        "-q", "--query",
        type=str,
        required=True,
        help="Search query",
    )

    parser.add_argument(
        "-k", "--top-k",
        type=int,
        default=DEFAULT_TOP_K,
        help=f"Number of results to return (default: {DEFAULT_TOP_K})",
    )

    parser.add_argument(
        "--index-dir",
        type=Path,
        default=DEFAULT_INDEX_DIR,
        help=f"Directory containing FAISS index (default: {DEFAULT_INDEX_DIR})",
    )

    parser.add_argument(
        "--chunks",
        type=Path,
        default=DEFAULT_CHUNKS_PATH,
        help=f"Path to chunks.json (default: {DEFAULT_CHUNKS_PATH})",
    )

    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="OpenRouter API key (or set OPENROUTER_API_KEY env var)",
    )

    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.70,
        help="Minimum similarity score threshold (default: 0.70)",
    )

    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Do not save evidence pack to file",
    )

    args = parser.parse_args()

    return RetrieverConfig(
        query=args.query,
        top_k=args.top_k,
        index_dir=args.index_dir,
        chunks_path=args.chunks,
        api_key=args.api_key,
        save_evidence=not args.no_save,
        min_confidence=args.min_confidence,
    )


def main():
    """Entry point."""
    try:
        config = parse_args()

        print("=" * 60, file=sys.stderr)
        print("Research Swarm Retriever", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        print(f"Query: {config.query}", file=sys.stderr)
        print(f"Top-k: {config.top_k}", file=sys.stderr)
        print(f"Index: {config.index_dir}", file=sys.stderr)
        print("-" * 60, file=sys.stderr)

        # Initialize retriever
        retriever = Retriever(config)

        # Load index and data
        print("Loading FAISS index...", file=sys.stderr)
        retriever.load_index()
        print(f"  Loaded {retriever.total_vectors} vectors", file=sys.stderr)

        print("Loading manifest...", file=sys.stderr)
        retriever.load_manifest()
        manifest_chunks = len(retriever.manifest.get("chunks", []))
        print(f"  Manifest has {manifest_chunks} entries", file=sys.stderr)

        print("Loading chunks index...", file=sys.stderr)
        retriever.load_chunks_index()
        print(f"  Indexed {len(retriever.chunks_index)} chunks", file=sys.stderr)

        # Perform retrieval
        print("\nEmbedding query...", file=sys.stderr)
        evidence = retriever.retrieve(config.query, config.top_k)

        before = len(evidence.results)
        evidence.results = [r for r in evidence.results if r.score >= config.min_confidence]
        filtered = before - len(evidence.results)
        if filtered > 0:
            print(f"Filtered {filtered} result(s) below confidence threshold {config.min_confidence}", file=sys.stderr)
        if not evidence.results:
            print("Warning: Low confidence results - consider broadening query", file=sys.stderr)

        # Output results
        print("\n" + "=" * 60, file=sys.stderr)
        print(f"Retrieved {len(evidence.results)} results", file=sys.stderr)
        print("=" * 60, file=sys.stderr)

        # Print evidence pack to stdout
        print(json.dumps(evidence.to_dict(), indent=2, ensure_ascii=False))

        # Save if requested
        if config.save_evidence:
            output_path = retriever.save_evidence_pack(evidence)
            print(f"\nEvidence pack saved to: {output_path}", file=sys.stderr)

        return 0

    except KeyboardInterrupt:
        print("\n\nInterrupted by user.", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
