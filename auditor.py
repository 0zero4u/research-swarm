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
        self.chunks = {}
        self.metadata = {}
        self.api_key = os.environ.get("OPENROUTER_API_KEY", "")
        self.citation_pattern = re.compile(r'\(([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(\d+))')
        self.quotes_pattern = re.compile(r'"([^"]+)"')

    def load_sources(self):
        """Load chunks and metadata from JSON files."""
        try:
            with open(self.chunks_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for item in data if isinstance(data, list) else [data]:
                    if 'source' in item:
                        self.chunks[item['source']] = item
        except FileNotFoundError:
            print(f"Warning: Chunks file not found at {self.chunks_path}")

        try:
            with open(self.metadata_path, 'r', encoding='utf-8') as f:
                self.metadata = json.load(f)
                if isinstance(self.metadata, list):
                    self.metadata = {m.get('source', m.get('id', '')): m for m in self.metadata}
        except FileNotFoundError:
            print(f"Warning: Metadata file not found at {self.metadata_path}")

    def extract_citations(self, content: str):
        """Extract MLA-style citations from content."""
        citations = []
        lines = content.split('\n')
        
        for line_num, line in enumerate(lines, 1):
            matches = self.citation_pattern.finditer(line)
            for match in matches:
                author = match.group(1)
                page = int(match.group(2))
                citations.append({
                    'author': author,
                    'page': page,
                    'line': line_num,
                    'text': match.group(0)
                })
        
        return citations

    def validate_page(self, author: str, page: int) -> bool:
        """Check if page number exists in relevant chunks."""
        author_lower = author.lower()
        
        for source, chunk_data in self.chunks.items():
            source_lower = source.lower()
            chunk_author = chunk_data.get('author', '').lower()
            
            if author_lower in source_lower or author_lower in chunk_author:
                chunking = chunk_data.get('chunking', {})
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
                else:
                    pages = chunk_data.get('pages', [])
                    if page in pages:
                        return True
                    
                    page_start = chunk_data.get('page_start', 0)
                    page_end = chunk_data.get('page_end', 0)
                    if page_start and page_end:
                        if page_start <= page <= page_end:
                            return True
        
        return False

    def check_source_existence(self, author: str) -> bool:
        """Check if author exists in any source."""
        author_lower = author.lower()
        
        if author_lower in [s.lower() for s in self.chunks.keys()]:
            return True
        
        for source, chunk_data in self.chunks.items():
            chunk_author = chunk_data.get('author', '').lower()
            chunk_title = chunk_data.get('title', '').lower()
            if author_lower in chunk_author or author_lower in chunk_title:
                return True
        
        for meta_author in self.metadata.values():
            if isinstance(meta_author, dict):
                if author_lower in meta_author.get('author', '').lower():
                    return True
        
        return False

    def check_quote_accuracy(self, quote: str) -> Optional[str]:
        """Check if quoted text exists in chunks. Returns source or None."""
        quote_lower = quote.lower().strip()
        
        for source, chunk_data in self.chunks.items():
            content = chunk_data.get('content', '').lower()
            if quote_lower in content:
                return source
        
        return None

    def validate_citation(self, citation: dict) -> list:
        """Validate a single citation and return any issues."""
        issues = []
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

    def audit(self, content: str) -> dict:
        """Run full audit on chapter content."""
        citations = self.extract_citations(content)
        all_issues = []
        
        for citation in citations:
            issues = self.validate_citation(citation)
            all_issues.extend(issues)
        
        total = len(citations)
        valid = total - len([i for i in all_issues if i['type'] in ('hallucination', 'invalid_page')])
        hallucination_count = len([i for i in all_issues if i['type'] == 'hallucination'])
        page_errors = len([i for i in all_issues if i['type'] == 'invalid_page'])
        
        page_error_rate = page_errors / total if total > 0 else 0
        passed = hallucination_count == 0 and page_error_rate <= 0.10
        
        return {
            'chapter_file': self.chapter_path.name,
            'total_citations': total,
            'valid_citations': valid,
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
    print(f"Valid Citations:  {report['valid_citations']}")
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
