# Research Swarm Pipeline Guide

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      RESEARCH SWARM PIPELINE                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  PHASE 1: INGESTION                                               │
│  ├── PDF Sources → downloader.py → corpus/*.txt                  │
│  └── PyMuPDF extracts text with page numbers                     │
│                                                                   │
│  PHASE 2: CHUNKING                                                │
│  ├── corpus/*.txt → chunker.py → chunks/chunks.json              │
│  └── Page-level chunks with provenance (chunk_id, author, page)  │
│                                                                   │
│  PHASE 3: EMBEDDING                                               │
│  ├── chunks.json → embedder.py → vector_index/index.faiss        │
│  └── qwen3-embedding-8b (4096 dim) via OpenRouter                │
│                                                                   │
│  PHASE 4: RETRIEVAL                                               │
│  ├── Query → rag_retriever_skill.py → evidence_packs/*.json      │
│  └── FAISS semantic search + structured evidence blocks [B_XXX]  │
│                                                                   │
│  PHASE 5: WRITING                                                 │
│  ├── Evidence pack → writer.py → draft.md with [chunk_id]        │
│  └── OpenRouter (qwen3.5-plus) generates academic prose          │
│                                                                   │
│  PHASE 6: FORMATTING                                              │
│  ├── draft.md → formatter.py → formatted.md with MLA             │
│  └── Converts [chunk_id] → (filename, Author Year, p. #)         │
│                                                                   │
│  PHASE 7: HUMANIZATION                                            │
│  ├── formatted.md → HumanizerAgent → humanized.md                │
│  └── OpenCode task with humanizer skill (minimax-m2.7)           │
│                                                                   │
│  PHASE 8: AUDIT                                                   │
│  ├── humanized.md → auditor.py → audit report JSON               │
│  └── Validates all citations exist in chunks.json                │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

## Model Stack

| Component | Model | Provider | Purpose |
|-----------|-------|----------|---------|
| Orchestrator | minimax-m2.7 | Local (OpenCode) | Coordination |
| Downloader | qwen3.5-plus | OpenRouter | URL handling |
| Chunker (metadata) | deepseek-v4-flash | OpenRouter | Bibliographic extraction |
| Embedder | qwen3-embedding-8b | OpenRouter | Vectorization |
| Writer | qwen3.5-plus | OpenRouter | Generation |
| Humanizer | minimax-m2.5 | Local (OpenCode task) | AI pattern removal |
| Auditor | qwen3.5-plus | OpenRouter | Verification |

## Key Design Decisions

### Citation Format Evolution

The pipeline supports three citation formats:

1. **`[chunk_id]`** — Used by writer.py internally (e.g., `[002_P001C003]`)
2. **`[B_XXX]`** — Used by rag_retriever_skill.py evidence blocks (e.g., `[B_001]`)
3. **MLA** — Final output format (e.g., `(Charyulu 2019, p. 1)`)

The writer.py outputs `[chunk_id]` citations. The formatter.py converts these to MLA using chunks.json metadata.

### Chunk ID Format

Chunk IDs follow the pattern: `{source_id}_P{page}C{chunk_on_page}`

Examples:
- `002_P001C001` — Source 002, Page 1, Chunk 1
- `the-other-side-of-silence-voices-from-the-partition-of-india_P002C002` — Full filename prefix

#### New: Auto-Generated Works Cited

`formatter.py` now automatically appends a `## Works Cited` section at the end of the formatted chapter. It extracts bibliographic metadata from `chunks.json` (author, title, year, journal, url) and generates MLA-formatted entries for all unique sources cited in the chapter.

#### Metadata Extraction

`chunker.py` now includes `LLMMetadataExtractor` which uses `deepseek/deepseek-v4-flash` via OpenRouter to extract clean bibliographic metadata from the first page of each PDF:
- **author**: Cleaned full names (no "Dr.", "Prof.", superscripts)
- **title**: Article/paper title (not journal name)
- **year**: 4-digit year
- **journal**: Journal or publisher name
- **url**: DOI or URL if present

If LLM extraction fails, chunker falls back to regex heuristics.

```json
{
  "query": "Partition violence 1947",
  "blocks": [
    {
      "block_id": "B_001",
      "chunk_id": "002_P001C002",
      "source": "Charyulu 2019",
      "source_filename": "002_0030bc.txt",
      "page": 1,
      "text": "...",
      "score": 0.71,
      "claims": ["railroad as central symbol"]
    }
  ],
  "total_retrieved": 10
}
```

## CLI Reference

### Full Pipeline Execution

```bash
# 1. Download sources
python3 downloader.py --urls "url1,url2,url3"

# 2. Chunk
python3 chunker.py

# 3. Embed
python3 embedder.py

# 4. Query evidence
python3 rag_retriever_skill.py "ghost train symbolism" --top-k 10 --min-confidence 0.65

# 5. Write section
python3 writer.py --evidence evidence_packs/ghost_train_symbolism.json \
  --topic "Ghost Train Symbolism" --output output/chapters/section.md

# 6. Format citations
python3 formatter.py --input output/chapters/section.md \
  --output output/chapters/section_formatted.md

# 7. Humanize (via OpenCode task)
task(category="writing", load_skills=["humanizer"],
  prompt="Humanize /path/to/section_formatted.md and save to /path/to/section_h.md")

# 8. Audit
python3 auditor.py --input output/chapters/section_h.md \
  --output output/audit/section_audit.json
```

## Common Issues & Fixes

### Issue: Formatter exits early with "No citations found"

**Cause**: Input file has only `[B_XXX]` citations and no `[chunk_id]` citations.

**Fix**: Use `--pack` flag to specify the evidence pack:
```bash
python3 formatter.py --input draft.md --pack evidence_packs/query.json
```

### Issue: Formatter regex doesn't match new-style chunk IDs

**Cause**: Chunk IDs now use full filename prefixes with spaces/dots.

**Fix**: The regex in formatter.py has been updated to match:
```python
r'\[([A-Za-z0-9_ %\.\-]+_P\d+C\d+)\]'
```

### Issue: HumanizerAgent fails with model error

**Cause**: humanizer_agent.py uses hardcoded OpenRouter model.

**Fix**: Use OpenCode task invocation instead:
```bash
task(category="writing", load_skills=["humanizer"], prompt="Humanize this file...")
```

### Issue: Writer.py can't read evidence packs

**Cause**: rag_retriever_skill.py outputs `"blocks"` but writer.py expects `"results"`.

**Fix**: writer.py now supports both keys:
```python
raw_chunks = data.get("results", []) or data.get("blocks", [])
```

## Data Flow

```
PDFs → corpus/*.txt → chunks.json → index.faiss
                                      ↓
                                 Query → evidence pack
                                      ↓
                                 Writer → draft.md
                                      ↓
                                 Formatter → formatted.md
                                      ↓
                                 Humanizer → humanized.md
                                      ↓
                                 Auditor → audit.json
```

## Directory Structure

```
research-swarm/
├── *.py                    # Pipeline scripts
├── .opencode/agents/       # Agent definitions
│   ├── academic-writer-agent.md
│   ├── humanizer-agent.md
│   └── research-agent.md
├── skills/rag-pull/SKILL.md
├── corpus/                 # Extracted text files
├── chunks/                 # chunks.json (provenance store)
├── vector_index/           # FAISS index + manifest
├── evidence_packs/         # RAG query results
├── output/
│   ├── chapters/          # Generated chapters
│   └── audit/             # Audit reports
├── research_swarm_roadmap.md
├── AGENTS.md              # Agent architecture
└── PIPELINE.md            # This file
```

## Environment Setup

```bash
export OPENROUTER_API_KEY="sk-or-v1-..."
```

Required Python packages:
```
faiss-cpu
numpy
requests
PyMuPDF
```

## Quality Gates

Each chapter must pass:
1. ✅ All citations converted to MLA
2. ✅ Auditor PASS (0 hallucinated citations)
3. ✅ Word count within target (2500-3500 for intro)
4. ✅ 7 sections present for Chapter 1
5. ✅ Works Cited section auto-generated by formatter.py
