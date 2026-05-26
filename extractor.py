"""
Research Swarm — Extractor Sub-Agent
Extracts references, cities, URLs, DOIs from PDFs and GitHub repositories.

Usage:
    from extractor import Extractor
    ext = Extractor()
    result = ext.extract_from_pdf("paper.pdf")
    result = ext.extract_from_github("https://github.com/user/repo")
    results = ext.process_batch("papers_dir/")

Author: Research Swarm Team
"""

import json
import re
import os
import sys
import tempfile
from pathlib import Path
from typing import Dict, Any, List, Optional

import fitz  # PyMuPDF
import requests

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
MODEL = "deepseek/deepseek-v4-flash"


class Extractor:
    """Extracts structured metadata from academic papers and repositories."""

    SYSTEM_PROMPT = """You are a research metadata extractor. Extract ONLY structured information from text.

Output EXACT JSON format (no markdown, no explanation):
{
    "references": [
        {"author": "...", "year": "...", "title": "...", "type": "article|book|conference|web|other"}
    ],
    "cities": ["City1", "City2"],
    "urls": ["https://..."],
    "dois": ["10.xxxx/..."]
}

Rules:
- references: Only actual bibliographic entries (author, year, title, type)
- cities: Capitalized proper nouns (University cities, conference locations)
- urls: Complete URLs starting with http:// or https://
- dois: Pattern 10.xxxx/xxxxx
- Return ONLY valid JSON"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or OPENROUTER_API_KEY
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY not set")

    def _call_deepseek(self, text: str, max_pages: int = 2) -> Dict[str, Any]:
        """Send text to DeepSeek via OpenRouter for extraction."""
        try:
            from openai import OpenAI
            client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=self.api_key,
            )

            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": f"Extract metadata (max {max_pages} pages):\n\n{text}"}
                ],
                extra_body={"reasoning": {"effort": "high"}},
                temperature=0.1,
                max_tokens=4096
            )

            reply = response.choices[0].message.content

            # Extract JSON from markdown if present
            json_match = re.search(r'```json\s*(.*?)\s*```', reply, re.DOTALL)
            if json_match:
                reply = json_match.group(1)
            else:
                # Try to find raw JSON object
                json_match = re.search(r'\{[\s\S]*\}', reply)
                if json_match:
                    reply = json_match.group(0)

            return json.loads(reply.strip())

        except json.JSONDecodeError:
            return self._fallback_extraction(text)
        except Exception as e:
            print(f"DeepSeek API error: {e}")
            return self._fallback_extraction(text)

    def _fallback_extraction(self, text: str) -> Dict[str, Any]:
        """Regex fallback when API fails."""
        # Extract DOIs
        dois = re.findall(r'10\.\d{4,}/[^\s\]\),\"\'<]+', text)

        # Extract URLs
        urls = re.findall(r'https?://[^\s\]\)\"\'<]+', text)

        # Extract city-like patterns near academic terms
        city_pattern = r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:University|Institute|Center|Centre|Lab)'
        cities = list(set(re.findall(city_pattern, text)))[:20]

        return {
            "references": [],
            "cities": cities,
            "urls": list(set(urls))[:30],
            "dois": list(set(dois))[:20]
        }

    def extract_from_pdf(self, pdf_path: str) -> Dict[str, Any]:
        """
        Extract metadata from last 2 pages of a PDF file.

        Args:
            pdf_path: Path to PDF file

        Returns:
            Dict with references, cities, urls, dois
        """
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        try:
            doc = fitz.open(pdf_path)
            total_pages = len(doc)

            # Extract last 2 pages
            start_page = max(0, total_pages - 2)
            text_chunks = []

            for page_num in range(start_page, total_pages):
                page = doc[page_num]
                text_chunks.append(f"--- Page {page_num + 1}/{total_pages} ---\n{page.get_text()}")

            doc.close()

            combined_text = "\n\n".join(text_chunks)
            result = self._call_deepseek(combined_text)

            result["source_file"] = os.path.basename(pdf_path)
            result["source_type"] = "pdf"
            result["pages_extracted"] = f"{start_page + 1}-{total_pages}"

            return result

        except fitz.FitZError as e:
            return {
                "error": f"Failed to read PDF: {str(e)}",
                "references": [], "cities": [], "urls": [], "dois": [],
                "source_file": os.path.basename(pdf_path),
                "source_type": "pdf"
            }

    def extract_from_github(self, github_url: str) -> Dict[str, Any]:
        """
        Extract README content from GitHub repository.

        Args:
            github_url: GitHub repository or file URL

        Returns:
            Dict with references, cities, urls, dois
        """
        # Convert GitHub URL to raw content URL
        raw_url = self._github_to_raw(github_url)

        try:
            response = requests.get(raw_url, timeout=30, headers={"User-Agent": "Research-Swarm/1.0"})
            response.raise_for_status()
            content = response.text

            result = self._call_deepseek(content)
            result["source_url"] = github_url
            result["source_type"] = "github"

            return result

        except requests.RequestException as e:
            return {
                "error": f"Failed to fetch GitHub: {str(e)}",
                "references": [], "cities": [], "urls": [], "dois": [],
                "source_url": github_url,
                "source_type": "github"
            }

    def _github_to_raw(self, url: str) -> str:
        """Convert github.com URL to raw.githubusercontent.com URL."""
        patterns = [
            # https://github.com/user/repo/blob/branch/path
            (r'github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.+)', 
             lambda m: f"https://raw.githubusercontent.com/{m.group(1)}/{m.group(2)}/{m.group(3)}/{m.group(4)}"),
            # https://github.com/user/repo (README fallback)
            (r'github\.com/([^/]+)/([^/]+)/?$',
             lambda m: f"https://api.github.com/repos/{m.group(1)}/{m.group(2)}/readme"),
        ]

        for pattern, converter in patterns:
            match = re.match(pattern, url)
            if match:
                if 'api.github.com' in converter(match):
                    # Need to fetch API to get README download URL
                    return converter(match)
                return converter(match)

        # Already raw URL or unknown format
        return url.replace('github.com', 'raw.githubusercontent.com').replace('/blob/', '/')

    def extract_from_url(self, url: str) -> Dict[str, Any]:
        """Auto-detect and extract from any URL (PDF or web)."""
        if 'github.com' in url:
            return self.extract_from_github(url)
        elif url.lower().endswith('.pdf'):
            return self._extract_pdf_from_url(url)
        else:
            return self._extract_web_content(url)

    def _extract_pdf_from_url(self, url: str) -> Dict[str, Any]:
        """Download PDF to temp file and extract."""
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
            try:
                response = requests.get(url, timeout=60, stream=True)
                response.raise_for_status()
                for chunk in response.iter_content(chunk_size=8192):
                    tmp.write(chunk)
                tmp_path = tmp.name

                result = self.extract_from_pdf(tmp_path)
                result["source_url"] = url
                return result
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    def _extract_web_content(self, url: str) -> Dict[str, Any]:
        """Extract from generic web page."""
        try:
            response = requests.get(url, timeout=30, headers={"User-Agent": "Research-Swarm/1.0"})
            response.raise_for_status()

            # Try to extract main content
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.text, 'html.parser')

            # Remove script/style elements
            for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
                tag.decompose()

            text = soup.get_text(separator='\n', strip=True)
            result = self._call_deepseek(text[:15000])  # Limit text size

            result["source_url"] = url
            result["source_type"] = "web"

            return result

        except ImportError:
            # bs4 not available, use raw text
            result = self._call_deepseek(response.text[:15000])
            result["source_url"] = url
            result["source_type"] = "web"
            return result
        except requests.RequestException as e:
            return {
                "error": f"Failed to fetch URL: {str(e)}",
                "references": [], "cities": [], "urls": [], "dois": [],
                "source_url": url,
                "source_type": "web"
            }

    def process_batch(self, pdf_dir: str, pattern: str = "*.pdf") -> List[Dict[str, Any]]:
        """
        Process all PDFs in a directory.

        Args:
            pdf_dir: Directory containing PDF files
            pattern: Glob pattern for matching files

        Returns:
            List of extraction results
        """
        results = []
        dir_path = Path(pdf_dir)

        if not dir_path.exists():
            raise FileNotFoundError(f"Directory not found: {pdf_dir}")

        pdf_files = list(dir_path.glob(pattern))
        if not pdf_files:
            pdf_files = list(dir_path.rglob(pattern))

        print(f"Found {len(pdf_files)} PDF(s) in {pdf_dir}")

        for pdf_path in pdf_files:
            try:
                result = self.extract_from_pdf(str(pdf_path))
                results.append(result)

                if result.get("error") and not result.get("references"):
                    print(f"  ❌ {pdf_path.name}: {result['error']}")
                else:
                    print(f"  ✅ {pdf_path.name}: {len(result.get('references', []))} refs, "
                          f"{len(result.get('cities', []))} cities, "
                          f"{len(result.get('dois', []))} DOIs")

            except Exception as e:
                results.append({
                    "error": str(e),
                    "source_file": pdf_path.name,
                    "references": [], "cities": [], "urls": [], "dois": []
                })
                print(f"  ❌ {pdf_path.name}: {e}")

        return results

    def save_results(self, results: List[Dict], output_path: str):
        """Save extraction results to JSON file."""
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

    def to_downloader_format(self, results: List[Dict]) -> Dict[str, Any]:
        """
        Transform extraction results for downloader agent.

        Returns:
            Dict with categorized data for download
        """
        download_items = {
            "papers": [],
            "references": [],
            "urls": [],
            " dois": []
        }

        for result in results:
            # Collect DOIs
            for doi in result.get("dois", []):
                download_items["dois"].append({"doi": doi, "source": result.get("source_file", result.get("source_url", "unknown"))})

            # Collect URLs
            for url in result.get("urls", []):
                if url not in [u["url"] for u in download_items["urls"]]:
                    download_items["urls"].append({"url": url, "source": result.get("source_file", result.get("source_url", "unknown"))})

            # Collect references
            for ref in result.get("references", []):
                download_items["references"].append(ref)

        return download_items


# Convenience functions
def extract_from_pdf(pdf_path: str) -> Dict[str, Any]:
    """Extract from PDF file."""
    ext = Extractor()
    return ext.extract_from_pdf(pdf_path)


def extract_from_github(github_url: str) -> Dict[str, Any]:
    """Extract from GitHub URL."""
    ext = Extractor()
    return ext.extract_from_github(github_url)


def process_batch(pdf_dir: str) -> List[Dict[str, Any]]:
    """Process directory of PDFs."""
    ext = Extractor()
    return ext.process_batch(pdf_dir)


def main():
    """CLI interface."""
    import argparse

    parser = argparse.ArgumentParser(description='Extract metadata from PDFs/GitHub using DeepSeek')
    parser.add_argument('path', help='PDF file, GitHub URL, or directory')
    parser.add_argument('--output', '-o', help='Output JSON file')
    parser.add_argument('--batch', '-b', action='store_true', help='Process directory (PDFs only)')
    parser.add_argument('--api-key', '-k', help='OpenRouter API key')

    args = parser.parse_args()

    api_key = args.api_key or OPENROUTER_API_KEY
    if not api_key:
        print("Error: Set OPENROUTER_API_KEY environment variable")
        sys.exit(1)

    ext = Extractor(api_key)

    # Determine source type
    if args.batch or Path(args.path).is_dir():
        results = ext.process_batch(args.path)
    elif args.path.startswith('http'):
        results = [ext.extract_from_url(args.path)]
    else:
        results = [ext.extract_from_pdf(args.path)]

    # Output
    print("\n" + "=" * 60)
    print("EXTRACTION RESULTS")
    print("=" * 60)

    for result in results:
        source = result.get('source_file') or result.get('source_url', 'unknown')
        print(f"\n📄 {source}")

        if result.get('error') and not result.get('references'):
            print(f"   ❌ {result['error']}")
            continue

        refs = result.get('references', [])
        if refs:
            print(f"\n   📚 References ({len(refs)}):")
            for r in refs[:5]:
                print(f"      - {r.get('author', '?')}, {r.get('year', '?')}: {r.get('title', '?')[:50]}...")
            if len(refs) > 5:
                print(f"      ... +{len(refs) - 5} more")

        cities = result.get('cities', [])
        if cities:
            print(f"\n   🏙️  Cities: {', '.join(cities[:10])}")

        dois = result.get('dois', [])
        if dois:
            print(f"\n   🔖 DOIs: {', '.join(dois[:5])}")

        urls = result.get('urls', [])
        if urls:
            print(f"\n   🔗 URLs: {len(urls)} found")

    if args.output:
        ext.save_results(results, args.output)
        print(f"\n💾 Saved to: {args.output}")
    else:
        print("\n" + "=" * 60)
        print("JSON OUTPUT")
        print("=" * 60)
        print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()