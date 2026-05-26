#!/usr/bin/env python3
"""
Citation Auditor - Validates citations in generated chapters against source chunks.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

import requests


# Constants
DEFAULT_MODEL = "qwen/qwen3.5-plus"
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"


class CitationAuditor:
    def __init__(
        self,
        chapter_path: str,
        chunks_path: Optional[str] = None,
        metadata_path: Optional[str] = None
    ):
        self.chapter_path = Path(chapter_path)
        self.chunks_path = Path(chunks_path) if chunks_path else Path("chunks/chunks.json")
        self.metadata_path = Path(metadata_path) if metadata_path else Path("corpus/metadata.json")
        self.chunks = []
        self.chunk_index = {}  # Index by source_filename for quick key lookup
        self.metadata = {}
        self.api_key = os.environ.get("OPENROUTER_API_KEY", "")
        # MLA citation: (Author Year, p. #) or (filename, Author Year, p. #) or (Author, Year, p. #)
        self.citation_pattern = re.compile(r'\((?:([a-zA-Z0-9_]+),\s*)?([A-Z][a-zA-Z]+)(?:,)?\s+(\d{4}),\s*p\.?\s*(\d+)\)')
        # Broad pattern to detect potential malformed citations
        self.broad_citation_pattern = re.compile(r'\(([^)]{3,60})\)')
        self.quotes_pattern = re.compile(r'"([^"]+)"')
        # Structured citation: [[chunk_id:page]]
        self.structured_pattern = re.compile(r'\[\[([A-Za-z0-9_]+):(\d+)\]\]')
        # MLA simple: (Author page) or (Author, page) — no year
        self.mla_simple_pattern = re.compile(r'\(([A-Z][a-zA-Z]*)\s*,?\s*(\d+)\)')
        # MLA author-in-text: AuthorName (Year, p. #) — e.g., Charyulu (2019, p. 47)
        # This is the most common MLA in-text citation where author is outside the parens
        self.mla_author_in_text_pattern = re.compile(r'([A-Z][a-zA-Z]+)\s+\((\d{4}),\s*p\.?\s*(\d+)\)')
        # Index by chunk_id for quick structured lookup
        self.chunk_by_id = {}

    def load_sources(self):
        """Load chunks and metadata from JSON files."""
        try:
            with open(self.chunks_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Handle {"chunks": [...]} format from chunker.py
                items = data
                if isinstance(data, dict) and 'chunks' in data:
                    items = data['chunks']
                for item in items if isinstance(items, list) else [items]:
                    self.chunks.append(item)
                    # Index by source_filename for quick presence checks
                    for key_field in ('source_filename', 'source'):
                        val = item.get(key_field, '')
                        if val:
                            self.chunk_index[val] = item
                    # Index by chunk_id for structured citation validation
                    cid = item.get('chunk_id', '')
                    if cid:
                        self.chunk_by_id[cid] = item
        except FileNotFoundError:
            print(f"Warning: Chunks file not found at {self.chunks_path}")

        try:
            with open(self.metadata_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Handle {"sources": [...]} format from downloader.py
                items = data
                if isinstance(data, dict) and 'sources' in data:
                    items = data['sources']
                if isinstance(items, list):
                    self.metadata = {}
                    for m in items:
                        key = m.get('filename') or m.get('id') or m.get('source', '')
                        self.metadata[key] = m
                else:
                    self.metadata = items
        except FileNotFoundError:
            print(f"Warning: Metadata file not found at {self.metadata_path}")

    def extract_citations(self, content: str):
        """Extract structured [[chunk_id:page]] and MLA-style citations from content."""
        citations = []
        lines = content.split('\n')
        seen_spans = set()  # Track (line_num, start) to avoid duplicates
        
        for line_num, line in enumerate(lines, 1):
            # Format 1: Structured [[chunk_id:page]]
            for match in self.structured_pattern.finditer(line):
                chunk_id = match.group(1)
                page = int(match.group(2))
                citations.append({
                    'chunk_id': chunk_id,
                    'page': page,
                    'line': line_num,
                    'text': match.group(0),
                    'type': 'structured'
                })
                seen_spans.add((line_num, match.start()))

            # Format 2a: MLA with year and page: (Author Year, p. #) or (filename, Author Year, p. #)
            for match in self.citation_pattern.finditer(line):
                if (line_num, match.start()) in seen_spans:
                    continue
                filename = match.group(1)  # Optional PDF filename prefix
                author = match.group(2)
                year = int(match.group(3))
                page = int(match.group(4))
                citations.append({
                    'author': author,
                    'filename': filename,
                    'year': year,
                    'page': page,
                    'line': line_num,
                    'text': match.group(0),
                    'type': 'mla'
                })
                seen_spans.add((line_num, match.start()))

            # Format 2b: MLA simple (Author page) or (Author, page) — page only, no year
            for match in self.mla_simple_pattern.finditer(line):
                if (line_num, match.start()) in seen_spans:
                    continue
                author = match.group(1)
                page = int(match.group(2))
                citations.append({
                    'author': author,
                    'page': page,
                    'line': line_num,
                    'text': match.group(0),
                    'type': 'mla'
                })
                seen_spans.add((line_num, match.start()))

            # Format 2c: MLA author-in-text: AuthorName (Year, p. #) — e.g., Charyulu (2019, p. 47)
            for match in self.mla_author_in_text_pattern.finditer(line):
                if (line_num, match.start()) in seen_spans:
                    continue
                author = match.group(1)
                year = int(match.group(2))
                page = int(match.group(3))
                citations.append({
                    'author': author,
                    'year': year,
                    'page': page,
                    'line': line_num,
                    'text': match.group(0),
                    'type': 'mla'
                })
                seen_spans.add((line_num, match.start()))

            # Fallback: parenthetical that looks citation-like but matches no known format
            for match in self.broad_citation_pattern.finditer(line):
                if (line_num, match.start()) in seen_spans:
                    continue
                inner = match.group(1)
                if re.search(r'[A-Z][a-z]+', inner) and re.search(r'\d+', inner):
                    citations.append({
                        'line': line_num,
                        'text': match.group(0),
                        'type': 'malformed_citation'
                    })
        
        return citations

    def validate_page(self, author: str, page: int) -> bool:
        """Check if page number exists in relevant chunks."""
        author_lower = author.lower()
        
        for chunk_data in self.chunks:
            source_filename = chunk_data.get('source_filename', '').lower()
            chunk_author = chunk_data.get('author', '').lower()
            chunk_text = chunk_data.get('text', '').lower()
            
            # Only check chunks related to this author
            if (author_lower in source_filename or author_lower in chunk_author
                    or author_lower in chunk_text):
                chunk_page = chunk_data.get('page', 0)
                if chunk_page == page:
                    return True
                
                chunking = chunk_data.get('chunking', {})
                if isinstance(chunking, dict):
                    page_ranges = chunking.get('page_ranges', [])
                    if page_ranges:
                        for page_range in page_ranges:
                            if isinstance(page_range, dict):
                                start = page_range.get('start', 0)
                                end = page_range.get('end', float('inf'))
                                if start <= page <= end:
                                    return True
                            elif isinstance(page_range, (list, tuple)):
                                if len(page_range) >= 2 and page_range[0] <= page <= page_range[1]:
                                    return True
        
        return False

    def check_chunk_exists(self, chunk_id: str) -> bool:
        """Check if a chunk_id exists in the loaded chunks."""
        return chunk_id in self.chunk_by_id

    def check_source_existence(self, author: str) -> bool:
        """Check if author exists in any source (source_filename, metadata, or chunk text)."""
        author_lower = author.lower()
        
        # Check if author appears in chunk source_filenames or source IDs (via index)
        for chunk_key in self.chunk_index:
            if author_lower in chunk_key.lower():
                return True
        
        # Check chunk structured fields and text content
        for chunk_data in self.chunks:
            for field in ('author', 'title', 'source_filename', 'url', 'source'):
                value = chunk_data.get(field, '')
                if author_lower in value.lower():
                    return True
            # Also check text content for author name
            text = chunk_data.get('text', '')
            if author_lower in text.lower():
                return True
        
        # Check all metadata fields for author match
        for meta_entry in self.metadata.values():
            if isinstance(meta_entry, dict):
                for field_value in meta_entry.values():
                    if isinstance(field_value, str) and author_lower in field_value.lower():
                        return True
        
        return False

    def check_quote_accuracy(self, quote: str) -> Optional[str]:
        """Check if quoted text exists in chunks. Returns source or None."""
        quote_lower = quote.lower().strip()
        
        for chunk_data in self.chunks:
            content = chunk_data.get('text', chunk_data.get('content', '')).lower()
            if quote_lower in content:
                return chunk_data.get('source_filename', 'unknown')
        
        return None

    def validate_citation(self, citation: dict) -> list:
        """Validate a single citation using hybrid logic (structured [[chunk_id:page]] or MLA)."""
        issues = []
        
        # Malformed citations don't have content to validate
        if citation['type'] == 'malformed_citation':
            issues.append({
                'type': 'malformed',
                'citation': citation['text'],
                'line': citation['line'],
                'message': f"Malformed citation format: '{citation['text']}'"
            })
            return issues
        
        # Format 1: Structured [[chunk_id:page]]
        if citation['type'] == 'structured':
            chunk_id = citation['chunk_id']
            if self.check_chunk_exists(chunk_id):
                # Valid structured citation — no issue
                return issues
            else:
                issues.append({
                    'type': 'hallucination',
                    'citation': citation['text'],
                    'line': citation['line'],
                    'message': f"No chunk found for '{chunk_id}'"
                })
                return issues
        
        # Format 2: MLA citation — verify author exists in sources
        if citation['type'] == 'mla':
            author = citation['author']
            page = citation['page']
            line = citation['line']
            text = citation['text']
            
            if not self.check_source_existence(author):
                issues.append({
                    'type': 'hallucination',
                    'citation': text,
                    'line': line,
                    'message': f"No source found for '{author}'"
                })
                return issues
            
            if not self.validate_page(author, page):
                issues.append({
                    'type': 'invalid_page',
                    'citation': text,
                    'line': line,
                    'message': f"Page {page} not found in source chunks for '{author}'"
                })
            
            return issues
        
        # Unknown citation type — treat as malformed
        issues.append({
            'type': 'malformed',
            'citation': citation.get('text', ''),
            'line': citation.get('line', 0),
            'message': "Unknown citation format"
        })
        return issues

    def audit(self, content: str) -> dict:
        """Run full audit on chapter content with hybrid citation detection."""
        citations = self.extract_citations(content)
        all_issues = []
        
        for citation in citations:
            issues = self.validate_citation(citation)
            all_issues.extend(issues)
        
        total = len(citations)
        hallucinated = len([i for i in all_issues if i['type'] == 'hallucination'])
        malformed = len([i for i in all_issues if i['type'] == 'malformed'])
        invalid_pages = len([i for i in all_issues if i['type'] == 'invalid_page'])
        
        # Count valid by format type
        structured_valid = sum(
            1 for c in citations
            if c['type'] == 'structured'
            and not any(i['citation'] == c['text'] for i in all_issues if i['type'] in ('hallucination', 'malformed'))
        )
        mla_valid = sum(
            1 for c in citations
            if c['type'] == 'mla'
            and not any(i['citation'] == c['text'] for i in all_issues if i['type'] in ('hallucination', 'malformed'))
        )
        
        valid = total - hallucinated - malformed - invalid_pages
        malformed_rate = (malformed + hallucinated) / total if total > 0 else 0
        passed = hallucinated == 0 and malformed_rate < 0.10
        
        return {
            'chapter_file': self.chapter_path.name,
            'total_citations': total,
            'valid_citations': valid,
            'structured_valid': structured_valid,
            'mla_valid': mla_valid,
            'hallucinated_citations': hallucinated,
            'malformed_citations': malformed,
            'invalid_pages': invalid_pages,
            'issues': all_issues,
            'passed': passed
        }

    def save_report(self, report: dict) -> str:
        """Save audit report to JSON file."""
        chapter_slug = self.chapter_path.stem
        output_dir = Path("output/audit")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_path = output_dir / f"{chapter_slug}_audit.json"
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        return str(output_path)

    def run(self) -> tuple:
        """Run the complete audit workflow."""
        self.load_sources()
        
        with open(self.chapter_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        report = self.audit(content)
        output_path = self.save_report(report)
        
        print_report(report)
        
        return report['passed'], output_path


def print_report(report: dict):
    """Print audit report to stdout."""
    print("\n" + "=" * 60)
    print("CITATION AUDIT REPORT")
    print("=" * 60)
    print(f"Chapter File:     {report['chapter_file']}")
    print(f"Total Citations:  {report['total_citations']}")
    print(f"  Structured:     {report.get('structured_valid', 0)}")
    print(f"  MLA:            {report.get('mla_valid', 0)}")
    print(f"Valid Citations:  {report['valid_citations']}")
    print(f"Hallucinated:     {report.get('hallucinated_citations', 0)}")
    print(f"Malformed:        {report.get('malformed_citations', 0)}")
    print(f"Invalid Pages:    {report.get('invalid_pages', 0)}")
    print(f"Status:           {'PASS' if report['passed'] else 'FAIL'}")
    print("-" * 60)
    
    if report['issues']:
        print(f"Issues Found:     {len(report['issues'])}")
        for issue in report['issues']:
            print(f"  [{issue['type'].upper()}] {issue['citation']}")
            print(f"    Line {issue['line']}: {issue['message']}")
    else:
        print("No issues found.")
    
    print("=" * 60 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Citation Auditor - Validates citations in generated chapters."
    )
    parser.add_argument(
        '--input', '-i',
        required=True,
        help='Input chapter file path'
    )
    parser.add_argument(
        '--chunks', '-c',
        default='chunks/chunks.json',
        help='Path to chunks.json file'
    )
    parser.add_argument(
        '--metadata', '-m',
        default='corpus/metadata.json',
        help='Path to metadata.json file'
    )
    
    args = parser.parse_args()
    
    auditor = CitationAuditor(
        chapter_path=args.input,
        chunks_path=args.chunks,
        metadata_path=args.metadata
    )
    
    auditor.load_sources()
    passed, output_path = auditor.run()
    
    print(f"Report saved to: {output_path}")
    
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
