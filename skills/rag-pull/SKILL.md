---
name: rag-pull
description: Query the FAISS RAG system for academic evidence. Returns structured evidence blocks for dissertation writing.
---

# RAG Pull Skill

Call this skill when you need evidence to support claims in your dissertation chapter.

## Purpose

This skill wraps the FAISS vector retriever and returns **structured evidence blocks** that you can use directly in academic writing. Each block contains:
- A unique `block_id` for citation (format: `[B_XXX]`)
- Source provenance (author, year, filename, page)
- Relevant text excerpt
- Relevance score
- Extracted claims the block supports

## When to Use

Invoke `rag-pull` when:
- Starting a new chapter or section
- You need evidence for specific claims
- You want to cite using `[B_XXX]` format (auditor-verifiable)
- You need structured evidence that maps claims to sources

## How It Works

1. You provide a **query** (topic or research question)
2. The skill queries the FAISS vector index
3. Returns top-5 relevant evidence blocks with provenance

## Output Format

Each block has these fields:

| Field | Description | Example |
|-------|-------------|---------|
| `block_id` | Use as `[B_XXX]` citation | `B_001` |
| `chunk_id` | Source chunk identifier | `002_P001C002` |
| `source` | Author and year | `Charyulu 2019` |
| `source_filename` | Original filename | `363508_8461703.txt` |
| `page` | Page number | `1` |
| `text` | Evidence text excerpt | "The rail route in..." |
| `score` | Relevance (0-1) | `0.71` |
| `claims` | What this block supports | `["railroad as central symbol"]` |

## Citation Format

**Use `[B_XXX]` format in your writing**, where XXX is the block_id:
- Good: `The railroad is a powerful symbol of India's misfortune [B_001].`
- Evidence pack provides: `Use block IDs like [B_001] in your citations`

## Example Workflow

```
1. User prompt: "Write about ghost train symbolism"
2. Agent calls: skill("rag-pull", query="ghost train symbolism partition violence")
3. Receives blocks:
   {
     "blocks": [
       {"block_id": "B_001", "source": "Charyulu 2019", "claims": ["railroad as central symbol"], ...},
       {"block_id": "B_002", "source": "Gupta 2014", "claims": ["train as symbol of migration"], ...}
     ]
   }
4. Agent writes: "The rail route in Train to Pakistan has especially fascinating and vile job [B_001]."
5. Agent cites using [B_XXX] format throughout
```

## Verification

The Citation Auditor (`auditor.py`) validates `[B_XXX]` citations by:
1. Extracting `[B_XXX]` pattern from text
2. Looking up block_id in the active evidence pack
3. Verifying the chunk exists in chunks.json
4. Flagging any hallucinated block citations

## CLI Test

```bash
cd /home/arshhtripathi/research-swarm
python3 rag_retriever_skill.py "ghost train symbolism"
```

Should return structured JSON with evidence blocks.

## Integration with Writer

The AcademicWriterAgent uses this skill internally:

```markdown
## RAG Integration
When given a topic:
1. Call rag-pull skill with query
2. Receive structured evidence blocks
3. Plan chapter — map each claim to a block_id
4. Write with [B_XXX] citations
5. Call rag-pull again for additional subtopics as needed
```

## Constraints

- Do NOT claim things not supported by retrieved blocks
- If no block supports a claim, say "Further research needed"
- Use `[B_XXX]` format so the auditor can verify citations
