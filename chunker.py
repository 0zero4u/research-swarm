#!/usr/bin/env python3
"""
Chunker Agent - Text chunking with provenance tracking.

Reads text from corpus/*.txt and outputs chunks.json with metadata.
"""

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


@dataclass
class Chunk:
    """Represents a single text chunk with provenance."""
    chunk_id: str
    source_id: str
    source_filename: str
    page: int
    text: str
    token_count: int


@dataclass
class ChunkOutput:
    """Output structure containing all chunks."""
    chunks: list = field(default_factory=list)


class Chunker:
    """Processes text documents into chunks with provenance."""
    
    SOFT_MAX_TOKENS = 500
    WORDS_PER_PAGE = 500  # When no page markers found
    MIN_CHUNK_CHARS = 50
    TOKEN_MULTIPLIER = 1.3
    
    # Page marker patterns
    PAGE_PATTERNS = [
        r'-{3}\s*Page\s+(\d+)\s*-{3}',  # --- Page 4 ---
        r'\[Page\s+(\d+)\]',            # [Page 4]
        r'Page\s+(\d+)[:\.]',           # Page 4: or Page 4.
        r'\f(\d+)\f',                   # Form feed with page number
    ]
    
    def __init__(self, corpus_dir: str = "corpus", output_dir: str = "chunks"):
        self.corpus_dir = Path(corpus_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # State for resume functionality
        self.state_file = self.output_dir / ".chunker_state.json"
        self.processed_sources = self._load_state()
    
    def _load_state(self) -> set:
        """Load processed sources from state file."""
        if self.state_file.exists():
            try:
                state = json.loads(self.state_file.read_text())
                return set(state.get("processed_sources", []))
            except (json.JSONDecodeError, IOError):
                pass
        return set()
    
    def _save_state(self, source_id: str):
        """Save progress to state file."""
        self.processed_sources.add(source_id)
        self.state_file.write_text(json.dumps({
            "processed_sources": list(self.processed_sources),
            "last_processed": source_id
        }))
    
    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count from text."""
        return int(len(text.split()) * self.TOKEN_MULTIPLIER)
    
    def _extract_pages(self, text: str) -> list[tuple[int, str]]:
        """Split text by page markers."""
        pages = []
        current_page = 1
        current_content = []
        
        # Split by page markers
        page_split_regex = '|'.join(self.PAGE_PATTERNS)
        segments = re.split(f'({page_split_regex})', text)
        
        for i, segment in enumerate(segments):
            # Skip None segments (can occur with re.split)
            if segment is None:
                continue
            
            # Check if this segment is a page marker
            matched = False
            for pattern in self.PAGE_PATTERNS:
                match = re.search(pattern, segment)
                if match:
                    # Save current page content
                    if current_content:
                        pages.append((current_page, ''.join(current_content)))
                        current_content = []
                    
                    current_page = int(match.group(1))
                    matched = True
                    break
            
            if not matched:
                current_content.append(segment)
        
        # Don't forget the last page
        if current_content:
            pages.append((current_page, ''.join(current_content)))
        
        # If no pages found, create synthetic pages
        if len(pages) == 0:
            words = text.split()
            if len(words) <= self.WORDS_PER_PAGE:
                pages = [(1, text)]
            else:
                # Split into pages of WORDS_PER_PAGE
                for i in range(0, len(words), self.WORDS_PER_PAGE):
                    page_words = words[i:i + self.WORDS_PER_PAGE]
                    page_num = (i // self.WORDS_PER_PAGE) + 1
                    pages.append((page_num, ' '.join(page_words)))
        
        return pages
    
    def _split_into_chunks(self, text: str, max_tokens: int = None) -> list[str]:
        """Split text into chunks, respecting sentence and paragraph boundaries."""
        if max_tokens is None:
            max_tokens = self.SOFT_MAX_TOKENS
        
        chunks = []
        
        # Split into paragraphs first (preserve structure)
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = []
        current_tokens = 0
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            
            para_tokens = self._estimate_tokens(para)
            
            # If single paragraph exceeds limit, split by sentences
            if para_tokens > max_tokens and current_chunk:
                # Save current chunk
                if current_chunk:
                    chunks.append('\n'.join(current_chunk))
                    current_chunk = []
                    current_tokens = 0
            
            if para_tokens > max_tokens:
                # Split by sentences
                sentences = re.split(r'(?<=[.!?])\s+', para)
                for sentence in sentences:
                    sentence = sentence.strip()
                    if not sentence:
                        continue
                    
                    sentence_tokens = self._estimate_tokens(sentence)
                    
                    if current_tokens + sentence_tokens > max_tokens and current_chunk:
                        chunks.append('\n'.join(current_chunk))
                        current_chunk = []
                        current_tokens = 0
                    
                    current_chunk.append(sentence)
                    current_tokens += sentence_tokens
            else:
                if current_tokens + para_tokens > max_tokens and current_chunk:
                    chunks.append('\n'.join(current_chunk))
                    current_chunk = []
                    current_tokens = 0
                
                current_chunk.append(para)
                current_tokens += para_tokens
        
        # Don't forget the last chunk
        if current_chunk:
            chunks.append('\n'.join(current_chunk))
        
        return [c.strip() for c in chunks if len(c.strip()) >= self.MIN_CHUNK_CHARS]
    
    def _extract_source_id(self, filename: str) -> str:
        """Extract source ID from filename (e.g., '001_file.txt' -> '001')."""
        name = Path(filename).stem
        # Extract leading numeric prefix
        match = re.match(r'^(\d+)', name)
        if match:
            return match.group(1)
        return name
    
    def process_file(self, filepath: Path) -> list[Chunk]:
        """Process a single file into chunks."""
        source_id = self._extract_source_id(filepath.name)
        
        # Skip if already processed (for resume)
        if source_id in self.processed_sources:
            print(f"  Skipping {filepath.name} (already processed)")
            return []
        
        print(f"  Processing {filepath.name}...")
        text = filepath.read_text(encoding='utf-8')
        
        # Extract pages
        pages = self._extract_pages(text)
        
        chunks = []
        chunk_counter = 1
        
        for page_num, page_text in pages:
            # Clean up page text
            page_text = page_text.strip()
            
            # Skip empty pages
            if len(page_text.strip()) < self.MIN_CHUNK_CHARS:
                continue
            
            # Split page into chunks
            page_chunks = self._split_into_chunks(page_text)
            
            for chunk_text in page_chunks:
                # Final validation
                if len(chunk_text.strip()) < self.MIN_CHUNK_CHARS:
                    continue
                
                chunk_id = f"{source_id}_P{page_num:03d}C{chunk_counter:03d}"
                
                chunk = Chunk(
                    chunk_id=chunk_id,
                    source_id=source_id,
                    source_filename=filepath.name,
                    page=page_num,
                    text=chunk_text,
                    token_count=self._estimate_tokens(chunk_text)
                )
                
                chunks.append(chunk)
                chunk_counter += 1
        
        # Save progress
        self._save_state(source_id)
        
        return chunks
    
    def process_corpus(self, source_filter: Optional[str] = None) -> list[Chunk]:
        """Process all files in corpus directory."""
        all_chunks = []
        
        if not self.corpus_dir.exists():
            print(f"Error: Corpus directory '{self.corpus_dir}' does not exist")
            return all_chunks
        
        # Find all txt files
        txt_files = sorted(self.corpus_dir.glob("*.txt"))
        
        if not txt_files:
            print(f"Warning: No .txt files found in {self.corpus_dir}")
            return all_chunks
        
        # Filter by source if specified
        if source_filter:
            txt_files = [f for f in txt_files if self._extract_source_id(f.name) == source_filter]
            if not txt_files:
                print(f"Error: No files found for source '{source_filter}'")
                return all_chunks
        
        print(f"Found {len(txt_files)} file(s) to process")
        
        for filepath in txt_files:
            chunks = self.process_file(filepath)
            all_chunks.extend(chunks)
            print(f"  -> Generated {len(chunks)} chunk(s)")
        
        return all_chunks
    
    def write_output(self, chunks: list[Chunk], output_file: str = "chunks.json"):
        """Write chunks to output file."""
        output_path = self.output_dir / output_file
        
        output_data = {"chunks": [asdict(c) for c in chunks]}
        
        output_path.write_text(
            json.dumps(output_data, indent=2, ensure_ascii=False),
            encoding='utf-8'
        )
        
        print(f"\nWrote {len(chunks)} chunks to {output_path}")
        
        # Summary stats
        total_tokens = sum(c.token_count for c in chunks)
        sources = set(c.source_id for c in chunks)
        print(f"Summary: {len(sources)} source(s), {total_tokens} total tokens (est.)")
        
        # Clean up state file on success
        if self.state_file.exists():
            self.state_file.unlink()


def main():
    parser = argparse.ArgumentParser(
        description="Chunk text documents with provenance tracking"
    )
    parser.add_argument(
        "--source",
        help="Process specific source only (e.g., '001')"
    )
    parser.add_argument(
        "--corpus",
        default="corpus",
        help="Input corpus directory (default: corpus)"
    )
    parser.add_argument(
        "--output-dir",
        default="chunks",
        help="Output directory (default: chunks)"
    )
    parser.add_argument(
        "--output-file",
        default="chunks.json",
        help="Output filename (default: chunks.json)"
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume interrupted job (skip processed sources)"
    )
    
    args = parser.parse_args()
    
    chunker = Chunker(
        corpus_dir=args.corpus,
        output_dir=args.output_dir
    )
    
    chunks = chunker.process_corpus(source_filter=args.source)
    
    if chunks:
        chunker.write_output(chunks, args.output_file)
    else:
        print("No chunks generated.")
        sys.exit(1)


if __name__ == "__main__":
    main()