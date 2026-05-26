"""
Phase 1 — Source Downloader Agent
Downloads PDFs from titles + optional URLs using free APIs.

Usage:
    python downloader.py "Train to Pakistan" "https://example.com/link.pdf"
    python downloader.py "arXiv:2301.12345"  # arXiv paper
    python downloader.py "Partition literature analysis"  # search only

APIs used:
- arXiv (free, no key)
- Semantic Scholar (free tier)
- CrossRef (free, DOI resolution)

Author: Research Swarm Team
"""

import os
import json
import time
import hashlib
import requests
import re
from pathlib import Path
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse

# Config
SOURCES_DIR = Path(__file__).parent / "sources"
METADATA_FILE = SOURCES_DIR / "metadata.json"
CHUNKS_FILE = Path(__file__).parent / "chunks.json"

SOURCES_DIR.mkdir(exist_ok=True)

# Free API endpoints
ARXIV_API = "http://export.arxiv.org/api/query"
SEMANTIC_SCHOLAR_API = "https://api.semanticscholar.org/graph/v1/paper/search"
CROSSREF_API = "https://api.crossref.org/works"
USER_AGENT = "Research-Swarm/2.0 (academic research tool)"


class SourceDownloader:
    """Downloads academic papers from various sources."""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.metadata = self._load_metadata()
    
    def _load_metadata(self) -> Dict[str, Any]:
        """Load existing metadata or create new."""
        if METADATA_FILE.exists():
            with open(METADATA_FILE, 'r') as f:
                return json.load(f)
        return {"sources": [], "version": "2.0"}
    
    def _save_metadata(self):
        """Save metadata to file."""
        with open(METADATA_FILE, 'w') as f:
            json.dump(self.metadata, f, indent=2)
    
    def _generate_source_id(self, title: str) -> str:
        """Generate consistent source ID from title."""
        clean = re.sub(r'[^a-zA-Z0-9]', '', title[:30].lower())
        prefix_map = {
            'train': 'NOV',    # Primary: novel
            'novel': 'NOV',
            'film': 'FLM',     # Primary: film
            'movie': 'FLM',
            'partition': 'SEC', # Secondary source
            'adaptation': 'SEC',
            'violence': 'SEC',
            'humanism': 'SEC',
        }
        prefix = 'SRC'  # default
        for key, val in prefix_map.items():
            if key in clean[:10]:
                prefix = val
                break
        
        # Hash for uniqueness
        hash_suffix = hashlib.md5(title.encode()).hexdigest()[:4].upper()
        return f"{prefix}_{hash_suffix}"
    
    def _sanitize_filename(self, title: str, source_id: str) -> str:
        """Create safe filename from title."""
        clean = re.sub(r'[^a-zA-Z0-9\-_]', '_', title[:50])
        return f"{source_id}_{clean}.pdf"
    
    def _download_file(self, url: str, dest_path: Path, max_retries: int = 3) -> bool:
        """Download file with retries."""
        for attempt in range(max_retries):
            try:
                response = self.session.get(url, timeout=30, stream=True)
                response.raise_for_status()
                
                # Check if actually a PDF
                content_type = response.headers.get('Content-Type', '')
                if 'pdf' not in content_type.lower() and not url.endswith('.pdf'):
                    # Check first bytes
                    first_bytes = response.content[:10]
                    if b'%PDF' not in first_bytes:
                        print(f"  Warning: URL doesn't appear to be PDF: {content_type}")
                
                with open(dest_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                return True
                
            except requests.exceptions.RequestException as e:
                print(f"  Attempt {attempt + 1}/{max_retries} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
        return False
    
    def _search_arxiv(self, query: str) -> Optional[Dict[str, Any]]:
        """Search arXiv for paper."""
        try:
            params = {
                'search_query': f'all:{query}',
                'max_results': 5,
                'sortBy': 'relevance'
            }
            response = self.session.get(ARXIV_API, params=params, timeout=15)
            response.raise_for_status()
            
            # Parse XML response (arXiv returns Atom XML)
            content = response.text
            
            # Extract paper info using regex (simple parser)
            entry_pattern = r'<entry>(.*?)</entry>'
            entries = re.findall(entry_pattern, content, re.DOTALL)
            
            for entry in entries:
                title_match = re.search(r'<title>(.*?)</title>', entry, re.DOTALL)
                id_match = re.search(r'<id>(.*?)</id>', entry)
                summary_match = re.search(r'<summary>(.*?)</summary>', entry, re.DOTALL)
                
                if title_match and id_match:
                    title = title_match.group(1).replace('\n', ' ').strip()
                    
                    # Check for PDF link
                    links = re.findall(r'<link[^>]+href="([^"]+)"[^>]*>', entry)
                    pdf_url = None
                    for link in links:
                        if 'pdf' in link:
                            pdf_url = link
                            if not link.endswith('.pdf'):
                                pdf_url = link + '.pdf'
                            break
                    
                    return {
                        'title': title,
                        'url': pdf_url,
                        'arxiv_id': id_match.group(1).split('/')[-1],
                        'source': 'arXiv'
                    }
            return None
        except Exception as e:
            print(f"  arXiv search error: {e}")
            return None
    
    def _search_semantic_scholar(self, query: str) -> Optional[Dict[str, Any]]:
        """Search Semantic Scholar for paper."""
        try:
            params = {
                'query': query,
                'limit': 5,
                'fields': 'title,authors,year,externalIds,openAccessPdf'
            }
            response = self.session.get(
                SEMANTIC_SCHOLAR_API,
                params=params,
                timeout=15
            )
            response.raise_for_status()
            data = response.json()
            
            papers = data.get('data', [])
            for paper in papers:
                # Prefer papers with free PDF
                oa_pdf = paper.get('openAccessPdf')
                pdf_url = oa_pdf.get('url') if oa_pdf else None
                
                # Fall back to arXiv ID if available
                external = paper.get('externalIds', {})
                arxiv_id = external.get('ArXiv')
                
                if not pdf_url and arxiv_id:
                    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
                
                authors = paper.get('authors', [])
                author_names = [a.get('name', '') for a in authors[:3]]
                
                return {
                    'title': paper.get('title', ''),
                    'url': pdf_url,
                    'year': paper.get('year'),
                    'authors': author_names,
                    'doi': external.get('DOI'),
                    'arxiv_id': arxiv_id,
                    'source': 'Semantic Scholar'
                }
            return None
        except Exception as e:
            print(f"  Semantic Scholar search error: {e}")
            return None
    
    def _search_crossref(self, query: str) -> Optional[Dict[str, Any]]:
        """Search CrossRef for paper (DOI resolution primarily)."""
        try:
            # Check if query looks like a DOI
            if query.startswith('10.'):
                url = f"{CROSSREF_API}/{query}"
                response = self.session.get(url, timeout=15)
                response.raise_for_status()
                data = response.json()
                work = data.get('message', {})
                
                authors = []
                for author in work.get('author', []):
                    given = author.get('given', '')
                    family = author.get('family', '')
                    if given or family:
                        authors.append(f"{given} {family}".strip())
                
                return {
                    'title': work.get('title', [''])[0] if work.get('title') else '',
                    'url': work.get('URL'),
                    'year': work.get('published-print', {}).get('date-parts', [[None]])[0][0],
                    'authors': authors,
                    'doi': query,
                    'publisher': work.get('publisher'),
                    'source': 'CrossRef'
                }
            
            # Search by title
            params = {
                'query.title': query,
                'rows': 5
            }
            response = self.session.get(CROSSREF_API, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
            items = data.get('message', {}).get('items', [])
            
            if items:
                work = items[0]
                authors = []
                for author in work.get('author', []):
                    given = author.get('given', '')
                    family = author.get('family', '')
                    if given or family:
                        authors.append(f"{given} {family}".strip())
                
                return {
                    'title': work.get('title', [''])[0] if work.get('title') else '',
                    'url': work.get('URL'),
                    'year': work.get('published-print', {}).get('date-parts', [[None]])[0][0],
                    'authors': authors,
                    'doi': work.get('DOI'),
                    'publisher': work.get('publisher'),
                    'source': 'CrossRef'
                }
            return None
        except Exception as e:
            print(f"  CrossRef search error: {e}")
            return None
    
    def _is_arxiv_id(self, query: str) -> bool:
        """Check if query looks like an arXiv ID."""
        pattern = r'(?:arXiv:)?(\d{4}\.\d{4,5}(v\d+)?|[a-z-]+/\d{7})'
        return bool(re.match(pattern, query, re.I))
    
    def _resolve_arxiv_pdf(self, arxiv_id: str) -> Optional[str]:
        """Get PDF URL for arXiv paper."""
        clean_id = arxiv_id.replace('arXiv:', '').strip()
        # Try both formats
        for fmt in [f"https://arxiv.org/pdf/{clean_id}.pdf", 
                    f"https://arxiv.org/pdf/{clean_id}"]:
            try:
                response = self.session.head(fmt, timeout=10, allow_redirects=True)
                if response.status_code == 200:
                    return fmt
            except:
                continue
        return None
    
    def download(self, title: str, url: Optional[str] = None, 
                 source_type: str = "secondary") -> Dict[str, Any]:
        """
        Download a paper by title and optional URL.
        
        Args:
            title: Paper title or arXiv ID (e.g., "arXiv:2301.12345")
            url: Direct PDF URL (optional)
            source_type: "primary" or "secondary"
        
        Returns:
            Source metadata dict
        """
        print(f"\n📥 Processing: {title}")
        if url:
            print(f"   URL provided: {url}")
        
        source_id = self._generate_source_id(title)
        filename = self._sanitize_filename(title, source_id)
        dest_path = SOURCES_DIR / filename
        
        # Check if already downloaded
        for source in self.metadata['sources']:
            if source.get('source_id') == source_id:
                if dest_path.exists():
                    print(f"   ⚠️  Already exists: {filename}")
                    return source
        
        result = None
        
        # Step 1: Direct URL if provided
        if url:
            print(f"   → Trying direct URL...")
            if self._download_file(url, dest_path):
                result = {
                    'source_id': source_id,
                    'title': title,
                    'url': url,
                    'pdf_path': str(dest_path),
                    'resolved': True,
                    'source_type': source_type,
                    'download_method': 'direct'
                }
        
        # Step 2: Check if arXiv ID
        if not result and self._is_arxiv_id(title):
            print(f"   → Trying arXiv ID...")
            arxiv_id = title.replace('arXiv:', '').strip()
            pdf_url = self._resolve_arxiv_pdf(arxiv_id)
            if pdf_url and self._download_file(pdf_url, dest_path):
                result = {
                    'source_id': source_id,
                    'title': title,
                    'arxiv_id': arxiv_id,
                    'url': pdf_url,
                    'pdf_path': str(dest_path),
                    'resolved': True,
                    'source_type': source_type,
                    'download_method': 'arxiv'
                }
        
        # Step 3: Search APIs
        if not result:
            print(f"   → Searching arXiv...")
            result = self._search_arxiv(title)
            if result and result.get('url'):
                print(f"   → Found: {result.get('title', '')[:60]}...")
                if self._download_file(result['url'], dest_path):
                    result['source_id'] = source_id
                    result['pdf_path'] = str(dest_path)
                    result['resolved'] = True
                    result['source_type'] = source_type
                    result['download_method'] = 'arxiv_api'
                else:
                    result = None
            
            if not result:
                print(f"   → Searching Semantic Scholar...")
                result = self._search_semantic_scholar(title)
                if result and result.get('url'):
                    print(f"   → Found: {result.get('title', '')[:60]}...")
                    if self._download_file(result['url'], dest_path):
                        result['source_id'] = source_id
                        result['pdf_path'] = str(dest_path)
                        result['resolved'] = True
                        result['source_type'] = source_type
                        result['download_method'] = 'semantic_scholar'
                    else:
                        result = None
            
            if not result:
                print(f"   → Searching CrossRef...")
                result = self._search_crossref(title)
                if result and result.get('url'):
                    print(f"   → Found: {result.get('title', '')[:60]}...")
                    # CrossRef URL is usually not a direct PDF, mark as unresolved
                    result['source_id'] = source_id
                    result['pdf_path'] = None
                    result['resolved'] = False
                    result['source_type'] = source_type
                    result['download_method'] = 'crossref'
                else:
                    result = None
        
        # Step 4: Save result
        if result:
            if result not in self.metadata['sources']:
                self.metadata['sources'].append(result)
            self._save_metadata()
            
            if result.get('resolved'):
                print(f"   ✅ Downloaded: {filename}")
            else:
                print(f"   ⚠️  Found metadata but no PDF: {result.get('url')}")
        else:
            # Record failed attempt
            result = {
                'source_id': source_id,
                'title': title,
                'url': url,
                'pdf_path': None,
                'resolved': False,
                'source_type': source_type,
                'download_method': 'failed'
            }
            self.metadata['sources'].append(result)
            self._save_metadata()
            print(f"   ❌ Could not find or download: {title}")
        
        return result
    
    def download_batch(self, items: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """
        Download multiple papers.
        
        Args:
            items: List of {"title": "...", "url": "...", "type": "primary|secondary"}
        
        Returns:
            List of result metadata dicts
        """
        results = []
        for i, item in enumerate(items):
            print(f"\n[{i+1}/{len(items)}]")
            result = self.download(
                title=item['title'],
                url=item.get('url'),
                source_type=item.get('type', 'secondary')
            )
            results.append(result)
            
            # Rate limit between requests
            if i < len(items) - 1:
                time.sleep(1)
        
        return results
    
    def list_sources(self) -> List[Dict[str, Any]]:
        """List all sources in metadata."""
        return self.metadata.get('sources', [])
    
    def show_status(self):
        """Show download status summary."""
        sources = self.metadata.get('sources', [])
        total = len(sources)
        resolved = sum(1 for s in sources if s.get('resolved'))
        
        print(f"\n📚 Source Status")
        print(f"   Total: {total}")
        print(f"   Downloaded: {resolved}")
        print(f"   Pending: {total - resolved}")
        
        if not sources:
            return
        
        print(f"\n   Sources:")
        for s in sources:
            status = "✅" if s.get('resolved') else "⏳"
            title = s.get('title', 'Unknown')[:50]
            method = s.get('download_method', 'unknown')
            print(f"   {status} [{s.get('source_id', '???')}] {title}... ({method})")


def main():
    """CLI interface."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Download academic papers')
    parser.add_argument('title', nargs='?', help='Paper title or arXiv ID')
    parser.add_argument('--url', '-u', help='Direct PDF URL')
    parser.add_argument('--type', '-t', choices=['primary', 'secondary'], 
                        default='secondary', help='Source type')
    parser.add_argument('--batch', '-b', action='store_true', help='Batch mode (JSON file)')
    parser.add_argument('--list', '-l', action='store_true', help='List all sources')
    parser.add_argument('--status', '-s', action='store_true', help='Show download status')
    
    args = parser.parse_args()
    
    downloader = SourceDownloader()
    
    if args.status or args.list:
        downloader.show_status()
        return
    
    if args.batch:
        # Read batch JSON
        import sys
        batch_file = sys.stdin.read() if not sys.stdin.isatty() else None
        if not batch_file:
            print("Error: Provide JSON array via stdin or file")
            print('Example: echo \'[{"title": "...", "url": "..."}]\' | python downloader.py --batch')
            return
        try:
            items = json.loads(batch_file)
            results = downloader.download_batch(items)
            print(f"\n✅ Batch complete: {len(results)} items processed")
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON: {e}")
        return
    
    if not args.title:
        parser.print_help()
        return
    
    result = downloader.download(args.title, args.url, args.type)
    
    if result.get('resolved'):
        print(f"\n✅ Success! Saved to: {result.get('pdf_path')}")
    else:
        print(f"\n⚠️  Paper found but PDF not downloadable")
        if result.get('url'):
            print(f"   URL: {result.get('url')}")


if __name__ == '__main__':
    main()