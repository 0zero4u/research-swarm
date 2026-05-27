
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




   

TITLE Partition, Violence and Humanism in Khushwant Singh's Train to Pakistan: A Comparative Study of the Novel and Film Adaptation

Preliminary Pages
Title Page
Declaration
Certificate
Acknowledgement
Abstract (~200-300 words)
Table of Contents
Main Chapters
Chapter I — Introduction (~8-10 pages)

1.1 Partition of India background
1.2 About Khushwant Singh
1.3 About the Novel Train to Pakistan
1.4 About the Film Adaptation
1.5 Aim/Objectives
1.6 Research Method/Scope
1.7 Thesis Statement
Chapter II — Review of Literature (~8-10 pages) 2.1 Partition Literature: Overview 2.2 Critical Studies on Train to Pakistan 2.3 Studies on Violence and Communalism 2.4 Studies on Humanism and Moral Crisis 2.5 Film Adaptation Studies 2.6 - Existing scholarship on Partition literature 2.7 Research Gap

Chapter III — Partition and Violence (~14-16 pages) Historical Violence in the Novel 3.2 Communal Breakdown in Mano Majra 3.3 Displacement and Refugee Trauma 3.4 Violence in the Film Adaptation 3.5 Comparative Analysis Chapter IV — Humanism and Moral Crisis (~14-16 pages)

Chapter IV — Humanism and Moral Conflict (~14-16 pages)

Jugga's sacrifice, compassion, morality
Novel vs film comparison
4.1 Jugga as the Humanist Figure 4.2 Compassion Amid Violence 4.3 Moral Crisis: Iqbal and Hukum Chand 4.4 Humanism in the Film Adaptation 4.5 Comparative Reading Chapter V — Adaptation Analysis (~7-8 pages)
Chapter V — Adaptation Analysis (~7-8 pages)

From Novel to Film 5.2 Omissions and Additions 5.3 Visual Representation of Violence 5.4 Cinematic Techniques 5.5 Limits of Adaptation

Novel to film: changes, omissions, cinematic techniques
Conclusion (~4-5 pages)

Summary, thesis return, no new arguments
Summary Major Findings Return to Thesis
Reference Material
Works Cited (MLA format ( refine improve nd correct it

Your outline is strong, but it has repetition, numbering issues, inconsistent chapter titles, and unclear section flow. I refined it into a more academic and thesis-ready structure with corrected headings, consistent numbering, better wording, and improved organization for an MA/BA dissertation.

TITLE
Train to Pakistan, Violence, and Humanism in Train to Pakistan: A Comparative Study of the Novel and Film Adaptation

Preliminary Pages
Title Page

Declaration

Certificate

Acknowledgement

Abstract (200–300 words)

Table of Contents

Chapter I — Introduction (8–10 Pages)
1.1 Historical Background: The Partition of India
Political and socio-historical context of the 1947 Partition

Causes and consequences of communal division

Violence, migration, and displacement

1.2 About Khushwant Singh
Life and literary background

Contribution to Partition literature

Themes and writing style

1.3 Introduction to the Novel Train to Pakistan
Plot overview

Major characters and setting (Mano Majra)

Major themes: violence, communalism, sacrifice, humanism

1.4 Introduction to the Film Adaptation
Overview of the film adaptation

Director, screenplay, and cinematic background

Relevance of adaptation to the study

1.5 Aim and Objectives of the Study
To analyze representations of Partition violence

To examine humanism and moral conflict in the novel and film

To compare literary and cinematic treatment of major themes

1.6 Research Methodology and Scope
Comparative textual and film analysis

Historical and literary approach

Scope and limitations of the study

1.7 Thesis Statement
Central argument of the dissertation

Chapter II — Review of Literature (8–10 Pages)
2.1 Overview of Partition Literature
Development and major themes of Partition writing

Key authors and texts

2.2 Critical Studies on Train to Pakistan
Scholarly interpretations of the novel

Themes of violence, nationalism, and identity

2.3 Studies on Violence and Communalism
Critical discussions on communal conflict and brutality in Partition literature

2.4 Studies on Humanism and Moral Crisis
Compassion, ethical conflict, sacrifice, and morality in literary criticism

2.5 Studies on Film Adaptation
Theories of adaptation

Literary texts adapted into films

2.6 Existing Scholarship on Train to Pakistan and Partition Narratives
Comparative overview of existing academic studies

2.7 Research Gap
What previous studies have not sufficiently explored

Justification for the present comparative study

Chapter III — Partition and Violence in Train to Pakistan (14–16 Pages)
3.1 Historical Violence in the Novel
Representation of Partition riots and brutality

Social and political dimensions of violence

3.2 Communal Breakdown in Mano Majra
Collapse of communal harmony

Hindu–Muslim–Sikh relationships

3.3 Displacement and Refugee Trauma
Forced migration and psychological suffering

Loss, fear, and displacement

3.4 Violence in the Film Adaptation
Visual portrayal of brutality and communal tension

Cinematic representation of trauma

3.5 Comparative Analysis of Violence in the Novel and Film
Similarities and differences in representation

Narrative versus visual impact

Chapter IV — Humanism and Moral Conflict (14–16 Pages)
4.1 Jugga as the Humanist Figure
Jugga’s transformation and sacrifice

Humanism in times of communal violence

4.2 Compassion Amid Violence
Human relationships during crisis

Love, empathy, and coexistence

4.3 Moral Crisis: Iqbal and Hukum Chand
Ethical dilemmas and political ambiguity

Crisis of responsibility and conscience

4.4 Humanism in the Film Adaptation
Representation of morality and compassion through cinematic devices

4.5 Comparative Reading of Humanism in the Novel and Film
Differences in characterization and moral emphasis

Visual versus textual representation of human values

Chapter V — Adaptation Analysis: From Novel to Film (7–8 Pages)
5.1 From Novel to Film: Adaptation Process
Transition from literary narrative to cinema

5.2 Omissions and Additions
Altered scenes, removed episodes, and new interpretations

5.3 Visual Representation of Violence and Emotion
Camera work, imagery, symbolism, and dramatic presentation

5.4 Cinematic Techniques and Narrative Style
Direction, screenplay, sound, editing, and mise-en-scène

5.5 Limits of Adaptation
Constraints of cinema in representing literary complexity

Challenges of translating Partition trauma to screen

Conclusion (4–5 Pages)
6.1 Summary of Major Findings
6.2 Return to the Thesis Statement
6.3 Final Reflections on Violence, Humanism, and Adaptation
Note: Avoid introducing new arguments in the conclusion. Focus on synthesis and interpretation.

Reference Material
Works Cited (MLA 9th Edition)
Include:

Primary texts (novel and film)

Books

Journal articles

Edited volumes

Reliable academic sources and dissertations

Bibliography (Optional, if required by university guidelines)



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

## PHASE 1 — DOWNLOADER AGENT

**Model:** `qwen/qwen3.5-plus` via OpenRouter

**Goal:** Download PDFs from URLs and convert to clean text

**Process:**
1. Receive list of URLs from user
2. Download each PDF
3. Extract text using PyMuPDF
4. Save to `corpus/{source_id}.txt`
5. Update `metadata.json` with status

**Output:** `corpus/*.txt` + `metadata.json`

**Folder Structure:**
```
corpus/
├── 001_train_to_pakistan.txt
├── 002_literature_review.txt
└── metadata.json
```

**Model Note:** Downloader uses qwen/qwen3.5-plus to handle complex URLs, retry logic, error handling.

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

**Embedder:** `qwen/qwen3-embedding-8b` via OpenRouter (1024 dimensions)
**Vector Store:** FAISS

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

| Component | Model | Notes |
|-----------|-------|-------|
| **Downloader** | `qwen/qwen3.5-plus` | OpenRouter |
| **PDF Extraction** | PyMuPDF | Fast, page-accurate |
| **Embedding** | `qwen/qwen3-embedding-8b` | OpenRouter, 1024 dim |
| **Vector Store** | FAISS | Simple, local, fast |
| **Writer LLM** | `qwen/qwen3-72B-Instruct` | OpenRouter |
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
| Phase 1 | ✅ Done | Downloader agent |
| Phase 2 | ✅ Done | Integrated in downloader (PyMuPDF) |
| Phase 3 | ✅ Done | Chunker agent (chunks.json) |
| Phase 4 | ✅ Done | Embedder (qwen3-embedding-8b → FAISS) |
| Phase 5 | ✅ Done | RAG retriever (FAISS + rag_retriever_skill) |
| Phase 6 | ✅ Done | AcademicWriterAgent (calls rag-pull internally, hybrid citations) |
| Phase 7 | ✅ Done | Humanizer agent (29 AI pattern categories) |
| Phase 8 | ✅ Done | Citation auditor |

---

## NEXT STEPS

1. **Collect PDFs**: Get the novel PDF + film transcript
2. **Download secondary sources**: Find 10-15 academic papers/books on Partition literature
3. **Run pipeline**: Extract → Chunk → Index → Query (rag_retriever_skill) → Write ([B_XXX]) → Format → Humanize → Audit
4. **Generate Chapter 1 (Introduction)** as first output
5. **Iterate** for remaining chapters
