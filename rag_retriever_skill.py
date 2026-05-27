#!/usr/bin/env python3
"""
RAG Retriever Skill - Structured evidence block retriever for academic writing.

Wraps the FAISS retriever and outputs structured evidence blocks with:
- block_id: [B_XXX] citation reference
- chunk_id: source identifier
- source: author year
- page: page number
- text: evidence text
- score: relevance score
- claims: what this block supports

Usage:
    python3 rag_retriever_skill.py "ghost train symbolism partition violence"
    python3 rag_retriever_skill.py "railroad symbolism mano majra" --top-k 5
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent))

from retriever import Retriever, RetrieverConfig, EvidenceResult


# Constants
DEFAULT_TOP_K = 5
DEFAULT_MIN_CONFIDENCE = 0.30  # Lowered for new multi-source corpus
DEFAULT_CHUNKS_PATH = Path("chunks/chunks.json")
DEFAULT_INDEX_DIR = Path("vector_index")
DEFAULT_EVIDENCE_DIR = Path("evidence_packs")


def _slugify_query(query: str) -> str:
    """Convert query string to safe filename slug."""
    # Lowercase, replace spaces with underscores, remove special chars
    slug = re.sub(r'[^a-z0-9]+', '_', query.lower()).strip('_')
    # Truncate to 60 chars to avoid long filenames
    return slug[:60]


def _get_evidence_pack_path(query: str) -> Path:
    """Get the path for the evidence pack corresponding to a query."""
    slug = _slugify_query(query)
    return DEFAULT_EVIDENCE_DIR / f"{slug}.json"


def format_author(author_str: str) -> str:
    """Extract last name from full author string for citations."""
    if not author_str:
        return "Unknown"
    
    # Handle "Shikha G. Mohana Charyulu" -> "Charyulu"
    # Handle "Smith, John" -> "Smith"
    parts = author_str.strip().split()
    
    # Check for "et al."
    if "et al." in author_str.lower():
        return parts[0].split(",")[0].strip() if "," in parts[0] else parts[0]
    
    # Split on " and " first
    if " and " in author_str:
        first_part = author_str.split(" and ")[0].strip()
        if "," in first_part:
            return first_part.split(",")[0].strip().split()[-1]
        return first_part.split()[-1]
    
    return parts[-1] if parts else "Unknown"


def extract_claims_from_text(text: str, chunk_id: str) -> list[str]:
    """Extract key claims/keywords from chunk text for evidence mapping."""
    # Simple heuristic: extract first 3-5 key topics from text
    claims = []
    
    # Normalize text for searching
    text_lower = text.lower()
    
    # Key claim patterns to look for
    claim_patterns = [
        ("railroad as central symbol", ["rail route", "railroad", "railway", "train symbol"]),
        ("Mano Majra intersection", ["mano majra"]),
        ("trains with grievous cargoes of death", ["grievous cargoes", "death", "ghost trains"]),
        ("partition violence 1947", ["partition", "1947"]),
        ("communal violence", ["communal violence", "riots"]),
        ("Sikh vs Muslim conflict", ["sikh", "muslim"]),
        ("Kalyug metaphor", ["kalyug"]),
        ("Juggut sacrifice", ["juggut", "sacrifice"]),
        ("Iqbal pessimism", ["iqbal", "pessimism"]),
        ("Hukum Chand officialdom", ["hukum", "officialdom"]),
        ("gender oppression women", ["women", "rape", "acid"]),
        ("feminist perspective", ["feminist", "gender"]),
        ("comparative study", ["comparative"]),
    ]
    
    for claim, patterns in claim_patterns:
        for pattern in patterns:
            if pattern in text_lower:
                if claim not in claims:
                    claims.append(claim)
                    break
    
    # Always include at least the chunk_id as a reference
    if not claims:
        claims.append(f"source: {chunk_id}")
    
    return claims[:5]  # Limit to 5 claims per block


def load_chunks_metadata(chunks_path: Path) -> dict:
    """Load chunks.json and build chunk_id -> metadata mapping."""
    with open(chunks_path) as f:
        data = json.load(f)
    items = data if isinstance(data, list) else data.get("chunks", [])
    return {c["chunk_id"]: c for c in items}


def build_structured_blocks(results: list[EvidenceResult], top_k: int, chunks_meta: dict) -> dict:
    """Convert retriever results to structured evidence blocks."""
    blocks = []
    
    for i, result in enumerate(results, start=1):
        block_id = f"B_{i:03d}"
        
        # Look up full chunk metadata
        chunk_meta = chunks_meta.get(result.chunk_id, {})
        author = format_author(chunk_meta.get("author", result.source_id))
        year = chunk_meta.get("year", "")
        
        source = f"{author} {year}".strip() if year else author
        if source in ("Unknown", ""):
            source = result.source_filename.split("_")[0] if result.source_filename else "Unknown"
        
        # Extract claims from text
        claims = extract_claims_from_text(result.text, result.chunk_id)
        
        # Truncate text if too long (for readability)
        text = result.text.strip()
        if len(text) > 500:
            # Try to find a sentence boundary
            cutoff = text[:500]
            last_period = cutoff.rfind('.')
            if last_period > 300:
                text = cutoff[:last_period + 1]
            else:
                text = cutoff + "..."
        
        block = {
            "block_id": block_id,
            "chunk_id": result.chunk_id,
            "source": source,
            "source_filename": result.source_filename,
            "page": result.page,
            "text": text,
            "score": round(result.score, 4),
            "claims": claims
        }
        blocks.append(block)
    
    return blocks


def save_evidence_pack(query: str, blocks: list[dict], top_k: int) -> Path:
    """Save structured evidence blocks as a JSON evidence pack.

    Args:
        query: The search query
        blocks: List of structured block dicts with block_id, chunk_id, source, page, text, etc.
        top_k: Number of results requested

    Returns:
        Path to the saved file.
    """
    DEFAULT_EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    pack_path = _get_evidence_pack_path(query)

    pack_data = {
        "query": query,
        "top_k": top_k,
        "blocks": blocks,
        "total_retrieved": len(blocks),
        "timestamp": datetime.now().isoformat(),
    }

    with open(pack_path, "w", encoding="utf-8") as f:
        json.dump(pack_data, f, indent=2, ensure_ascii=False)

    return pack_path


def load_evidence_pack(query: str) -> Optional[dict]:
    """Load an evidence pack for a query if it exists.
    
    Returns the pack dict or None if not found.
    """
    pack_path = _get_evidence_pack_path(query)
    if not pack_path.exists():
        return None
    with open(pack_path, "r", encoding="utf-8") as f:
        return json.load(f)


def retrieve_evidence(
    query: str,
    top_k: int = DEFAULT_TOP_K,
    index_dir: Path = DEFAULT_INDEX_DIR,
    chunks_path: Path = DEFAULT_CHUNKS_PATH,
    api_key: Optional[str] = None,
    min_confidence: float = 0.30,
    save_pack: bool = True
) -> dict:
    """
    Main retrieval function: query FAISS and return structured evidence blocks.
    
    Returns:
        dict with:
            - query: the search query
            - blocks: list of evidence blocks with [B_XXX] IDs
            - total_retrieved: number of blocks returned
            - prompt: instructions for citing blocks
    """
    # Build config (don't save evidence pack by default from skill)
    config = RetrieverConfig(
        query=query,
        top_k=top_k,
        index_dir=index_dir,
        chunks_path=chunks_path,
        api_key=api_key,
        save_evidence=save_pack,
        min_confidence=min_confidence
    )
    
    try:
        # Initialize retriever
        retriever = Retriever(config)
        
        # Load FAISS index
        retriever.load_index()
        retriever.load_manifest()
        retriever.load_chunks_index()
        
        # Query
        evidence = retriever.retrieve(query, top_k)
        
        # Filter by confidence
        filtered_results = [r for r in evidence.results if r.score >= min_confidence]
        evidence.results = filtered_results
        
        # Build structured blocks
        chunks_meta = load_chunks_metadata(config.chunks_path)
        blocks = build_structured_blocks(evidence.results, top_k, chunks_meta)
        
        if save_pack:
            save_evidence_pack(query, blocks, top_k)
        
        return {
            "query": query,
            "blocks": blocks,
            "total_retrieved": len(blocks),
            "prompt": "Use block IDs like [B_001] in your citations. Each block supports specific claims listed above."
        }
        
    except Exception as e:
        return {
            "query": query,
            "blocks": [],
            "total_retrieved": 0,
            "error": str(e),
            "prompt": "Use block IDs like [B_001] in your citations."
        }


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="RAG Retriever Skill - Structured evidence blocks for academic writing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 rag_retriever_skill.py "ghost train symbolism partition violence"
  python3 rag_retriever_skill.py "railroad symbolism mano majra" --top-k 5
  python3 rag_retriever_skill.py "communal violence 1947" --min-confidence 0.65
        """
    )
    
    parser.add_argument(
        "query",
        nargs="+",
        help="Search query (multiple words/phrases)"
    )
    parser.add_argument(
        "-k", "--top-k",
        type=int,
        default=DEFAULT_TOP_K,
        help=f"Number of results to return (default: {DEFAULT_TOP_K})"
    )
    parser.add_argument(
        "--index-dir",
        type=Path,
        default=DEFAULT_INDEX_DIR,
        help=f"Directory containing FAISS index (default: {DEFAULT_INDEX_DIR})"
    )
    parser.add_argument(
        "--chunks",
        type=Path,
        default=DEFAULT_CHUNKS_PATH,
        help=f"Path to chunks.json (default: {DEFAULT_CHUNKS_PATH})"
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="OpenRouter API key (or set OPENROUTER_API_KEY env var)"
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.30,
        help="Minimum similarity score threshold (default: 0.30)"
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Save evidence pack to file"
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        default=True,
        help="Pretty-print JSON output (default: True)"
    )
    
    args = parser.parse_args()
    
    # Join query words
    query = " ".join(args.query)
    
    # Retrieve
    result = retrieve_evidence(
        query=query,
        top_k=args.top_k,
        index_dir=args.index_dir,
        chunks_path=args.chunks,
        api_key=args.api_key,
        min_confidence=args.min_confidence,
        save_pack=args.save
    )
    
    # Output JSON
    if args.pretty:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(result, ensure_ascii=False))
    
    # Exit code based on results
    if "error" in result:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
