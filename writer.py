#!/usr/bin/env python3
"""
Research Swarm Writer Agent
===========================
Generates academic chapter sections from evidence packs using LLM synthesis.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional
from dataclasses import dataclass


# ============================================================================
# CONFIGURATION
# ============================================================================

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_MODEL = "qwen/qwen3-72B-instruct"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

SYSTEM_PROMPT = """You are an academic dissertation writer specializing in South Asian history and literature.
You write in formal academic prose.

CRITICAL RULES - VIOLATIONS WILL CAUSE CITATION AUDIT FAILURE:
1. Cite ONLY from the provided evidence pack - NEVER invent citations
2. Do NOT invent page numbers - use page numbers exactly as provided in the evidence
3. Do NOT cite sources not in the evidence pack
4. If a claim is not supported by evidence, write: "Further research is needed to..."
5. Write in scholarly third person
6. Maintain paragraph coherence
7. Include section headers (## for H2, ### for H3)
8. End with discussion questions or a transition

CITATION FORMAT (use structured format):
- Primary: [[chunk_id:page]] e.g., [[002_P001C003:1]]
- Fallback MLA: (AuthorName PageNumber) e.g., (Singh 85)
- Either format is acceptable - auditor validates both
"""


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class EvidenceChunk:
    """Represents a single evidence chunk from the retriever."""
    chunk_id: str
    source_filename: str
    page: int
    text: str

    @classmethod
    def from_dict(cls, data: dict) -> 'EvidenceChunk':
        return cls(
            chunk_id=data.get("chunk_id", ""),
            source_filename=data.get("source_filename", ""),
            page=data.get("page", 0),
            text=data.get("text", "")
        )


@dataclass
class EvidencePack:
    """Container for evidence pack data."""
    query: str
    chunks: list[EvidenceChunk]
    
    @classmethod
    def from_dict(cls, data: dict) -> 'EvidencePack':
        chunks = [EvidenceChunk.from_dict(c) for c in data.get("results", [])]
        return cls(
            query=data.get("query", ""),
            chunks=chunks
        )


# ============================================================================
# API CLIENT
# ============================================================================

class OpenRouterClient:
    """Client for interacting with OpenRouter API."""
    
    def __init__(self, api_key: str, model: str = OPENROUTER_MODEL):
        self.api_key = api_key
        self.model = model
        self.base_url = OPENROUTER_BASE_URL
    
    def generate(self, system_prompt: str, user_prompt: str, max_length: int = 4000) -> str:
        """Generate text using OpenRouter API."""
        import urllib.request
        import urllib.error
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "max_tokens": max_length,
            "temperature": 0.3,  # Lower temperature for academic precision
        }
        
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST"
        )
        
        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                result = json.loads(response.read().decode("utf-8"))
                return result["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")
            raise RuntimeError(f"OpenRouter API error {e.code}: {error_body}")


# ============================================================================
# CHUNK LOOKUP
# ============================================================================

class ChunkStore:
    """In-memory store for full chunk text lookup."""
    
    def __init__(self, chunks_path: Optional[Path] = None):
        self.chunks_path = chunks_path
        self._store: dict[str, str] = {}
        if chunks_path and chunks_path.exists():
            self._load_chunks()
    
    def _load_chunks(self):
        """Load chunks from chunks.json."""
        with open(self.chunks_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            for item in data.get("chunks", []):
                self._store[item["chunk_id"]] = item.get("text", "")
    
    def get(self, chunk_id: str) -> Optional[str]:
        """Get full text for a chunk ID."""
        return self._store.get(chunk_id)


# ============================================================================
# SLUG UTILITIES
# ============================================================================

def slugify(title: str) -> str:
    """Convert title to URL-safe slug."""
    # Remove chapter numbering if present
    title = re.sub(r'^(Chapter\s+\d+:?\s*|Section\s+\d+(\.\d+)*:?\s*)', '', title, flags=re.IGNORECASE)
    # Lowercase and replace spaces/special chars
    slug = title.lower()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'[\s]+', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    slug = slug.strip('-')
    return slug


# ============================================================================
# WRITING PROMPT BUILDER
# ============================================================================

def build_writing_prompt(topic: str, pack: EvidencePack, max_length: int, chunk_store: Optional[ChunkStore] = None) -> str:
    """Build the user prompt for the writer."""
    
    # Build evidence section
    evidence_lines = []
    evidence_dict = {}
    
    for i, chunk in enumerate(pack.chunks, 1):
        # Try to get full text from chunk store
        full_text = chunk.text
        if chunk_store:
            stored_text = chunk_store.get(chunk.chunk_id)
            if stored_text:
                full_text = stored_text
        
        evidence_lines.append(
            f"[EVIDENCE {i}]\n"
            f"Chunk ID: {chunk.chunk_id}\n"
            f"Source: {chunk.source_filename}, Page {chunk.page}\n"
            f"---\n"
            f"{full_text}\n"
        )
        evidence_dict[chunk.chunk_id] = chunk
    
    evidence_section = "\n\n".join(evidence_lines)
    
    # Count unique sources
    unique_sources = set(c.source_filename for c in pack.chunks)
    
    prompt = f"""TOPIC: {topic}

RESEARCH QUESTION: {pack.query if pack.query else 'Based on the provided evidence.'}

EVIDENCE PACK:
{evidence_section}

CRITICAL WRITING RULES:
- Write a scholarly chapter section on the topic using ONLY the evidence provided
- Each piece of evidence is labeled [EVIDENCE N]
- You may use each source multiple times when relevant, but always cite accurately
- NEVER fabricate citations - only sources in this evidence pack are available
- NEVER invent page numbers - use the page numbers exactly as shown in the evidence
- If you need to make a claim not supported by evidence, write: "Further research is needed to..."
- Write in formal academic prose (MLA style)
- Use section headers: ## for main sections, ### for subsections
- Cite sources as (AuthorName PageNumber) - example: (Singh 85)
- Include a brief transition or discussion questions at the end
- Target length: approximately {max_length} words
- Write from a detached scholarly perspective

OUTPUT FORMAT:
Provide ONLY the chapter section in Markdown format. Do not include your reasoning
or meta-commentary. Just write the section itself.
"""
    return prompt


# ============================================================================
# OUTPUT PROCESSING
# ============================================================================

def process_output(text: str, pack: EvidencePack) -> str:
    """Post-process the generated text."""
    
    # Count evidence used
    unique_sources = len(set(c.source_filename for c in pack.chunks))
    
    # Add evidence footer if not already present
    if "*Evidence used:" not in text:
        text += f"\n\n---\n*Evidence used: {len(pack.chunks)} chunks from {unique_sources} sources*\n"
    
    return text.strip()


# ============================================================================
# MAIN WRITER CLASS
# ============================================================================

class Writer:
    """Main Writer agent for generating chapter sections."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or OPENROUTER_API_KEY
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY environment variable not set")
        self.client = OpenRouterClient(self.api_key)
    
    def write(
        self,
        topic: str,
        evidence_pack: EvidencePack,
        max_length: int = 4000,
        chunk_store: Optional[ChunkStore] = None
    ) -> str:
        """Generate a chapter section from the evidence pack."""
        
        # Build prompt
        prompt = build_writing_prompt(topic, evidence_pack, max_length, chunk_store)
        
        # Generate
        output = self.client.generate(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=prompt,
            max_length=max_length
        )
        
        # Post-process
        return process_output(output, evidence_pack)
    
    def write_to_file(
        self,
        topic: str,
        evidence_pack: EvidencePack,
        output_path: Path,
        max_length: int = 4000,
        chunk_store: Optional[ChunkStore] = None
    ) -> str:
        """Generate and save chapter section to file."""
        
        content = self.write(topic, evidence_pack, max_length, chunk_store)
        
        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Save
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
        
        return content


# ============================================================================
# CLI INTERFACE
# ============================================================================

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
	    description="Research Swarm Writer Agent - Generate academic chapter sections",
	    formatter_class=argparse.RawDescriptionHelpFormatter,
	    epilog="""
Examples:
  python3 writer.py --topic "Partition and Violence in 1947"
  python3 writer.py --topic "Chapter 3: Train to Pakistan" --evidence evidence_packs/partition.json
  python3 writer.py --topic "Khushwant Singh as Historian" --max-length 2000
  cat evidence_packs/partition.json | python3 writer.py --topic "Partition Violence"
	    """
    )
    
    parser.add_argument(
        "--topic", "-t",
        required=False,
        help="Chapter title or topic to write about"
    )
    
    parser.add_argument(
        "--evidence", "-e",
        type=Path,
        help="Path to evidence pack JSON file (default: read from stdin)"
    )
    
    parser.add_argument(
        "--output", "-o",
        type=Path,
        help="Output path for chapter file (default: output/chapters/{slug}.md)"
    )
    
    parser.add_argument(
        "--chunks",
        type=Path,
        default=Path("chunks/chunks.json"),
        help="Path to chunks.json for full text lookup"
    )
    
    parser.add_argument(
        "--max-length",
        type=int,
        default=4000,
        help="Maximum token length for generation"
    )
    
    parser.add_argument(
        "--api-key",
        help="OpenRouter API key (default: from OPENROUTER_API_KEY env)"
    )
    
    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()
    
    # Load evidence pack
    if args.evidence:
        with open(args.evidence, "r", encoding="utf-8") as f:
            pack_data = json.load(f)
    else:
        # Read from stdin
        pack_data = json.load(sys.stdin)
    
    pack = EvidencePack.from_dict(pack_data)
    
    # Get topic
    topic = args.topic
    if not topic:
        # Try to get from evidence pack query
        topic = pack.query
        if not topic:
            print("Error: --topic is required when no query in evidence pack", file=sys.stderr)
            sys.exit(1)
    
    # Initialize chunk store
    chunk_store = None
    if args.chunks.exists():
        chunk_store = ChunkStore(args.chunks)
    
    # Initialize writer
    writer = Writer(api_key=args.api_key)
    
    # Determine output path
    output_path = args.output
    if not output_path:
        slug = slugify(topic)
        output_path = Path("output/chapters") / f"{slug}.md"
    
    # Generate and save
    print(f"Writing chapter section: {topic}", file=sys.stderr)
    print(f"Evidence: {len(pack.chunks)} chunks", file=sys.stderr)
    print(f"Output: {output_path}", file=sys.stderr)
    
    content = writer.write_to_file(
        topic=topic,
        evidence_pack=pack,
        output_path=output_path,
        max_length=args.max_length,
        chunk_store=chunk_store
    )
    
    # Print to stdout
    print(content)


if __name__ == "__main__":
    main()
