"""
Phase 2 — Extractor Agent
Extracts references, cities, URLs, DOIs from PDFs using LLM (deepseek-r1).

Usage:
    python extractor.py sources/priyanka_gupta.pdf
    python extractor.py sources/ --batch

Author: Research Swarm Team
"""

import json
import re
import os
import sys
from pathlib import Path
from typing import Dict, Any, List

import fitz

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")


class LLMExtractor:
    """Uses LLM to extract structured data from bibliography text."""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or OPENROUTER_API_KEY
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY not set")
    
    def _call_llm(self, text: str) -> Dict[str, Any]:
        """Call deepseek-r1 via OpenRouter to extract references."""
        try:
            from openai import OpenAI
            client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=self.api_key,
            )
            
            prompt = f"""You are an academic reference extractor. Extract ALL references from the bibliography section below.

For each reference, extract:
- author: full author name(s)
- year: publication year
- title: title of the work
- type: "book", "article", "chapter", "web", or "unknown"

Also extract:
- cities: ALL city names mentioned in the text
- urls: ALL web URLs found
- dois: ALL DOI identifiers found

Return ONLY valid JSON in this exact format:
{{
  "references": [
    {{"author": "...", "year": "...", "title": "...", "type": "..."}}
  ],
  "cities": ["city1", "city2"],
  "urls": ["https://..."],
  "dois": ["10.xxxx/xxxx"]
}}

BIBLIOGRAPHY TEXT:
{text}

Return JSON only, no explanation."""

            response = client.chat.completions.create(
                model="deepseek/deepseek-r1",
                messages=[{"role": "user", "content": prompt}],
                extra_body={
                    "reasoning": {"effort": "high"}
                }
            )
            
            reply = response.choices[0].message.content
            
            # Extract JSON from response (might be wrapped in ```json)
            json_match = re.search(r'```json\s*(.*?)\s*```', reply, re.DOTALL)
            if json_match:
                reply = json_match.group(1)
            
            return json.loads(reply)
            
        except Exception as e:
            print(f"LLM extraction error: {e}")
            return {"references": [], "cities": [], "urls": [], "dois": [], "error": str(e)}
    
    def extract(self, text: str) -> Dict[str, Any]:
        """Extract from bibliography text."""
        return self._call_llm(text)


class PDFExtractor:
    """Extracts bibliography sections from PDFs."""
    
    def __init__(self, pdf_path: str):
        self.pdf_path = Path(pdf_path)
        self.all_text = ""
        self.bib_text = ""
        self._load()
    
    def _load(self):
        """Load PDF text - last 2 pages only for bibliography."""
        try:
            doc = fitz.open(str(self.pdf_path))
            total_pages = len(doc)
            
            # Get last 2 pages (bibliography usually at end)
            last_pages = []
            for page_num in range(max(0, total_pages - 2), total_pages):
                page = doc[page_num]
                last_pages.append(page.get_text())
            
            self.all_text = "\n".join(last_pages)
            doc.close()
        except Exception as e:
            print(f"Error loading PDF: {e}")
    
    def _find_bibliography_section(self) -> str:
        """Extract bibliography section text."""
        lines = self.all_text.split('\n')
        in_bib = False
        bib_lines = []
        
        bib_keywords = [
            r'^reference', r'^bibliography', r'^works cited', 
            r'^selected bibliography', r'^literature cited', r'^working bibliography'
        ]
        
        for line in lines:
            line_stripped = line.strip()
            line_lower = line_stripped.lower()
            
            # Only trigger at START of line (after stripping)
            if not in_bib:
                for kw in bib_keywords:
                    if re.match(kw, line_lower):
                        in_bib = True
                        break
            
            if in_bib:
                bib_lines.append(line)
        
        return '\n'.join(bib_lines)
    
    def extract_with_llm(self, api_key: str = None) -> Dict[str, Any]:
        """Extract using LLM on bibliography text."""
        bib_text = self._find_bibliography_section()
        
        if not bib_text.strip():
            return {
                "pdf_path": str(self.pdf_path),
                "pdf_name": self.pdf_path.name,
                "references": [],
                "cities": [],
                "urls": [],
                "dois": [],
                "error": "No bibliography section found"
            }
        
        try:
            extractor = LLMExtractor(api_key)
            result = extractor.extract(bib_text)
            
            return {
                "pdf_path": str(self.pdf_path),
                "pdf_name": self.pdf_path.name,
                "references": result.get("references", []),
                "cities": result.get("cities", []),
                "urls": result.get("urls", []),
                "dois": result.get("dois", []),
                "stats": {
                    "bib_chars": len(bib_text),
                    "total_pages_scanned": 2
                }
            }
        except Exception as e:
            return {
                "pdf_path": str(self.pdf_path),
                "pdf_name": self.pdf_path.name,
                "references": [],
                "cities": [],
                "urls": [],
                "dois": [],
                "error": str(e)
            }


def process_pdf(pdf_path: str, api_key: str = None) -> Dict[str, Any]:
    """Process single PDF."""
    if not Path(pdf_path).exists():
        return {"error": f"File not found: {pdf_path}"}
    
    extractor = PDFExtractor(pdf_path)
    return extractor.extract_with_llm(api_key)


def process_batch(pdf_dir: str, api_key: str = None) -> List[Dict[str, Any]]:
    """Process all PDFs in directory."""
    pdf_dir = Path(pdf_dir)
    results = []
    
    pdf_files = list(pdf_dir.glob("*.pdf"))
    if not pdf_files:
        pdf_files = list(pdf_dir.rglob("*.pdf"))
    
    print(f"Found {len(pdf_files)} PDF(s)")
    
    for pdf_path in pdf_files:
        print(f"\n📄 Processing: {pdf_path.name}")
        result = process_pdf(str(pdf_path), api_key)
        results.append(result)
        
        if result.get("error") and not result.get("references"):
            print(f"   ❌ {result.get('error', 'Unknown error')}")
        else:
            print(f"   ✅ References: {len(result.get('references', []))}")
            print(f"   🏙️  Cities: {len(result.get('cities', []))}")
            print(f"   🔗 URLs: {len(result.get('urls', []))}")
            print(f"   🔖 DOIs: {len(result.get('dois', []))}")
    
    return results


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Extract references, cities, URLs from PDFs using LLM')
    parser.add_argument('path', help='PDF file or directory of PDFs')
    parser.add_argument('--output', '-o', help='Output JSON file')
    parser.add_argument('--batch', '-b', action='store_true', help='Process directory')
    parser.add_argument('--api-key', '-k', help='OpenRouter API key')
    
    args = parser.parse_args()
    
    api_key = args.api_key or OPENROUTER_API_KEY
    if not api_key:
        print("Error: Set OPENROUTER_API_KEY environment variable")
        sys.exit(1)
    
    if args.batch or Path(args.path).is_dir():
        results = process_batch(args.path, api_key)
    else:
        results = [process_pdf(args.path, api_key)]
    
    print("\n" + "="*60)
    print("EXTRACTION RESULTS")
    print("="*60)
    
    for result in results:
        print(f"\n📄 {result['pdf_name']}")
        
        if result.get('error') and not result.get('references'):
            print(f"   ❌ {result['error']}")
            continue
        
        refs = result.get('references', [])
        if refs:
            print(f"\n   📚 References ({len(refs)}):")
            for r in refs[:5]:
                print(f"      - {r.get('author', '?')}, {r.get('year', '?')}: {r.get('title', '?')[:60]}...")
            if len(refs) > 5:
                print(f"      ... and {len(refs) - 5} more")
        
        cities = result.get('cities', [])
        if cities:
            print(f"\n   🏙️  Cities: {', '.join(cities)}")
        
        urls = result.get('urls', [])
        if urls:
            print(f"\n   🔗 URLs ({len(urls)}):")
            for url in urls[:3]:
                print(f"      - {url[:70]}...")
        
        dois = result.get('dois', [])
        if dois:
            print(f"\n   🔖 DOIs: {', '.join(dois)}")
    
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\n💾 Saved to: {args.output}")
    else:
        print("\n" + "="*60)
        print("FULL JSON (use --output to save)")
        print("="*60)
        print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()