# Research Swarm Pipeline — Implementation Roadmap

**Last Updated:** 2026-05-26
**Status:** Ready for Implementation

---

## MISSION

Build an academic research-writing system that:
1. Writes grounded academic content
2. Knows exactly where every sentence came from
3. Preserves source provenance: sentence → chunk → paper → page → URL
4. Tracks citation lineage: Priyanka → Bruschi
5. Minimizes token burn
6. Scales from 1 paper → many papers

---

## CORE PRINCIPLES

1. **NO SENTENCE WITHOUT EVIDENCE** — Every generated claim maps to evidence
2. **RELATIONSHIP-FIRST RETRIEVAL** — Citation relationships first, semantic inside narrowed candidate space
3. **CHEAP MODELS RETRIEVE / SMART MODELS WRITE**
4. **SMALL VERTICAL SLICE FIRST** — Never start with 30 papers

---

## PHASE 0 — VERTICAL SLICE

**Dataset:** 1 Priyanka paper + 3–10 bibliography references

**Goal:** Validate entire pipeline with traceable citations

**Success:** Writer generates one grounded section with traceable citations

---

## PHASE 1 — SOURCE INGESTION

**Agent:** Scout (low complexity)

**Goal:** Build trusted source inventory

**Tasks:**
- Ingest Priyanka paper
- Extract bibliography
- Resolve URLs (DOI, publisher, arXiv, PDF URL)
- Download PDFs
- Save metadata

**Output Schema:**
```json
{
  "source_id": "PRI_001",
  "title": "...",
  "authors": ["Priyanka Gupta"],
  "year": null,
  "url": "...",
  "pdf_path": "sources/PRI_001.pdf",
  "resolved": true
}
```

**Error Handling:**
- Download retry: 3x
- If unresolved: `resolved: false` + `raw_reference: "Bruschi, Isabella, 2010..."`

**Deliverable:** `sources/metadata.json`

---

## PHASE 2 — PDF EXTRACTION + CLEANING

**Agent:** Explore (medium complexity)

**Goal:** Convert PDFs into normalized text

**Tasks:**
- Extract text (PyMuPDF or pdfplumber)
- Remove OCR junk
- Remove headers/footers/page numbers
- Preserve sections
- Preserve page mapping

**Output:** `corpus/SRC_XXX/cleaned.txt`

**Acceptance:** Readable text, minimal noise, page traceability survives

---

## PHASE 3 — CITATION GRAPH CONSTRUCTION

**Agent:** Explore (medium complexity)
**Runs:** Parallel with Phase 4

**Goal:** Understand citation relationships

**Outputs:**

### A. Citation Graph
```json
{
  "citation_graph.json": {
    "PRI_001": { "cites": ["REF_017", "REF_021"] }
  }
}
```

### B. References Database
```json
{
  "REF_017": {
    "author": "Isabella Bruschi",
    "title": "Partition in Fiction Gendered Perspectives",
    "year": 2010,
    "publisher": "Atlantic Publishers",
    "url": null,
    "resolved": false
  }
}
```

### C. Theme Graph + Index

**Theme Graph** (`theme_graph.json`):
```json
{
  "chunk_id": "PRI_001_C021",
  "themes": ["Gandhi", "partition", "freedom movement"]
}
```

**Theme Index** (`theme_index.json`) — inverted index for fast lookup:
```json
{
  "Gandhi": ["PRI_001_C021", "PRI_001_C029"],
  "partition": ["PRI_001_C004", "REF_017_C008"]
}
```

**Theme Extraction Method:** Hybrid
- Curated seed vocabulary (10–15 academic themes)
- Constrained LLM expansion (max 2 new themes per chunk)
- Embedding validation (similarity >= 0.75)
- Max themes per chunk: 5

**Theme Vocabulary (Seed):**
```
partition, Gandhi, communal riots, violence, migration, gender,
freedom movement, nationalism, memory, identity, partition literature, postcolonialism
```

**Rule:** `max_lineage_depth = 2` — trace PRI_001 → REF_017, not beyond REF_017's citations

---

## PHASE 4 — CHUNKING + PROVENANCE

**Agent:** Explore (medium complexity)
**Runs:** Parallel with Phase 3

**Goal:** Create retrievable academic chunks

**Chunking Rules:**
- Soft target: 1000 tokens
- Hard max: 1500 tokens
- Overlap: 50 tokens
- Never split mid-sentence
- Preserve paragraph boundary
- Attach section title as metadata

**Chunk Schema:**
```json
{
  "chunk_id": "PRI_001_C021",
  "source_id": "PRI_001",
  "author": "Priyanka Gupta",
  "page": 4,
  "section": "Partition discourse",
  "url": "...",
  "themes": ["Gandhi", "partition", "freedom movement"],
  "citation_refs": ["REF_017"],
  "text": "..."
}
```

**Critical Rule:** Every chunk carries full provenance

**Deliverable:** `chunks.json`

---

## PHASE 5 — LIGHTRAG INDEXING

**Agent:** RAG (medium complexity)

**Goal:** Store corpus for retrieval

**Implementation:** HKUDS LightRAG (official)

**IMPORTANT:** LightRAG does NOT own provenance — metadata is injected externally

**Embedding Model:** `intfloat/multilingual-e5-large` via OpenRouter
- 1024 dimensions
- English-only corpus (but model supports multilingual)
- Fallback: `sentence-transformers/multi-qa-mpnet-base-dot-v1`

**LightRAG Stores:**
- `content` = chunk text
- `metadata` = chunk_id, author, page, url, citation_refs, source_id, section, themes

**Rule:** Metadata must survive retrieval — writer always receives text + provenance

---

## PHASE 6 — RELATIONSHIP-FIRST RETRIEVAL

**Agent:** RAG (medium complexity)

**Goal:** Retrieve evidence pack

**Pipeline:**
```
query
↓
rule-based query parser (extract themes, authors, citation refs)
↓
dynamic traversal over pre-built citation/theme graph
↓
candidate neighborhood (via theme_index.json inverted lookup)
↓
semantic retrieval (LightRAG, but only within candidate set)
↓
light rerank (cross-encoder)
↓
evidence pack
```

**Query Parser:** Rule-based (non-LLM)
- Extract noun phrases, author names, citation refs, entities
- No LLM call at query time

**Reranking Model:** `cross-encoder/ms-marco-MiniLM-L-6-v2` (HuggingFace)
- Two-stage: top-50 candidates → rerank → top-3-5

**Confidence Thresholds:**
- >= 0.65: normal
- 0.40–0.65: `low_confidence: true`
- < 0.40: reject, return empty

**Output — Evidence Pack:**
```json
{
  "chunk_id": "PRI_001_C021",
  "author": "Priyanka Gupta",
  "page": 4,
  "url": "...",
  "citation_refs": ["REF_017"],
  "quote": "Gandhi's non-cooperation movement (1920-22)...",
  "confidence": 0.82
}
```

**Failure:** `status: empty` — writer must escalate

---

## PHASE 7 — CITATION EXPANSION

**Agent:** Citation Expansion (medium complexity)

**Goal:** Expand references when writer needs cited source content

**Trigger:** Writer requests `expand REF_017`

**Pipeline:**
```
1. Check: Is REF_017 in corpus?
2. If no: Fetch PDF → extract → chunk → index → re-retrieve
3. If yes: Skip to re-retrieve
```

**If Unavailable:**
```json
{
  "unverified": true,
  "warning": "REF_017 could not be fetched"
}
```

**Writer Rule:** Never hallucinate missing citations — must flag or skip

**Purpose:** Prevents citation laundering

---

## PHASE 8 — WRITER AGENT

**Agent:** AcademicWriterAgent (high complexity)

**Goal:** Generate grounded academic writing

**Input:**
- Evidence Pack
- References database (for proper citation display)

**Rules:**
1. No unsupported claims
2. No invented citations
3. Every paragraph tied to evidence
4. Direct attribution preferred

**Good Attribution:**
> According to Priyanka Gupta...

**Better Attribution:**
> Isabella Bruschi argues that..., later discussed by Priyanka Gupta.

**Writer Must Answer:** "Where did this sentence come from?"

**System Prompt Override:** Configure AcademicWriterAgent with Phase 8 rules

---

## PHASE 9 — VALIDATION + FEEDBACK LOOP

**Agent:** Orchestrator

**Goal:** Detect silent failures

**Validation:**
- Sample: 50 sentences (stratified)
  - 20 high confidence
  - 20 medium confidence
  - 10 citation-expanded
- Selection: Random stratified

**Checks Per Sentence:**
- Evidence exists?
- Chunk exists?
- Page exists?
- URL exists?
- Citation resolves?
- Claim supported by chunk?

**Metrics:**
- `support_rate >= 95%`
- `false_citation_rate <= 2%`

**If Fail:**
- Expand citation
- Re-index
- Retry validation

---

## AGENT RESPONSIBILITIES

| Agent | Complexity | Phases |
|-------|------------|--------|
| **Scout** | Low | Phase 1: Download, URL resolution, source inventory |
| **Explore** | Medium | Phase 2: PDF extraction, cleaning |
| **Explore** | Medium | Phase 3: Citation graph, theme graph construction |
| **Explore** | Medium | Phase 4: Chunking + provenance |
| **RAG** | Medium | Phase 5: LightRAG indexing |
| **RAG** | Medium | Phase 6: Relationship-first retrieval |
| **Citation Expansion** | Medium | Phase 7: Citation expansion |
| **AcademicWriterAgent** | High | Phase 8: Grounded synthesis |
| **Orchestrator** | — | Phase 9: Validation + feedback |

---

## FINAL STACK

| Component | Model | Provider |
|-----------|-------|----------|
| **Embedding** | `intfloat/multilingual-e5-large` | OpenRouter |
| **Reranker** | `cross-encoder/ms-marco-MiniLM-L-6-v2` | HuggingFace |
| **Writer LLM** | `qwen/qwen3-72B-Instruct` | OpenRouter |
| **RAG Infra** | LightRAG (HKUDS) | Local |
| **Extraction** | PyMuPDF or pdfplumber | Local |
| **Query Parser** | Rule-based (regex + NLP) | Local |

**⚠️ SETUP:** Set `OPENROUTER_API_KEY` as environment variable before running. Never store in code.

---

## ARCHITECTURE DIAGRAM

```
Phase 1: Source Ingestion (Scout)
         ↓
Phase 2: PDF Extraction (Explore)
         ↓
┌────────┴────────┐
│ Phase 3         │ ←── Parallel
│ Citation Graph  │
│ Theme Graph     │
└────────┬────────┘
         ||
┌────────┴────────┐
│ Phase 4         │ ←── Parallel
│ Chunking        │
│ Provenance      │
└────────┬────────┘
         ↓
Phase 5: LightRAG Indexing (RAG)
         ↓
Phase 6: Relationship-First Retrieval (RAG)
         ↓
Phase 7: Citation Expansion (if needed)
         ↓
Phase 8: Writer Agent → Grounded Output
         ↓
Phase 9: Validation + Feedback Loop
```

---

## PROVENANCE CHAIN

```
Sentence
  → Evidence Pack (Phase 6)
    → chunk_id
      → source_id
        → author
        → page
        → url
        → citation_refs[]
          → Reference (Phase 3)
            → author
            → title
            → year
            → url (or raw_reference)
```

**Example:**
```
"Gandhi's non-cooperation movement was based on Satyagraha."
  → chunk_id: PRI_001_C021
    → author: Priyanka Gupta
    → page: 4
    → url: [Priyanka paper URL]
    → citation_refs: [REF_017]
      → REF_017: Isabella Bruschi, "Partition in Fiction Gendered Perspectives", 2010
```

---

## FOLDER STRUCTURE

```
research_pipeline/
├── sources/
│   ├── metadata.json
│   ├── PRI_001.pdf
│   └── REF_017.pdf
├── corpus/
│   ├── PRI_001/
│   │   └── cleaned.txt
│   └── REF_017/
│       └── cleaned.txt
├── graphs/
│   ├── citation_graph.json
│   ├── theme_graph.json
│   └── theme_index.json
├── references.json
├── chunks.json
├── lightrag_index/
│   └── [LightRAG persistence]
└── output/
    └── evidence_packs/
```

---

## OPEN QUESTIONS (Resolved)

| Question | Resolution |
|----------|------------|
| Theme vocabulary | Hybrid: curated seed + constrained LLM expansion (max 2 new, similarity >= 0.75) |
| Inverted index | Separate file (`theme_index.json`) |
| LightRAG + graph integration | Metadata-first, graph separate from LightRAG |
| Query parser | Rule-based (non-LLM) |
| Embedding model | `intfloat/multilingual-e5-large` |
| Reranker | `cross-encoder/ms-marco-MiniLM-L-6-v2` |
| Writer model | `qwen/qwen3-72B-Instruct` |
| Validation | 50-sentence stratified sample, 95% support threshold |
| Lineage depth | Max 2 levels |

---

## STATUS

| Phase | Status |
|-------|--------|
| Phase 0 | ✅ Planned |
| Phase 1 | ✅ Designed |
| Phase 2 | ✅ Designed |
| Phase 3 | ✅ Designed |
| Phase 4 | ✅ Designed |
| Phase 5 | ✅ Designed |
| Phase 6 | ✅ Designed |
| Phase 7 | ✅ Designed |
| Phase 8 | ✅ Designed |
| Phase 9 | ✅ Designed |

**Next Step:** Implementation of Phase 1 (Source Ingestion)

---

## VALIDATION PAPER

**Author:** Priyanka Gupta (Research Scholar, SMVDU, Katra, J&K)

**Sample Chunk:**
> "Gandhi's non-cooperation movement (1920-22), Civil Disobedience Movement (1930) and Quit India Movement (1942) were based on Satyagraha. Many novelists tried to bring out the issue of the freedom fight in their works."

**Reference:** Bruschi, Isabella. *Partition in Fiction Gendered Perspectives*. Atlantic Publishers: New Delhi. 2010. Print.
