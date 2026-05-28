# Research Swarm — Agent Architecture

**Last Updated:** 2026-05-26

---

## Pipeline Overview

```
URLs → Downloader → Chunker → Embedder → FAISS Index
                                      ↓
Query → rag_retriever_skill.py → Structured Evidence Blocks [B_XXX]
                                      ↓
AcademicWriterAgent (calls rag-pull internally) → hybrid citations [B_XXX]
                                      ↓
Formatter → HumanizerAgent → Citation Auditor → PASS
```

## Citation Formats

| Format | Example | Use |
|--------|---------|-----|
| Block | `[B_001]` | Primary — from rag_retriever evidence blocks |
| Hybrid | `[002_P001C002:(Charyulu 2019, p. 1)]` | Writer can also use |
| MLA | `(Charyulu 2019, p. 1)` | After formatting |

---

## Agents

### Orchestrator (Sisyphus)
- **Role:** Main coordinator, delegates to sub-agents
- **Model:** minimax-m2.7
- **Responsibilities:**
  - Parse user requests
  - Delegate tasks to appropriate sub-agents
  - Monitor progress
  - Handle errors and retries

---

## Sub-Agents

### 1. Downloader Agent
| Property | Value |
|-----------|-------|
| **File** | `downloader.py` |
| **Model** | `qwen/qwen3.5-plus` (OpenRouter) |
| **Phase** | Phase 1 |
| **Input** | List of URLs |
| **Output** | `corpus/*.txt` + `metadata.json` |

**Responsibilities:**
- Download PDFs from URLs
- Extract text using PyMuPDF
- Save to corpus directory
- Track download status

**CLI:**
```bash
python3 downloader.py --urls "url1,url2"
python3 downloader.py --input urls.txt
```

---

### 2. Chunker Agent
| Property | Value |
|-----------|-------|
| **File** | `chunker.py` |
| **Model** | None (algorithmic) |
| **Phase** | Phase 3 |
| **Input** | `corpus/*.txt` |
| **Output** | `chunks/chunks.json` |

**Responsibilities:**
- Read text files from corpus
- Split into page-level chunks
- Preserve sentence boundaries
- Attach provenance metadata (source_id, page, chunk_id)

**CLI:**
```bash
python3 chunker.py              # Process all
python3 chunker.py --source 001 # Specific source
python3 chunker.py --resume      # Resume interrupted
```

**Chunk Schema:**
```json
{
  "chunk_id": "001_P001C001",
  "source_id": "001",
  "source_filename": "paper.txt",
  "author": "Shikha and Charyulu",
  "title": "Khushwant Singh Novel Train to Pakistan...",
  "year": "2019",
  "journal": "Journal of Advances and Scholarly Researches",
  "url": "https://doi.org/...",
  "page": 1,
  "text": "...",
  "token_count": 250
}
```

---

### 3. Embedder Agent (TODO)
| Property | Value |
|-----------|-------|
| **File** | `embedder.py` |
| **Model** | `qwen/qwen3-embedding-8b` (OpenRouter) |
| **Phase** | Phase 4 |
| **Input** | `chunks/chunks.json` |
| **Output** | `vector_index/*.faiss` |

**Responsibilities:**
- Embed chunks using qwen3-embedding-8b
- Store vectors in FAISS index
- Map chunk_id to vector index

---

### 4. Retriever Agent (TODO)
| Property | Value |
|-----------|-------|
| **File** | `retriever.py` |
| **Model** | None (algorithmic) |
| **Phase** | Phase 5 |
| **Input** | Query + `vector_index/` |
| **Output** | Evidence pack |

**Responsibilities:**
- Semantic search over vectors
- Return top-k relevant chunks
- Package as evidence pack

**Note:** Requires `faiss-cpu` and `requests` — use the venv: `/tmp/rs-venv/bin/python retriever.py`

---

### 5. RAG Pull Skill
| Property | Value |
|-----------|-------|
| **File** | `rag_retriever_skill.py` |
| **Model** | `qwen/qwen3-embedding-8b` (OpenRouter) |
| **Phase** | Phase 5 |
| **Input** | Topic/query string |
| **Output** | Structured evidence blocks with `[B_XXX]` IDs |

**How it works:** Agent calls `rag_retriever_skill.py` internally, receives structured blocks with provenance, citations, and claims. The skill wraps FAISS retriever.

**Evidence Block Schema:**
```json
{
  "block_id": "B_001",
  "chunk_id": "002_P001C002",
  "source": "Charyulu 2019",
  "page": 1,
  "text": "The rail route in Train to Pakistan...",
  "score": 0.71,
  "claims": ["railroad as central symbol"]
}
```

**CLI:**
```bash
python3 rag_retriever_skill.py "ghost train symbolism partition violence"
python3 rag_retriever_skill.py "humanism values" --top-k 60 --min-confidence 0.30
```

---

### 6. Writer Agent
| Property | Value |
|-----------|-------|
| **Agent** | `AcademicWriterAgent` (OpenCode sub-agent) |
| **File** | `~/.config/opencode/agents/academic-writer-agent.md` |
| **Model** | `minimax-m2.5` via OpenCode task |
| **Phase** | Phase 6 |
| **Input** | Topic + Evidence pack |
| **Output** | Chapter section with MLA citations |

**How it works:** Invoked via OpenCode `task(category="writing")` with `academic-writing` + `humanizer` skill chain. The `writer.py` script is a fallback wrapper (minimax/m2.7 has null-content issues via urllib).

**Responsibilities:**
- Generate academic prose in formal scholarly voice
- Write MLA citations directly (author-in-text style: `Author (Year, p. #)`)
- Apply skill chain: academic-writing → humanizer → formal-writing

**Output Format:**
```markdown
## 1.1 Partition of India

The historiography... Charyulu (2019, p. 47).

## 1.2 About the Author

[Next section...]
```

**CLI (via OpenCode task):**
```bash
# Primary method — use task() with AcademicWriterAgent
task(category="writing", load_skills=["academic-writing", "humanizer"], prompt="...")
```

**E2E Test (2026-05-26):** ghost-train-symbolism chapter written, humanized, audited — 1 MLA citation detected (Charyulu 2019), PASS.

---

### 7. Formatter Agent
| Property | Value |
|-----------|-------|
| **File** | `formatter.py` |
| **Model** | None (algorithmic) |
| **Phase** | Phase 6b |
| **Input** | Writer output with `[chunk_id]` citations |
| **Output** | Chapter with MLA citations `(filename, Author Year, p. #)` |

**Responsibilities:**
- Convert `[chunk_id]` citations to MLA format
- Look up author/title/year from chunks.json
- Format: `(filename, Author Year, p. #)`

**CLI:**
```bash
python3 formatter.py --input output/draft.md
python3 formatter.py --input output/draft.md --output output/final.md
```

---

### 8. Humanizer Agent
| Property | Value |
|-----------|-------|
| **File** | `humanizer_agent.py` (wrapper) |
| **Model** | `qwen/qwen3.5-plus` via OpenCode task+skill |
| **Phase** | Phase 7 |
| **Input** | Formatted chapter with MLA citations |
| **Output** | Humanized chapter (`_h.md`) |

**How it works:** Invoked via OpenCode task with `humanizer` skill loaded. The skill applies 29 AI-pattern categories in a 4-pass workflow. The Python wrapper is a lightweight file-based interface — the actual work happens inside OpenCode's agent system.

**Responsibilities:**
- Remove 29 categories of AI writing patterns
- Apply 4-pass humanization workflow
- Preserve all MLA citations and headings
- Add natural voice and varied sentence rhythm

**AI Patterns Removed:**
- Significance inflation, -ing fillers, copula avoidance
- Promotional language, vague attributions, rule of three
- Negative parallelisms, em dash overuse, passive voice
- Excessive hedging, filler phrases, AI vocabulary
- Curly quotes, emojis, title case headings
- Generic conclusions, signposting, chatbot artifacts

**CLI (via OpenCode task):**
```bash
# Via OpenCode task + humanizer skill (RECOMMENDED)
task(category="writing", load_skills=["humanizer"], --input output/chapters/final.md)

# Via Python wrapper (writes to _h.md suffix)
python3 humanizer_agent.py --input output/chapters/final.md
python3 humanizer_agent.py --input output/chapters/final.md --output output/chapters/chapter_h.md
```

**E2E Test (2026-05-26):** `ghost-train.md` → `ghost-train_h.md` — 5/5 citations valid, prose natural, auditor PASS.

---

### 9. Citation Auditor Agent
| Property | Value |
|-----------|-------|
| **File** | `auditor.py` |
| **Model** | `qwen/qwen3.5-plus` (OpenRouter) |
| **Phase** | Phase 8 |
| **Input** | Writer output |
| **Output** | Validation report |

**Responsibilities:**
- Verify citations exist in chunks
- Check MLA format
- Flag hallucinated citations

---

## Data Flow

```
1. User provides URLs
         ↓
2. Downloader → corpus/*.txt + metadata.json
         ↓
3. Chunker → chunks/chunks.json
         ↓
4. Embedder → vector_index/*.faiss
         ↓
5. Retriever ← User Query → Evidence Pack
         ↓
6. AcademicWriterAgent (calls rag-pull internally) → Draft with [B_XXX] citations
         ↓
7. HumanizerAgent (task+skill) → Natural-sounding prose
         ↓
8. Citation Auditor → Validation Report
         ↓
8. Human Review → Final Output
```

---

## Directory Structure

```
research-swarm/
├── *.py                    # Pipeline scripts (downloader, chunker, embedder, retriever, formatter, auditor, humanizer_agent)
├── ~/.config/opencode/agents/
│   ├── academic-writer-agent.md   # AcademicWriterAgent (primary writer)
│   ├── humanizer-agent.md         # HumanizerAgent definition
│   └── research-agent.md          # ResearchAgent (RAG queries)
├── corpus/                 # Downloaded text (local only)
│   ├── *.txt
│   └── metadata.json
├── chunks/                 # Chunked data (local only)
│   └── chunks.json
├── vector_index/           # FAISS index (local only)
│   └── *.faiss
├── output/
│   ├── chapters/          # Generated chapters
│   └── audit/             # Audit reports
├── research_swarm_roadmap.md
└── AGENTS.md              # This file
```

---

## Model Stack

| Agent | Model | Provider | Purpose |
|-------|-------|----------|---------|
| Orchestrator | minimax-m2.7 | Local | Coordination |
| Downloader | qwen3.5-plus | OpenRouter | URL handling |
| Chunker | None | — | Text processing |
| Embedder | qwen3-embedding-8b | OpenRouter | Vectorization (4096 dim) |
| Retriever | None | — | Search |
| Writer | minimax-m2.5 | OpenCode task | Generation (AcademicWriterAgent) |
| RAG Retriever | qwen3-embedding-8b | OpenRouter | Evidence retrieval (FAISS) |
| Formatter | None | — | Citation formatting |
| Humanizer | qwen3.5-plus | OpenRouter | AI pattern removal |
| Auditor | qwen3.5-plus | OpenRouter | Verification |

---

## Status

| Agent | Status | Notes |
|-------|--------|-------|
| Orchestrator | ✅ | Sisyphus |
| Downloader | ✅ | Working |
| Chunker | ✅ | Working |
| Embedder | ✅ | Working (qwen3-embedding-8b, 4096 dim) |
| Retriever | ✅ | Working (semantic search) |
| Writer | ✅ | AcademicWriterAgent (task+skill) |
| Formatter | ✅ | MLA citation formatter |
| Humanizer | ✅ | AI pattern removal (29 categories) |
| RAG Pull | ✅ | Structured evidence blocks [B_XXX] |
| Auditor | ✅ | Citation validation |

---

## Usage

### Full Pipeline
```bash
# 1. Download
python3 downloader.py --urls "url1,url2,url3"

# 2. Chunk (semantic, 150+ words)
python3 chunker.py

# 3. Embed
python3 embedder.py

# 4. Query evidence (hybrid RAG — agent calls internally)
python3 rag_retriever_skill.py "ghost train symbolism partition violence"

# 5. Write (AcademicWriterAgent calls rag-pull internally)
task(category="writing", load_skills=["academic-writing", "humanizer"], prompt="...")

# 6. Format
python3 formatter.py --input output/chapters/draft.md

# 7. Humanize
task(category="writing", load_skills=["humanizer"], prompt="...")

# 8. Audit
python3 auditor.py --input output/chapters/final_h.md
```

### Via Orchestrator
```bash
python3 orchestrator.py --urls "urls.txt" --chapter "Partition and Violence"
```
