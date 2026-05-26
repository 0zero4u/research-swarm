#!/usr/bin/env python3
"""
Embedder Agent - Creates FAISS vectors from document chunks.

Reads chunks from chunks/chunks.json and creates a FAISS index with
normalized embeddings using OpenRouter's qwen3-embedding-8b model.
"""

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import faiss
import numpy as np
import requests

# Constants
EMBEDDING_MODEL = "qwen/qwen3-embedding-8b"
EMBEDDING_DIM = 1024
DEFAULT_BATCH_SIZE = 32
DEFAULT_CHUNKS_PATH = Path("chunks/chunks.json")
DEFAULT_INDEX_DIR = Path("vector_index")
INDEX_FILE = "index.faiss"
MANIFEST_FILE = "manifest.json"


@dataclass
class EmbedderConfig:
    """Configuration for the embedder."""
    chunks_path: Path = DEFAULT_CHUNKS_PATH
    index_dir: Path = DEFAULT_INDEX_DIR
    batch_size: int = DEFAULT_BATCH_SIZE
    resume: bool = False
    api_key: Optional[str] = None
    embedding_model: str = EMBEDDING_MODEL
    embedding_dim: int = EMBEDDING_DIM


@dataclass
class Chunk:
    """Represents a document chunk."""
    chunk_id: str
    text: str
    metadata: dict = field(default_factory=dict)


@dataclass
class ChunkManifest:
    """Manifest mapping FAISS indices to chunk IDs."""
    chunks: list[dict] = field(default_factory=list)


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
            "X-Title": "Research Swarm Embedder",
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
                    # Normalize for cosine similarity
                    emb_array = np.array(emb, dtype=np.float32)
                    norm = np.linalg.norm(emb_array)
                    if norm > 0:
                        emb_array = emb_array / norm
                    embeddings.append(emb_array.tolist())
                
                return embeddings
                
            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    print(f"API request failed (attempt {attempt + 1}/{max_retries}): {e}")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    raise RuntimeError(f"Failed to get embeddings after {max_retries} attempts: {e}")
    
    def check_api_key(self) -> bool:
        """Verify API key is valid."""
        try:
            response = self.session.get(
                f"{self.BASE_URL}/auth/key",
                timeout=10,
            )
            return response.status_code == 200
        except Exception:
            return False


class Embedder:
    """Main embedder class for creating FAISS vectors."""
    
    def __init__(self, config: EmbedderConfig):
        self.config = config
        self.api_key = config.api_key or os.environ.get("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY not found in environment or config")
        
        self.client = OpenRouterClient(self.api_key, config.embedding_model)
        self.index: Optional[faiss.Index] = None
        self.manifest = ChunkManifest()
        self.processed_count = 0
        self.total_chunks = 0
    
    def load_chunks(self) -> list[Chunk]:
        """Load chunks from JSON file."""
        if not self.config.chunks_path.exists():
            raise FileNotFoundError(f"Chunks file not found: {self.config.chunks_path}")
        
        with open(self.config.chunks_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        chunks = []
        for item in data.get("chunks", []):
            chunk = Chunk(
                chunk_id=item["chunk_id"],
                text=item["text"],
                metadata=item.get("metadata", {}),
            )
            chunks.append(chunk)
        
        return chunks
    
    def initialize_index(self):
        """Initialize or load FAISS index."""
        self.config.index_dir.mkdir(parents=True, exist_ok=True)
        
        index_path = self.config.index_dir / INDEX_FILE
        manifest_path = self.config.index_dir / MANIFEST_FILE
        
        if self.config.resume and index_path.exists() and manifest_path.exists():
            # Resume from existing index
            print(f"Resuming from existing index at {self.config.index_dir}")
            self.index = faiss.read_index(str(index_path))
            
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest_data = json.load(f)
                self.manifest = ChunkManifest(**manifest_data)
            
            self.processed_count = len(self.manifest.chunks)
            print(f"Loaded existing index with {self.processed_count} vectors")
        else:
            # Create new index
            print("Creating new FAISS index (IndexFlatIP for inner product)")
            self.index = faiss.IndexFlatIP(self.config.embedding_dim)
            self.manifest = ChunkManifest()
            self.processed_count = 0
    
    def embed_batch(self, chunks: list[Chunk]) -> np.ndarray:
        """Embed a batch of chunks."""
        texts = [chunk.text for chunk in chunks]
        embeddings = self.client.embed_texts(texts)
        
        # Convert to numpy array for FAISS
        return np.array(embeddings, dtype=np.float32)
    
    def process_chunks(self, chunks: list[Chunk]):
        """Process all chunks and build FAISS index."""
        self.total_chunks = len(chunks)
        
        if self.processed_count >= self.total_chunks:
            print(f"All {self.total_chunks} chunks already processed")
            return
        
        # Process in batches
        remaining = chunks[self.processed_count:]
        
        for i in range(0, len(remaining), self.config.batch_size):
            batch = remaining[i:i + self.config.batch_size]
            batch_num = (i // self.config.batch_size) + 1
            total_batches = (len(remaining) + self.config.batch_size - 1) // self.config.batch_size
            
            print(f"Processing batch {batch_num}/{total_batches} ({len(batch)} chunks)...")
            
            # Get embeddings
            vectors = self.embed_batch(batch)
            
            # Add to index
            start_idx = self.processed_count
            self.index.add(vectors)
            
            # Update manifest
            for j, chunk in enumerate(batch):
                self.manifest.chunks.append({
                    "chunk_id": chunk.chunk_id,
                    "faiss_idx": start_idx + j,
                })
            
            self.processed_count += len(batch)
            
            # Save progress
            self.save_index()
            
            print(f"  Progress: {self.processed_count}/{self.total_chunks} chunks indexed")
    
    def save_index(self):
        """Save FAISS index and manifest to disk."""
        index_path = self.config.index_dir / INDEX_FILE
        manifest_path = self.config.index_dir / MANIFEST_FILE
        
        faiss.write_index(self.index, str(index_path))
        
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(self.manifest.__dict__, f, indent=2, ensure_ascii=False)
    
    def run(self):
        """Main execution method."""
        print("=" * 60)
        print("Research Swarm Embedder")
        print("=" * 60)
        print(f"Model: {self.config.embedding_model}")
        print(f"Dimensions: {self.config.embedding_dim}")
        print(f"Batch size: {self.config.batch_size}")
        print(f"Chunks file: {self.config.chunks_path}")
        print(f"Output directory: {self.config.index_dir}")
        print("=" * 60)
        
        # Verify API key
        print("Verifying OpenRouter API key...")
        if not self.client.check_api_key():
            raise RuntimeError("Invalid OpenRouter API key")
        print("API key verified\n")
        
        # Load chunks
        print(f"Loading chunks from {self.config.chunks_path}...")
        chunks = self.load_chunks()
        self.total_chunks = len(chunks)
        print(f"Loaded {self.total_chunks} chunks\n")
        
        # Initialize index
        self.initialize_index()
        
        # Process chunks
        print("Building FAISS index...\n")
        self.process_chunks(chunks)
        
        # Final save
        self.save_index()
        
        print("\n" + "=" * 60)
        print("Embedding Complete!")
        print("=" * 60)
        print(f"Total vectors: {self.index.ntotal}")
        print(f"Index saved to: {self.config.index_dir / INDEX_FILE}")
        print(f"Manifest saved to: {self.config.index_dir / MANIFEST_FILE}")


def parse_args() -> EmbedderConfig:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Embedder - Create FAISS vectors from document chunks",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 embedder.py              Process all chunks
  python3 embedder.py --batch 50   Use batch size of 50
  python3 embedder.py --resume     Resume interrupted processing
        """,
    )
    
    parser.add_argument(
        "--chunks",
        type=Path,
        default=DEFAULT_CHUNKS_PATH,
        help=f"Path to chunks.json (default: {DEFAULT_CHUNKS_PATH})",
    )
    
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_INDEX_DIR,
        help=f"Output directory for index (default: {DEFAULT_INDEX_DIR})",
    )
    
    parser.add_argument(
        "--batch",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Batch size for embedding (default: {DEFAULT_BATCH_SIZE})",
    )
    
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from existing index and manifest",
    )
    
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="OpenRouter API key (or set OPENROUTER_API_KEY env var)",
    )
    
    return EmbedderConfig(
        chunks_path=parser.parse_args().chunks,
        index_dir=parser.parse_args().output,
        batch_size=parser.parse_args().batch,
        resume=parser.parse_args().resume,
        api_key=parser.parse_args().api_key,
    )


def main():
    """Entry point."""
    try:
        config = parse_args()
        embedder = Embedder(config)
        embedder.run()
        return 0
    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Progress saved.")
        return 130
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
