# Research Swarm — Agent Architecture

**Last Updated:** 2026-05-26

---

## Pipeline Overview

```
URLs → Downloader → Chunker → Embedder → Retriever → Writer → Citation Auditor
         ↓            ↓          ↓           ↓          ↓
       corpus/     chunks/   vector_index  evidence   output/
        *.txt     chunks.json              packs     chapters/
```

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

---

### 5. Writer Agent (TODO)
| Property | Value |
|-----------|-------|
| **File** | `writer.py` |
| **Model** | `qwen/qwen3-72B-Instruct` (OpenRouter) |
| **Phase** | Phase 6 |
| **Input** | Topic + Evidence pack |
| **Output** | Chapter section (Markdown) |

**Responsibilities:**
- Generate academic prose
- Cite sources with MLA format
- Maintain page-level provenance

**Output Format:**
```markdown
## 1.1 Partition of India

The historiography... (Author, 4).

## 1.2 About the Author

[Next section...]
```

---

### 6. Citation Auditor Agent (TODO)
| Property | Value |
|-----------|-------|
| **File** | `auditor.py` |
| **Model** | `qwen/qwen3.5-plus` (OpenRouter) |
| **Phase** | Phase 7 |
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
6. Writer → Draft Chapter (Markdown)
         ↓
7. Citation Auditor → Validation Report
         ↓
8. Human Review → Final Output
```

---

## Directory Structure

```
research-swarm/
├── agents/                  # Agent code
│   ├── orchestrator.py    # Main coordinator
│   ├── downloader.py      # Phase 1
│   ├── chunker.py         # Phase 3
│   ├── embedder.py        # Phase 4 (TODO)
│   ├── retriever.py       # Phase 5 (TODO)
│   ├── writer.py          # Phase 6 (TODO)
│   └── auditor.py         # Phase 7 (TODO)
├── corpus/                 # Downloaded text (local only)
│   ├── *.txt
│   └── metadata.json
├── chunks/                 # Chunked data (local only)
│   └── chunks.json
├── vector_index/           # FAISS index (local only)
│   └── *.faiss
├── output/                 # Final chapters
│   └── chapter_*.md
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
| Writer | qwen3-72B-Instruct | OpenRouter | Generation |
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
| Writer | ✅ | Implemented |
| Auditor | ✅ | Implemented |

---

## Usage

### Full Pipeline
```bash
# 1. Download
python3 downloader.py --urls "url1,url2,url3"

# 2. Chunk
python3 chunker.py

# 3. Embed
python3 embedder.py

# 4. Retrieve
python3 retriever.py --query "Partition violence in Train to Pakistan"

# 5. Write
python3 writer.py --topic "Chapter 3: Partition and Violence"

# 6. Audit
python3 auditor.py --input output/draft.md
```

### Via Orchestrator
```bash
python3 orchestrator.py --urls "urls.txt" --chapter "Partition and Violence"
```
