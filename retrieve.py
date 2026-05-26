"""
Phase 6 Retrieval System - Relationship-First Approach

Pipeline:
query -> rule-based query parser -> graph traversal -> LightRAG retrieval -> rerank -> evidence pack

Author: Research Swarm Team
"""

import json
import re
from typing import List, Dict, Any, Set, Tuple
from pathlib import Path
# Optional: sentence-transformers for reranking
try:
    from sentence_transformers import CrossEncoder
    CROSS_ENCODER_AVAILABLE = True
except ImportError:
    CROSS_ENCODER_AVAILABLE = False
    print("Warning: sentence-transformers not installed. Reranking will use cosine similarity fallback.")


class QueryParser:
    """Rule-based query parser (non-LLM) for extracting themes and authors."""
    
    def __init__(self, theme_index_path: str):
        self.theme_index_path = theme_index_path
        self._load_theme_index()
        self._compile_patterns()
    
    def _load_theme_index(self):
        """Load theme index to get available themes."""
        with open(self.theme_index_path, 'r') as f:
            self.theme_index = json.load(f)
        self.available_themes = set(self.theme_index.keys())
    
    def _compile_patterns(self):
        """Compile regex patterns for author detection."""
        # Common author name patterns (Indian names common in academic papers)
        self.author_patterns = [
            r'\b([A-Z][a-z]+)\s+(?:Gupta|Singh|Malgonkar|Butalia|Menon|Bhasin)\b',
            r'\b([A-Z][a-z]+)\b',  # Single names like "Priyanka", "Khushwant", "Manohar"
        ]
        
        # Themes to detect (from theme_index keys)
        self.theme_keywords = {
            'partition': ['partition', 'partitioning', 'partitioned'],
            'Gandhi': ['gandhi', 'mahatma', 'gandhian'],
            'communal riots': ['communal riots', 'communal violence', 'riots', 'clashes'],
            'violence': ['violence', 'violent', 'bloodshed', 'atrocities'],
            'nationalism': ['nationalism', 'nationalist', 'patriotism'],
            'memory': ['memory', 'memories', 'remembrance', 'nostalgia'],
            'identity': ['identity', 'identities', 'belonging'],
            'Train to Pakistan': ['train to pakistan', 'mano majra'],
            'migration': ['migration', 'migrants', 'refugees', 'exodus'],
            'A Bend in the Ganges': ['bend in the ganges', 'ganges'],
        }
    
    def parse(self, query: str) -> Dict[str, Any]:
        """Parse query to extract themes and authors."""
        query_lower = query.lower()
        
        # Extract themes
        themes = self._extract_themes(query_lower)
        
        # Extract authors
        authors = self._extract_authors(query)
        
        return {
            'themes': themes,
            'authors': authors,
            'query_lower': query_lower
        }
    
    def _extract_themes(self, query_lower: str) -> List[str]:
        """Match query against available themes."""
        matched_themes = []
        
        for theme in self.available_themes:
            # Direct match
            if theme.lower() in query_lower:
                matched_themes.append(theme)
            # Keyword matching
            elif theme in self.theme_keywords:
                for keyword in self.theme_keywords[theme]:
                    if keyword in query_lower:
                        matched_themes.append(theme)
                        break
        
        return list(set(matched_themes))  # Deduplicate
    
    def _extract_authors(self, query: str) -> List[str]:
        """Extract author names using regex patterns."""
        authors = []
        
        # Known authors in the dataset
        known_authors = [
            'Priyanka', 'Priyanka Gupta',
            'Khushwant', 'Khushwant Singh',
            'Manohar', 'Manohar Malgonkar',
            'Urvashi', 'Urvashi Butalia',
            'Ritu', 'Ritu Menon',
            'Kamla', 'Kamla Bhasin'
        ]
        
        for author in known_authors:
            if author in query:
                full_name = author if ' ' in author else f"{author} {'Gupta' if 'Priyanka' in author else 'Singh' if 'Khushwant' in author else 'Malgonkar' if 'Manohar' in author else ''}"
                authors.append(full_name)
        
        return list(set(authors))


class GraphTraversal:
    """Graph traversal using theme_index.json to find candidate chunks."""
    
    def __init__(self, theme_index_path: str):
        self.theme_index_path = theme_index_path
        self._load_theme_index()
    
    def _load_theme_index(self):
        """Load theme index."""
        with open(self.theme_index_path, 'r') as f:
            self.theme_index = json.load(f)
    
    def find_candidates(self, themes: List[str], authors: List[str] = None) -> Set[str]:
        """Find candidate chunk IDs from themes (and optionally authors)."""
        candidate_chunks = set()
        
        for theme in themes:
            if theme in self.theme_index:
                page_ids = self.theme_index[theme]
                for page_id in page_ids:
                    chunk_id = page_id.replace('_P', '_C')
                    candidate_chunks.add(chunk_id)
        
        if not candidate_chunks:
            for theme_chunks in self.theme_index.values():
                for page_id in theme_chunks:
                    chunk_id = page_id.replace('_P', '_C')
                    candidate_chunks.add(chunk_id)
        
        return candidate_chunks


class LightRAGRetriever:
    """LightRAG retrieval with cosine similarity via embeddings."""
    
    def __init__(self, lightrag_index_path: str, chunks_path: str):
        self.lightrag_index_path = lightrag_index_path
        self.chunks_path = chunks_path
        self._load_data()
    
    def _load_data(self):
        """Load LightRAG index and chunks."""
        # Load KV store text chunks
        kv_store_path = Path(self.lightrag_index_path) / 'kv_store_text_chunks.json'
        with open(kv_store_path, 'r') as f:
            kv_data = json.load(f)
        
        # Load VDB chunks (embeddings)
        vdb_path = Path(self.lightrag_index_path) / 'vdb_chunks.json'
        with open(vdb_path, 'r') as f:
            vdb_data = json.load(f)
        
        # Load chunks metadata
        with open(self.chunks_path, 'r') as f:
            chunks_data = json.load(f)
        
        self.chunks = {c['chunk_id']: c for c in chunks_data['chunks']}
        self.kv_store = kv_data
        self.vdb_data = vdb_data
        
        # Build chunk_id to hash mapping
        self.hash_to_chunk_id = {}
        self.page_to_chunk = {}  # Map P001 -> C001
        for chunk_id, chunk_info in self.chunks.items():
            # Map page IDs (P001) to chunk IDs (C001)
            if '_P' in chunk_id:
                page_id = chunk_id
                chunk_id_c = chunk_id.replace('_P', '_C')
            else:
                page_id = chunk_id
                chunk_id_c = chunk_id
            
            self.page_to_chunk[page_id] = chunk_id
            
            for hash_id, kv_info in self.kv_store.items():
                if kv_info.get('source_id') == chunk_id:
                    self.hash_to_chunk_id[hash_id] = chunk_id
    
    def get_embedding(self, text: str, hash_id: str) -> list:
        """Get embedding for a chunk from VDB."""
        # Find embedding for this hash
        for item in self.vdb_data.get('data', []):
            if item.get('__id__') == hash_id:
                # In real implementation, embeddings would be stored
                # For now, return placeholder
                return [0.0] * 1024  # embedding_dim = 1024
        return None
    
    def cosine_similarity(self, vec1: list, vec2: list) -> float:
        """Compute cosine similarity between two vectors."""
        import math
        norm1 = math.sqrt(sum(x*x for x in vec1))
        norm2 = math.sqrt(sum(x*x for x in vec2))
        if norm1 == 0 or norm2 == 0:
            return 0.0
        dot = sum(a*b for a, b in zip(vec1, vec2))
        return dot / (norm1 * norm2)
    
    def retrieve(self, query: str, candidate_chunk_ids: Set[str], top_k: int = 10) -> List[Dict]:
        """Retrieve relevant chunks using simple keyword matching and ranking."""
        results = []
        
        clean_query = query.lower().strip('?').strip('!').strip('.')
        query_terms = [t.strip('?').strip('!').strip('.') for t in clean_query.split()]
        
        for hash_id, chunk_info in self.kv_store.items():
            source_id = chunk_info.get('source_id')
            if source_id not in candidate_chunk_ids:
                continue
            
            text = chunk_info.get('content', '')
            text_lower = text.lower()
            
            matches = sum(1 for term in query_terms if term in text_lower)
            term_score = matches / len(query_terms) if query_terms else 0
            
            phrase_bonus = 1.0 if clean_query in text_lower else 0.0
            
            first_match = text_lower.find(clean_query)
            position_score = 0.5 if first_match != -1 and first_match < 500 else 0.0
            
            total_score = term_score + phrase_bonus * 0.5 + position_score * 0.2
            
            if total_score > 0:
                results.append({
                    'chunk_id': source_id,
                    'hash_id': hash_id,
                    'text': text,
                    'raw_score': total_score,
                    'metadata': self.chunks.get(source_id, {})
                })
        
        # Sort by score
        results.sort(key=lambda x: x['raw_score'], reverse=True)
        
        return results[:top_k]


class Reranker:
    """Reranking using cross-encoder/ms-marco-MiniLM-L-6-v2."""
    
    def __init__(self, model_name: str = 'cross-encoder/ms-marco-MiniLM-L-6-v2'):
        self.model_name = model_name
        self.model = None
        self._load_model()
    
    def _load_model(self):
        """Load cross-encoder model."""
        if CROSS_ENCODER_AVAILABLE:
            try:
                self.model = CrossEncoder(model_name)
                print(f"Loaded cross-encoder model: {model_name}")
            except Exception as e:
                print(f"Failed to load cross-encoder: {e}")
                self.model = None
        else:
            print("sentence-transformers not available. Using fallback scoring.")
    
    def rerank(self, query: str, candidates: List[Dict], top_k: int = 3) -> List[Dict]:
        """Rerank candidates and return top-k."""
        if not candidates:
            return []
        
        if self.model is None:
            # Fallback: use raw_score for reranking
            return self._fallback_rerank(candidates, top_k)
        
        # Prepare pairs for cross-encoder
        pairs = [(query, cand['text'][:512]) for cand in candidates]  # Truncate for model
        
        try:
            scores = self.model.predict(pairs)
            
            # Attach scores and sort
            for i, cand in enumerate(candidates):
                cand['rerank_score'] = float(scores[i])
            
            candidates.sort(key=lambda x: x['rerank_score'], reverse=True)
            
        except Exception as e:
            print(f"Reranking failed: {e}")
            return self._fallback_rerank(candidates, top_k)
        
        return candidates[:top_k]
    
    def _fallback_rerank(self, candidates: List[Dict], top_k: int) -> List[Dict]:
        """Fallback reranking using raw scores."""
        candidates.sort(key=lambda x: x.get('raw_score', 0), reverse=True)
        return candidates[:top_k]


class EvidencePacker:
    """Package retrieval results into evidence pack format."""
    
    def __init__(self):
        pass
    
    def pack(self, reranked_candidates: List[Dict], query: str) -> List[Dict]:
        """Convert candidates to evidence pack format."""
        evidence_list = []
        
        for cand in reranked_candidates:
            metadata = cand.get('metadata', {})
            
            # Calculate confidence based on rerank score
            confidence = self._calculate_confidence(cand)
            
            # Extract quote (first 200 chars of relevant text)
            quote = self._extract_quote(cand['text'], query)
            
            evidence = {
                'chunk_id': cand['chunk_id'],
                'author': metadata.get('author', 'Unknown'),
                'page': metadata.get('page', 0),
                'section': metadata.get('section', 'Unknown'),
                'themes': metadata.get('themes', []),
                'citation_refs': metadata.get('citation_refs', []),
                'quote': quote,
                'confidence': confidence
            }
            
            evidence_list.append(evidence)
        
        return evidence_list
    
    def _calculate_confidence(self, candidate: Dict) -> float:
        """Calculate confidence score."""
        raw_score = candidate.get('raw_score', 0)
        rerank_score = candidate.get('rerank_score', 0)
        
        effective_score = rerank_score if rerank_score > 0 else raw_score
        
        if effective_score >= 2.0:
            confidence = 0.85
        elif effective_score >= 1.5:
            confidence = 0.75
        elif effective_score >= 1.0:
            confidence = 0.65
        elif effective_score >= 0.5:
            confidence = 0.50
        else:
            confidence = max(0.15, effective_score)
        
        return round(confidence, 2)
    
    def _extract_quote(self, text: str, query: str, max_length: int = 300) -> str:
        """Extract relevant quote from text."""
        text_lower = text.lower()
        query_lower = query.lower()
        
        # Find query term position
        for term in query_lower.split():
            pos = text_lower.find(term)
            if pos != -1:
                # Extract around the match
                start = max(0, pos - 50)
                end = min(len(text), pos + max_length)
                
                quote = text[start:end]
                
                # Clean up the quote
                if start > 0:
                    quote = '...' + quote
                if end < len(text):
                    quote = quote + '...'
                
                return quote
        
        # Fallback: first max_length chars
        return text[:max_length] + ('...' if len(text) > max_length else '')


class Phase6Retriever:
    """Main Phase 6 retrieval pipeline."""
    
    def __init__(self, 
                 theme_index_path: str,
                 chunks_path: str,
                 lightrag_index_path: str):
        
        self.query_parser = QueryParser(theme_index_path)
        self.graph_traversal = GraphTraversal(theme_index_path)
        self.lightrag_retriever = LightRAGRetriever(lightrag_index_path, chunks_path)
        self.reranker = Reranker()
        self.evidence_packer = EvidencePacker()
    
    def retrieve(self, query: str, top_k: int = 3) -> Dict[str, Any]:
        """
        Execute the full Phase 6 retrieval pipeline.
        
        Args:
            query: User query string
            top_k: Number of evidence items to return
        
        Returns:
            Dict containing evidence pack and metadata
        """
        # Step 1: Parse query (rule-based)
        parsed = self.query_parser.parse(query)
        print(f"[Phase 6] Parsed query - themes: {parsed['themes']}, authors: {parsed['authors']}")
        
        # Step 2: Graph traversal (find candidate chunks via theme_index.json)
        candidate_chunks = self.graph_traversal.find_candidates(
            parsed['themes'], 
            parsed['authors']
        )
        print(f"[Phase 6] Found {len(candidate_chunks)} candidate chunks")
        
        # Step 3: LightRAG retrieval (within candidate set)
        candidates = self.lightrag_retriever.retrieve(
            query, 
            candidate_chunks, 
            top_k=10
        )
        print(f"[Phase 6] Retrieved {len(candidates)} candidates")
        
        # Step 4: Reranking (cross-encoder/ms-marco-MiniLM-L-6-v2)
        reranked = self.reranker.rerank(query, candidates, top_k=top_k)
        print(f"[Phase 6] Reranked to {len(reranked)} results")
        
        # Step 5: Evidence pack output
        evidence_pack = self.evidence_packer.pack(reranked, query)
        print(f"[Phase 6] Packaged {len(evidence_pack)} evidence items")
        
        # Classify confidence levels
        for i, evidence in enumerate(evidence_pack):
            conf = evidence['confidence']
            if conf >= 0.65:
                confidence_level = 'normal'
            elif conf >= 0.40:
                confidence_level = 'low_confidence'
            else:
                confidence_level = 'rejected'
                # Remove rejected items
                if confidence_level == 'rejected':
                    print(f"[Phase 6] Rejected evidence below threshold: chunk_id={evidence['chunk_id']}, confidence={conf}")
        
        # Filter to only normal confidence
        filtered_evidence = [e for e in evidence_pack if e['confidence'] >= 0.40]
        
        return {
            'query': query,
            'parsed_themes': parsed['themes'],
            'parsed_authors': parsed['authors'],
            'candidate_count': len(candidate_chunks),
            'evidence_pack': filtered_evidence,
            'total_results': len(filtered_evidence)
        }


def main():
    """Main function to run the retrieval system."""
    # Paths
    theme_index_path = '/home/arshhtripathi/research-swarm/graphs/theme_index.json'
    chunks_path = '/home/arshhtripathi/research-swarm/chunks.json'
    lightrag_index_path = '/home/arshhtripathi/research-swarm/lightrag_index/'
    
    # Initialize Phase 6 retriever
    retriever = Phase6Retriever(
        theme_index_path=theme_index_path,
        chunks_path=chunks_path,
        lightrag_index_path=lightrag_index_path
    )
    
    # Test query
    query = "What does the paper say about Gandhi?"
    
    print(f"\n{'='*60}")
    print(f"Phase 6 Retrieval System")
    print(f"Query: {query}")
    print(f"{'='*60}\n")
    
    # Execute retrieval
    result = retriever.retrieve(query, top_k=3)
    
    # Print results
    print(f"\n{'='*60}")
    print("EVIDENCE PACK")
    print(f"{'='*60}\n")
    
    print(json.dumps(result['evidence_pack'], indent=2))
    
    return result


if __name__ == '__main__':
    main()