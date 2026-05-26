# Research Swarm Pipeline — Simplified for Dissertation Writing

**Last Updated:** 2026-05-26
**Status:** Ready for Implementation (v2 — Simplified)

---

## MISSION

Build a dissertation-writing assistant that:
1. Generates full chapter-length academic content (6-8 pages per chapter)
2. Every sentence backed by evidence from source PDFs
3. Page-level provenance: every citation traceable to a specific page
4. Produces proper MLA-formatted dissertation chapters
5. Simple, maintainable RAG pipeline — no overengineering

---

## DISSERTATION TARGET STRUCTURE

Based on department pattern (chapter-style, not theoretical thesis):

### Preliminary Pages
1. Title Page
2. Declaration
3. Certificate
4. Acknowledgement
5. Abstract (~200-300 words)
6. Table of Contents

### Main Chapters
7. **Chapter I — Introduction** (~8-10 pages)
   - 1.1 Partition of India background
   - 1.2 About Khushwant Singh
   - 1.3 About the Novel *Train to Pakistan*
   - 1.4 About the Film Adaptation
   - 1.5 Aim/Objectives
   - 1.6 Research Method/Scope
   - 1.7 Thesis Statement

8. **Chapter II — Review of Literature** (~8-10 pages)
   - Existing scholarship on Partition literature
   - Humanism studies, violence representation, adaptation studies

9. **Chapter III — Partition and Violence** (~14-16 pages)
   - Communal conflict, riots, displacement
   - Novel vs film comparison

10. **Chapter IV — Humanism and Moral Conflict** (~14-16 pages)
    - Jugga's sacrifice, compassion, morality
    - Novel vs film comparison

11. **Chapter V — Adaptation Analysis** (~7-8 pages)
    - Novel to film: changes, omissions, cinematic techniques

12. **Conclusion** (~4-5 pages)
    - Summary, thesis return, no new arguments

### Reference Material
13. Works Cited (MLA format)

**Total: ~56-65 pages**

---

## CORE PRINCIPLES

1. **NO SENTENCE WITHOUT EVIDENCE** — Every claim maps to a chunk with page number
2. **SIMPLE RAG** — Semantic search over PDFs, no graph complexity
3. **CHEAP MODELS RETRIEVE / SMART MODELS WRITE**
4. **PAGE-LEVEL PROVENANCE** — Every citation: [author, page]
5. **FULL CHAPTERS** — Generate 6-8 page sections, not 3-paragraph samples

---

## SIMPLIFIED PIPELINE

```
Source PDFs (novel, film script, 10-15 secondary sources)
        ↓
PDF Extraction (PyMuPDF) → preserve page numbers
        ↓
Chunking (page-level or 500-token, preserve paragraph)
        ↓
Embedding + Vector Store (simple FAISS or sqlite-vector)
        ↓
Semantic Search (top-k relevant chunks)
        ↓
Evidence Pack (text + [author, page, source_id])
        ↓
Writer Agent (generates full chapter section)
        ↓
Output (chapter section with traceable citations)
```

---

## PHASE 1 — SOURCE INGESTION

**Goal:** Collect all PDFs for dissertation corpus

**Primary Sources (must have):**
- *Train to Pakistan* — Khushwant Singh (novel)
- *Train to Pakistan* film (directed by Pamela Rooks) — script/transcript
- Any critical edition with page numbers

**Secondary Sources (10-15 recommended):**
- Partition history books
- Adaptation studies
- Humanism in literature
- Academic articles on Khushwant Singh

**Output:** `sources/metadata.json`
```json
{
  "source_id": "NOV_001",
  "type": "primary",
  "title": "Train to Pakistan",
  "author": "Khushwant Singh",
  "year": 1956,
  "pdf_path": "sources/train_to_pakistan.pdf",
  "resolved": true
}
```

---

## PHASE 2 — PDF EXTRACTION

**Goal:** Convert PDFs to clean text with page mapping

**Tool:** PyMuPDF (fitz)

**Rules:**
- Preserve page numbers exactly
- Remove headers/footers/page numbers from text
- Keep paragraph structure intact
- Track: page_number → original_pdf_page

**Output:** `corpus/NOV_001/cleaned.txt`

---

## PHASE 3 — CHUNKING + PROVENANCE

**Goal:** Create retrievable chunks with full provenance

**Chunking Rules:**
- Page-level chunks (one page = one chunk, or split long pages)
- Soft max: 500 tokens per chunk
- Never split mid-sentence
- Attach metadata: source_id, author, page, section_title

**Chunk Schema:**
```json
{
  "chunk_id": "NOV_001_P004",
  "source_id": "NOV_001",
  "author": "Khushwant Singh",
  "page": 4,
  "section": "Chapter 1",
  "text": "The train came late at night...",
  "type": "primary"
}
```

**Deliverable:** `chunks.json`

---

## PHASE 4 — VECTOR INDEXING

**Goal:** Enable semantic search over chunks

**Tool:** Simple embedding + FAISS or sqlite-vector

**Embedding Model:** `sentence-transformers/multi-qa-mpnet-base-dot-v1` (fast, good for retrieval)

**Storage:**
- `chunks.json` — all chunk metadata + text
- `vector_index/` — FAISS index file

**No complex metadata in vector store** — keep provenance in chunks.json, not embedded.

---

## PHASE 5 — RETRIEVAL

**Goal:** Given a query/topic, return relevant evidence

**Pipeline:**
```
query/topic string
    ↓
semantic search (top-10 chunks by cosine similarity)
    ↓
filter by confidence threshold (>= 0.4)
    ↓
evidence pack
```

**Evidence Pack:**
```json
{
  "chunk_id": "NOV_001_P004",
  "author": "Khushwant Singh",
  "page": 4,
  "source_title": "Train to Pakistan",
  "type": "primary",
  "text": "The train came late at night...",
  "similarity": 0.82
}
```

**Confidence Thresholds:**
- >= 0.65: normal
- 0.40-0.65: low_confidence (flag)
- < 0.40: reject

---

## PHASE 6 — WRITER AGENT

**Goal:** Generate full chapter section from evidence packs

**Input:**
- Chapter topic/subheading
- Evidence packs (list of relevant chunks)
- Writing style: academic, formal, MLA tone

**Rules:**
1. Every paragraph must cite evidence: (Author, Page)
2. No invented citations
3. No unsupported claims
4. Quote directly when using exact phrases
5. Paraphrase with citation otherwise

**Output Format:**
```markdown
## 1.1 Partition of India

The historiography of the Partition reveals... (Singh, 4).

[Generated paragraph with citations...]

## 1.2 About the Author

[Next section...]
```

**Writer Model:** `qwen/qwen3-72B-Instruct` via OpenRouter

---

## PHASE 7 — VALIDATION

**Goal:** Verify citations before final output

**Checks per paragraph:**
- [ ] Every citation has matching chunk in chunks.json
- [ ] Page number exists in source
- [ ] Claim matches chunk text (not hallucinated)
- [ ] MLA format correct: (Author Page)

**If validation fails:**
- Re-run retrieval with lower threshold
- Flag for human review

---

## FOLDER STRUCTURE (SIMPLIFIED)

```
research-swarm/
├── sources/
│   ├── metadata.json
│   ├── train_to_pakistan.pdf      # Primary: novel
│   ├── film_transcript.pdf         # Primary: film
│   └── [secondary_sources].pdf    # Secondary: articles/books
├── corpus/
│   ├── NOV_001/
│   │   └── cleaned.txt
│   └── [secondary_chunks]/
├── chunks.json                    # All chunks with provenance
├── vector_index/                  # FAISS index
├── output/
│   ├── chapter_01_intro.md
│   ├── chapter_02_lit_review.md
│   └── ...
└── research_swarm_roadmap.md
```

---

## STACK

| Component | Choice | Notes |
|-----------|--------|-------|
| **PDF Extraction** | PyMuPDF | Fast, page-accurate |
| **Embedding** | `multi-qa-mpnet-base-dot-v1` | Optimized for Q&A retrieval |
| **Vector Store** | FAISS | Simple, local, fast |
| **Writer LLM** | `qwen/qwen3-72B-Instruct` | Via OpenRouter |
| **Citation Format** | MLA | (Author Page) |

---

## WHAT WE REMOVED (vs v1)

- ~~Citation graph construction~~ — not needed
- ~~Theme graph + theme_index~~ — overengineered
- ~~Relationship-first retrieval~~ — simple semantic search sufficient
- ~~LightRAG~~ — too complex for dissertation corpus
- ~~Cross-encoder reranker~~ — embedding similarity good enough
- ~~Phase 7 citation expansion~~ — manual citation lookup for unavailable refs
- ~~50-sentence stratified validation~~ — per-paragraph check sufficient

---

## STATUS

| Phase | Status | Notes |
|-------|--------|-------|
| Phase 1 | ⏳ Pending | Need: novel PDF, film transcript, 10-15 secondary sources |
| Phase 2 | ⏳ Pending | — |
| Phase 3 | ⏳ Pending | — |
| Phase 4 | ⏳ Pending | — |
| Phase 5 | ⏳ Pending | — |
| Phase 6 | ⏳ Pending | Writer agent to generate chapters |
| Phase 7 | ⏳ Pending | Validation before output |

---

## NEXT STEPS

1. **Collect PDFs**: Get the novel PDF + film transcript
2. **Download secondary sources**: Find 10-15 academic papers/books on Partition literature
3. **Run pipeline**: Extract → Chunk → Index → Retrieve → Write
4. **Generate Chapter 1 (Introduction)** as first output
5. **Iterate** for remaining chapters