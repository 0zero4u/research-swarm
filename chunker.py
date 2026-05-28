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

import requests


@dataclass
class Chunk:
    """Represents a single text chunk with provenance and metadata."""
    chunk_id: str
    source_id: str
    source_filename: str
    author: str
    title: str
    year: str
    journal: str
    volume: str
    issue: str
    url: str
    page: int
    text: str
    token_count: int


@dataclass
class ChunkOutput:
    """Output structure containing all chunks."""
    chunks: list = field(default_factory=list)


class LLMMetadataExtractor:
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
    OPENROUTER_MODEL = "deepseek/deepseek-v4-flash"
    OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

    @classmethod
    def extract(cls, text: str, source_filename: str) -> dict:
        if not cls.OPENROUTER_API_KEY:
            return {}

        first_page = text[:2000].strip()
        if len(first_page) < 200:
            return {}

        prompt = f"""Extract bibliographic metadata from this academic document header.
Return ONLY a JSON object with these exact keys: author, title, year, journal, url.
If any field is unknown, use empty string "".

Document text:
---
{first_page}
---

Rules:
- author: Full name(s) as they appear, cleaned (no "Dr.", "Prof.", superscripts). Multiple authors separated by " and ".
- title: The article/paper title exactly as printed, NOT the journal name.
- year: 4-digit year only.
- journal: The journal or publisher name, NOT the article title.
- url: DOI or URL if present, else empty string.

Output JSON only, no explanation."""

        try:
            response = requests.post(
                f"{cls.OPENROUTER_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {cls.OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://research-swarm.local",
                },
                json={
                    "model": cls.OPENROUTER_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 500,
                    "temperature": 0.1,
                },
                timeout=30
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]

            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                metadata = json.loads(json_match.group(0))
                return {
                    "author": metadata.get("author", "").strip(),
                    "title": metadata.get("title", "").strip(),
                    "year": metadata.get("year", "").strip(),
                    "journal": metadata.get("journal", "").strip(),
                    "url": metadata.get("url", "").strip(),
                }
        except Exception as e:
            print(f"  LLM metadata extraction failed for {source_filename}: {e}", file=sys.stderr)

        return {}


class Chunker:
    """Processes text documents into chunks with provenance."""
    
    SOFT_MAX_TOKENS = 15000
    TOKEN_MULTIPLIER = 1.0  # ~1 token per word for English prose
    MIN_CHUNK_WORDS = 150  # Minimum words per chunk (no char-based minimum)
    MIN_CHUNK_CHARS = 50   # Minimum characters per chunk
    
    # Page marker patterns
    PAGE_PATTERNS = [
        r'-{3}\s*Page\s+(\d+)\s*-{3}',  # --- Page 4 ---
        r'\[Page\s+(\d+)\]',            # [Page 4]
        r'Page\s+(\d+)[:\.]',           # Page 4: or Page 4.
        r'\f(\d+)\f',                   # Form feed with page number
    ]
    
    def __init__(self, corpus_dir: str = None, output_dir: str = None):
        _base = Path(__file__).parent
        self.corpus_dir = Path(corpus_dir) if corpus_dir else _base / "corpus"
        self.output_dir = Path(output_dir) if output_dir else _base / "chunks"
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
        """Split text by page markers to extract page numbers.

        Returns list of (page_num, page_content) tuples.
        If no page markers found, returns single page with full text.
        Does NOT artificially split by word count (paragraph-level splitting
        happens later in _split_into_chunks).
        """
        pages = []
        current_page = 1
        current_content = []

        # Split by page markers
        page_split_regex = '|'.join(self.PAGE_PATTERNS)
        segments = re.split(f'({page_split_regex})', text)

        for i, segment in enumerate(segments):
            if segment is None:
                continue

            # Check if this segment is a page marker
            matched = False
            for pattern in self.PAGE_PATTERNS:
                match = re.search(pattern, segment)
                if match:
                    if current_content:
                        pages.append((current_page, ''.join(current_content)))
                        current_content = []

                    current_page = int(match.group(1))
                    matched = True
                    break

            if not matched:
                current_content.append(segment)

        if current_content:
            pages.append((current_page, ''.join(current_content)))

        # If no pages found, treat entire text as one page (splitting happens later)
        if len(pages) == 0:
            pages = [(1, text)]

        return pages
    
    def _split_into_chunks(self, text: str, max_tokens: int = None) -> list[str]:
        """Split text into chunks bottom-up by paragraphs, merge undersized chunks."""
        if max_tokens is None:
            max_tokens = self.SOFT_MAX_TOKENS

        HARD_MAX_WORDS = 1350  # Flush chunk after accumulating this many words

        chunks = []
        paragraphs = re.split(r'\n\s*\n', text)

        current_chunk = []
        current_word_count = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            para_words = len(para.split())
            para_tokens = int(para_words * self.TOKEN_MULTIPLIER)

            if para_tokens > max_tokens or para_words > HARD_MAX_WORDS:
                if current_chunk:
                    chunks.append('\n'.join(current_chunk))
                    current_chunk = []
                    current_word_count = 0

                sentences = re.split(r'(?<=[.!?])\s+', para)
                sub_chunk = []
                sub_word_count = 0
                for sent in sentences:
                    sent = sent.strip()
                    if not sent:
                        continue
                    sent_words = len(sent.split())
                    if sub_word_count > 0 and (sub_word_count + sent_words) * self.TOKEN_MULTIPLIER > max_tokens:
                        chunks.append(' '.join(sub_chunk))
                        sub_chunk = []
                        sub_word_count = 0
                    sub_chunk.append(sent)
                    sub_word_count += sent_words
                if sub_chunk:
                    chunks.append(' '.join(sub_chunk))
            else:
                flush = current_word_count > 0 and (
                    current_word_count >= HARD_MAX_WORDS
                    or current_word_count + para_words > HARD_MAX_WORDS
                    or (current_word_count + para_words) * self.TOKEN_MULTIPLIER > max_tokens
                )
                if flush:
                    chunks.append('\n'.join(current_chunk))
                    current_chunk = []
                    current_word_count = 0

                current_chunk.append(para)
                current_word_count += para_words

        if current_chunk:
            chunks.append('\n'.join(current_chunk))

        merged = []
        i = 0
        n = len(chunks)

        while i < n:
            chunk_text = chunks[i]
            chunk_words = len(chunk_text.split())

            if chunk_words < self.MIN_CHUNK_WORDS:
                if merged:
                    merged[-1] = merged[-1] + '\n\n' + chunk_text
                    merged_word_count = len(merged[-1].split())
                    j = i + 1
                    while merged_word_count < self.MIN_CHUNK_WORDS and j < n:
                        merged[-1] = merged[-1] + '\n\n' + chunks[j]
                        merged_word_count = len(merged[-1].split())
                        j += 1
                    i = j
                else:
                    j = i + 1
                    while j < n and len(chunks[j].split()) < self.MIN_CHUNK_WORDS:
                        j += 1
                    if j < n:
                        merged.append(chunk_text + '\n\n' + chunks[j])
                        i = j + 1
                    else:
                        merged.append(chunk_text)
                        i = j
            else:
                merged.append(chunk_text)
                i += 1

        return merged
    
    def _extract_source_id(self, filename: str) -> str:
        """Extract source ID from filename (e.g., '001_file.txt' -> '001')."""
        name = Path(filename).stem
        # Extract leading numeric prefix
        match = re.match(r'^(\d+)', name)
        if match:
            return match.group(1)
        return name
    
    @staticmethod
    def _is_likely_not_title(line: str) -> bool:
        low = line.lower()
        bad_prefixes = [
            'international open-access', 'an international peer reviewed',
            'an interdisciplinary academic', 'impact factor',
            'double-blind, peer-reviewed', 'refereed, multidisciplinary',
            'vol.', 'volume', 'issue ', 'issn', 'doi.',
        ]
        for p in bad_prefixes:
            if low.startswith(p) or (p + ' ' in low and len(line) < 120):
                return True
        return False

    @staticmethod
    def _clean_author(author: str) -> str:
        """Remove academic title prefixes from author string."""
        cleaned = re.sub(r'\b(Dr\.|Prof\.|Mr\.|Ms\.|Mrs\.|Er\.)\s+', '', author)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        cleaned = re.sub(r'[.;,]+$', '', cleaned)
        return cleaned

    def _extract_metadata(self, text: str, source_filename: str) -> dict:
        metadata = {
            "author": "",
            "title": "",
            "year": "",
            "journal": "",
            "volume": "",
            "issue": "",
            "url": ""
        }

        # 1. URL — doi.org, https?://, then bare www.* domains
        url = ""
        doi_match = re.search(r'(doi\.org/[^\s)>\]]+)', text)
        if doi_match:
            url = f"https://{doi_match.group(1)}"
        else:
            http_match = re.search(r'(https?://[^\s)>\]]+)', text)
            if http_match:
                url = http_match.group(1)
            else:
                www_match = re.search(r'(www\.[^\s)>\]]{4,})', text, re.IGNORECASE)
                if www_match:
                    url = f"http://{www_match.group(1)}"
        metadata["url"] = url

        # 2. Year — 4-digit year between 1900-2099
        year_match = re.search(r'\b(19\d{2}|20\d{2})\b', text)
        if year_match:
            metadata["year"] = year_match.group(1)

        # 2b. Volume and Issue — common patterns in academic headers
        vol_match = re.search(r'Volume\s+(\d+)[,\s]+Issue\s+(\d+)', text, re.IGNORECASE)
        if vol_match:
            metadata["volume"] = vol_match.group(1)
            metadata["issue"] = vol_match.group(2)
        else:
            vol_match2 = re.search(r'Vol\.?\s*(\d+)[,\s]+No\.?\s*(\d+)', text, re.IGNORECASE)
            if vol_match2:
                metadata["volume"] = vol_match2.group(1)
                metadata["issue"] = vol_match2.group(2)
            else:
                vol_match3 = re.search(r'Vol\.?\s*(\d+)', text, re.IGNORECASE)
                if vol_match3:
                    metadata["volume"] = vol_match3.group(1)

        # 3. Labeled patterns (most reliable)
        labeled_patterns = [
            (r'(?:Author|Authors?)\s*[:;]\s*(.+?)(?:\n|\.\s|$)', "author"),
            (r'(?:Title)\s*[:;]\s*(.+?)(?:\n|\.\s|$)', "title"),
            (r'(?:Journal|Publisher)\s*[:;]\s*(.+?)(?:\n|\.\s|$)', "journal"),
        ]
        for pattern, key in labeled_patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                val = match.group(1).strip().rstrip('.')
                if val:
                    metadata[key] = val

        lines = text.strip().split('\n')

        # 4. Heuristic: author names in early lines
        if not metadata["author"]:
            title_honorific = re.compile(r'\b(Dr\.|Prof\.|Mr\.|Ms\.|Mrs\.)\s', re.IGNORECASE)
            for line in lines[:10]:
                line = line.strip()
                if not line:
                    continue
                # Strong signal: "Dr." or "Prof." in the line
                if title_honorific.search(line):
                    cleaned = re.sub(r'([A-Za-z]+)[\d\*]+', r'\1', line)
                    metadata["author"] = self._clean_author(cleaned)
                    break
                # Look for "Name1 Surname1* Name2 Surname2" with superscripts
                if re.search(r'[A-Z][a-z]+[\d\*]+\s+[A-Z][a-z]+[\d\*]+', line):
                    cleaned = re.sub(r'([A-Za-z]+)[\d\*]+', r'\1', line)
                    metadata["author"] = self._clean_author(cleaned)
                    break

        # 5. Heuristic: title from first substantial line
        if not metadata["title"]:
            skip_re = re.compile(
                r'(?:\b(?:Abstract|Keywords|ISSN|DOI|Vol\.|No\.|Introduction|'
                r'Conclusion|References|Bibliography|Research\s+Scholar|'
                r'Associate\s+Professor|University|College|Institute|Department|'
                r'Corresponding\s+Author|Page)\b|'
                r'\b(?:Dr\.|Prof\.)(?:\s+[A-Z]\.?)?)',
                re.IGNORECASE
            )
            title_candidates = []
            for line in lines:
                line = line.strip()
                if not line or len(line) < 20:
                    continue
                if re.search(r'https?://|www\.', line, re.IGNORECASE):
                    continue
                if re.search(r'^-{3,}', line):
                    continue
                if re.search(r'^\d+\s*$', line):
                    continue
                if skip_re.search(line):
                    continue
                # Skip lines starting with journal-like words
                if re.search(r'^Journal\s+of|^International\s+Journal|^Proceedings\s+of', line, re.IGNORECASE):
                    continue
                if self._is_likely_not_title(line):
                    continue
                if line[0].isupper():
                    title_candidates.append(line.rstrip('.;,:').rstrip())

            # Accept first candidate; validate it doesn't look like a periodical marker
            for candidate in title_candidates:
                # Real article titles tend to be longer (>30 chars) and describe content
                if len(candidate) >= 30 and not any(
                    kw in candidate.lower() for kw in ['refereed journal', 'international journal', 'academic journal', 'peer reviewed']
                ):
                    metadata["title"] = candidate
                    break
                # Even shorter lines can be titles if they contain specific content keywords
                elif any(kw in candidate.lower() for kw in ['train to pakistan', 'partition', 'khushwant singh', 'a bend in the']):
                    metadata["title"] = candidate
                    break

        # 6. Heuristic: journal name
        if not metadata["journal"]:
            journal_match = re.search(r'(Journal\s+of\s+[A-Z][^.\n]{5,80})', text)
            if journal_match:
                metadata["journal"] = journal_match.group(1).strip()
            else:
                pub_match = re.search(
                    r'(?:Publisher|Published by|Press|Publishing)\s*[:;]?\s*([A-Z][^.\n]{5,80})',
                    text
                )
                if pub_match:
                    metadata["journal"] = pub_match.group(1).strip().rstrip('.')

        author_weak = not metadata["author"] or len(metadata["author"]) < 3
        title_weak = not metadata["title"] or any(
            kw in metadata["title"].lower() for kw in ['journal', 'refereed', 'peer-reviewed', 'international']
        )
        if author_weak or title_weak:
            llm_meta = LLMMetadataExtractor.extract(text, source_filename)
            if llm_meta.get("author"):
                metadata["author"] = llm_meta["author"]
            if llm_meta.get("title"):
                metadata["title"] = llm_meta["title"]
            if llm_meta.get("year") and not metadata["year"]:
                metadata["year"] = llm_meta["year"]
            if llm_meta.get("journal"):
                metadata["journal"] = llm_meta["journal"]
            if llm_meta.get("url") and not metadata["url"]:
                metadata["url"] = llm_meta["url"]

        return metadata

    def process_file(self, filepath: Path) -> list[Chunk]:
        """Process a single file into chunks."""
        source_id = self._extract_source_id(filepath.name)

        if source_id in self.processed_sources:
            print(f"  Skipping {filepath.name} (already processed)")
            return []

        print(f"  Processing {filepath.name}...")
        text = filepath.read_text(encoding='utf-8')

        pages = self._extract_pages(text)

        first_page_text = ""
        for _, page_text in pages:
            if page_text.strip():
                first_page_text = page_text
                break
        metadata = self._extract_metadata(first_page_text, filepath.name)

        chunks = []
        chunk_counter = 1

        for page_num, page_text in pages:
            page_text = page_text.strip()
            if not page_text:
                continue

            lines = page_text.split('\n')
            if lines and lines[0].strip().isdigit():
                page_text = '\n'.join(lines[1:]).strip()

            page_chunks = self._split_into_chunks(page_text)

            for chunk_text in page_chunks:
                chunk_text = chunk_text.strip()
                if not chunk_text:
                    continue

                chunk_id = f"{source_id}_P{page_num:03d}C{chunk_counter:03d}"

                chunk = Chunk(
                    chunk_id=chunk_id,
                    source_id=source_id,
                    source_filename=filepath.name,
                    author=metadata["author"],
                    title=metadata["title"],
                    year=metadata["year"],
                    journal=metadata["journal"],
                    volume=metadata.get("volume", ""),
                    issue=metadata.get("issue", ""),
                    url=metadata["url"],
                    page=page_num,
                    text=chunk_text,
                    token_count=self._estimate_tokens(chunk_text)
                )

                chunks.append(chunk)
                chunk_counter += 1

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