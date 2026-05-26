#!/usr/bin/env python3
"""
Research Swarm Downloader Agent
Downloads PDFs, extracts text, and manages corpus for dissertation pipeline.
Uses Qwen3.5-Plus via OpenRouter for intelligent URL handling.
"""

import os
import sys
import json
import hashlib
import tempfile
import argparse
from typing import List, Dict, Optional
from pathlib import Path
from urllib.parse import urlparse
from dataclasses import dataclass, field, asdict
from datetime import datetime

import fitz  # PyMuPDF
import requests

# OpenRouter configuration
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = "qwen/qwen3.5-plus"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

CORPUS_DIR = Path(__file__).parent / "corpus"
METADATA_FILE = CORPUS_DIR / "metadata.json"


@dataclass
class SourceResult:
    """Result for a single source download."""
    id: str
    url: str
    status: str  # "success", "failed", "partial"
    text_length: int = 0
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    filename: Optional[str] = None


class OpenRouterClient:
    """Client for OpenRouter API with Qwen model."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or OPENROUTER_API_KEY
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY environment variable not set")
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "ResearchSwarm/1.0"
        })
    
    def _call_api(self, messages: List[Dict], **kwargs) -> str:
        """Make a call to OpenRouter API."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://research-swarm.local",
            "X-Title": "Research Swarm Downloader",
        }
        
        payload = {
            "model": OPENROUTER_MODEL,
            "messages": messages,
            **kwargs
        }
        
        response = self.session.post(
            f"{OPENROUTER_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
            timeout=60
        )
        response.raise_for_status()
        
        data = response.json()
        return data["choices"][0]["message"]["content"]
    
    def analyze_url(self, url: str) -> Dict:
        """
        Use LLM to analyze URL and determine:
        - If it's a valid PDF URL
        - What paper/source it refers to
        - Any additional context needed
        """
        messages = [
            {
                "role": "system",
                "content": """You are a research assistant analyzing URLs for academic paper downloads.
Given a URL, analyze it and respond with JSON containing:
- is_valid_pdf_url: boolean indicating if URL points to downloadable PDF
- suggested_filename: suggested base filename (no extension)
- source_type: "arxiv", "pdf_direct", "web", or "unknown"
- notes: brief description of what this URL likely contains

Return ONLY valid JSON, no markdown formatting."""
            },
            {
                "role": "user",
                "content": f"Analyze this URL: {url}"
            }
        ]
        
        try:
            response = self._call_api(messages, temperature=0.3, max_tokens=200)
            # Clean response - remove markdown code blocks if present
            response = response.strip()
            if response.startswith("```"):
                response = response.split("```")[1]
                if response.startswith("json"):
                    response = response[4:]
                response = response.strip().rstrip("```")
            
            return json.loads(response)
        except Exception as e:
            return {
                "is_valid_pdf_url": True,  # Assume valid if LLM fails
                "suggested_filename": urlparse(url).path.split("/")[-1].replace(".pdf", ""),
                "source_type": "unknown",
                "notes": f"LLM analysis failed: {str(e)}"
            }


class Downloader:
    """
    Research swarm downloader agent.
    Downloads PDFs, extracts text, saves to corpus.
    """
    
    def __init__(self, corpus_dir: Optional[Path] = None):
        self.corpus_dir = Path(corpus_dir) if corpus_dir else CORPUS_DIR
        self.corpus_dir.mkdir(parents=True, exist_ok=True)
        
        self.llm_client = None
        if OPENROUTER_API_KEY:
            try:
                self.llm_client = OpenRouterClient()
            except ValueError as e:
                print(f"Warning: {e}")
        
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "ResearchSwarm/1.0 (Academic Research Tool)"
        })
        
        # Load existing metadata
        self.metadata = self._load_metadata()
    
    def _load_metadata(self) -> Dict:
        """Load existing metadata or create new."""
        if METADATA_FILE.exists():
            with open(METADATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {
            "sources": [],
            "created_at": datetime.utcnow().isoformat(),
            "version": "1.0"
        }
    
    def _generate_source_id(self, url: str) -> str:
        """Generate a unique source ID from URL hash."""
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        existing_ids = {s["id"] for s in self.metadata["sources"]}
        
        # Find next available sequential number
        used_numbers = set()
        for sid in existing_ids:
            try:
                parts = sid.split("_")
                if parts[0].isdigit():
                    used_numbers.add(int(parts[0]))
            except (ValueError, IndexError):
                pass
        
        counter = 1
        while counter in used_numbers:
            counter += 1
        
        return f"{counter:03d}_{url_hash[:6]}"
    
    def _download_with_retry(self, url: str, max_retries: int = 2) -> Optional[bytes]:
        """Download file with retry logic."""
        for attempt in range(max_retries + 1):
            try:
                response = self.session.get(url, timeout=60, stream=True)
                response.raise_for_status()
                return response.content
                
            except requests.RequestException as e:
                if attempt < max_retries:
                    import time
                    time.sleep(2 ** attempt)  # Exponential backoff
                    continue
                raise
    
    def extract_text(self, pdf_path: str) -> str:
        """
        Extract text from PDF using PyMuPDF.
        Handles multi-column layouts and various PDF structures.
        """
        text_parts = []
        
        try:
            doc = fitz.open(pdf_path)
            
            for page_num, page in enumerate(doc):
                # Extract text with layout preservation
                page_text = page.get_text("text")
                
                if page_text.strip():
                    text_parts.append(f"\n--- Page {page_num + 1} ---\n")
                    text_parts.append(page_text)
                else:
                    # Try blocks for better layout
                    blocks = page.get_text("blocks")
                    if blocks:
                        # Sort by y-coordinate for reading order
                        sorted_blocks = sorted(blocks, key=lambda b: (b[1], b[0]))
                        page_text = "\n".join(b[4].strip() for b in sorted_blocks if b[4].strip())
                        if page_text:
                            text_parts.append(f"\n--- Page {page_num + 1} ---\n")
                            text_parts.append(page_text)
            
            doc.close()
            
        except fitz.FitzError as e:
            raise ValueError(f"PyMuPDF error: {str(e)}")
        
        full_text = "\n".join(text_parts)
        
        # Clean up excessive whitespace
        import re
        full_text = re.sub(r'\n{3,}', '\n\n', full_text)
        full_text = re.sub(r' {2,}', ' ', full_text)
        
        return full_text.strip()
    
    def save_text(self, source_id: str, text: str, url: str) -> str:
        """Save extracted text to corpus directory using original PDF filename from URL."""
        pdf_filename = url.split("/")[-1]
        base_name = pdf_filename.replace(".pdf", "")
        filename = f"{base_name}.txt"
        filepath = self.corpus_dir / filename
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(text)
        
        return filename
    
    def update_metadata(self, results: List[SourceResult]) -> None:
        """Update metadata.json with download results."""
        # Update existing or add new sources
        existing_urls = {s["url"]: s for s in self.metadata["sources"]}
        
        for result in results:
            result_dict = asdict(result)
            if result.url in existing_urls:
                # Update existing
                idx = next(i for i, s in enumerate(self.metadata["sources"]) if s["url"] == result.url)
                self.metadata["sources"][idx] = result_dict
            else:
                self.metadata["sources"].append(result_dict)
        
        # Add/update metadata
        self.metadata["updated_at"] = datetime.utcnow().isoformat()
        self.metadata["total_sources"] = len(self.metadata["sources"])
        self.metadata["successful"] = sum(1 for s in self.metadata["sources"] if s["status"] == "success")
        self.metadata["failed"] = sum(1 for s in self.metadata["sources"] if s["status"] in ("failed", "partial"))
        
        # Write metadata
        with open(METADATA_FILE, "w", encoding="utf-8") as f:
            json.dump(self.metadata, f, indent=2, ensure_ascii=False)
    
    def process_url(self, url: str) -> SourceResult:
        """Process a single URL: download PDF, extract text, save."""
        source_id = self._generate_source_id(url)
        
        try:
            # Analyze URL with LLM if available
            if self.llm_client:
                try:
                    analysis = self.llm_client.analyze_url(url)
                    if not analysis.get("is_valid_pdf_url", True):
                        return SourceResult(
                            id=source_id,
                            url=url,
                            status="failed",
                            error=f"LLM determined URL is not valid PDF: {analysis.get('notes', 'Unknown')}"
                        )
                except Exception as e:
                    print(f"  LLM analysis skipped: {e}")
            
            # Download PDF
            content = self._download_with_retry(url)
            if content is None:
                return SourceResult(
                    id=source_id,
                    url=url,
                    status="failed",
                    error="Download returned empty content"
                )
            
            # Check PDF magic bytes
            if content[:5] != b"%PDF-":
                return SourceResult(
                    id=source_id,
                    url=url,
                    status="failed",
                    error="Downloaded content is not a valid PDF"
                )
            
            # Save to temp file for extraction
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            
            try:
                # Extract text
                text = self.extract_text(tmp_path)
                
                if not text or len(text) < 100:
                    return SourceResult(
                        id=source_id,
                        url=url,
                        status="partial",
                        text_length=len(text),
                        error="Very little text extracted - may be image-based PDF"
                    )
                
                # Save text to corpus
                filename = self.save_text(source_id, text, url)
                
                return SourceResult(
                    id=source_id,
                    url=url,
                    status="success",
                    text_length=len(text),
                    filename=filename
                )
                
            finally:
                # Clean up temp file
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
        
        except requests.RequestException as e:
            return SourceResult(
                id=source_id,
                url=url,
                status="failed",
                error=f"Download error: {str(e)}"
            )
        except Exception as e:
            return SourceResult(
                id=source_id,
                url=url,
                status="failed",
                error=f"Processing error: {str(e)}"
            )
    
    def download(self, urls: List[str]) -> Dict:
        """
        Main download method. Processes all URLs and returns results.
        
        Args:
            urls: List of PDF URLs to download
            
        Returns:
            Dict with results summary and individual source results
        """
        results = []
        
        print(f"Processing {len(urls)} URL(s)...")
        
        for i, url in enumerate(urls, 1):
            print(f"[{i}/{len(urls)}] Processing: {url[:80]}...")
            
            result = self.process_url(url)
            results.append(result)
            
            status_icon = "✓" if result.status == "success" else "⚠" if result.status == "partial" else "✗"
            print(f"  {status_icon} {result.status.upper()}: {result.text_length} chars")
            
            if result.error:
                print(f"    Error: {result.error[:100]}")
        
        # Update metadata
        self.update_metadata(results)
        
        # Summary
        success_count = sum(1 for r in results if r.status == "success")
        partial_count = sum(1 for r in results if r.status == "partial")
        failed_count = sum(1 for r in results if r.status == "failed")
        
        summary = {
            "total": len(urls),
            "successful": success_count,
            "partial": partial_count,
            "failed": failed_count,
            "results": [asdict(r) for r in results],
            "corpus_dir": str(self.corpus_dir),
            "metadata_file": str(METADATA_FILE)
        }
        
        print(f"\nDownload complete!")
        print(f"  Success: {success_count}, Partial: {partial_count}, Failed: {failed_count}")
        print(f"  Corpus: {self.corpus_dir}")
        print(f"  Metadata: {METADATA_FILE}")
        
        return summary


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Research Swarm PDF Downloader Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 downloader.py --urls "https://example.com/paper1.pdf,https://example.com/paper2.pdf"
  python3 downloader.py --urls "https://arxiv.org/pdf/2301.00001.pdf"
  python3 downloader.py --input urls.txt  # File with one URL per line
        """
    )
    
    parser.add_argument(
        "--urls",
        type=str,
        help="Comma-separated list of PDF URLs"
    )
    
    parser.add_argument(
        "--input",
        type=str,
        help="Path to file containing URLs (one per line)"
    )
    
    parser.add_argument(
        "--corpus-dir",
        type=str,
        help=f"Corpus directory (default: {CORPUS_DIR})"
    )
    
    parser.add_argument(
        "--skip-llm",
        action="store_true",
        help="Skip LLM URL analysis (faster but less intelligent)"
    )
    
    args = parser.parse_args()
    
    # Collect URLs
    urls = []
    
    if args.urls:
        urls = [u.strip() for u in args.urls.split(",") if u.strip()]
    elif args.input:
        input_path = Path(args.input)
        if input_path.exists():
            with open(input_path, "r", encoding="utf-8") as f:
                urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        else:
            print(f"Error: Input file not found: {args.input}")
            return 1
    else:
        print("Error: Must provide --urls or --input")
        parser.print_help()
        return 1
    
    if not urls:
        print("Error: No URLs provided")
        return 1
    
    # Initialize downloader
    corpus_dir = Path(args.corpus_dir) if args.corpus_dir else None
    downloader = Downloader(corpus_dir=corpus_dir)
    
    if args.skip_llm:
        downloader.llm_client = None
    
    # Process URLs
    results = downloader.download(urls)
    
    return 0 if results["failed"] == 0 else 1


if __name__ == "__main__":
    exit(main())
