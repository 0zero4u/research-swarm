#!/usr/bin/env python3
"""
Citation Formatter

Converts structured citations in Markdown files to proper MLA format.

Supported formats:
  [chunk_id:(author year, p. #)]  — hybrid: validates chunk, keeps MLA intact
  [chunk_id]                       — simple: looks up metadata, generates MLA
  [B_XXX]                          — block: looks up block in evidence packs, generates MLA

Usage:
    python3 formatter.py --input output/chapters/draft.md
    python3 formatter.py --input output/chapters/draft.md --output output/chapters/final.md
"""

import argparse
import json
import re
import sys
from pathlib import Path


def load_chunks(chunks_path="chunks/chunks.json"):
    """Load chunks.json and build chunk_id -> metadata mapping."""
    try:
        with open(chunks_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: chunks file not found at '{chunks_path}'", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: invalid JSON in '{chunks_path}': {e}", file=sys.stderr)
        sys.exit(1)

    chunks_map = {}
    for chunk in data.get("chunks", []):
        chunk_id = chunk.get("chunk_id")
        if chunk_id:
            chunks_map[chunk_id] = chunk
    return chunks_map


def load_evidence_pack(pack_path: str) -> dict:
    """Load a single evidence pack JSON file.

    Returns dict with blocks, or empty dict if not found/error.
    """
    try:
        with open(pack_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, IOError):
        return {}


def load_all_evidence_packs(evidence_dir="evidence_packs"):
    """Load all evidence packs and build block_id -> chunk_metadata mapping.
    
    Returns dict mapping "B_XXX" -> chunk_metadata dict.
    """
    evidence_path = Path(evidence_dir)
    if not evidence_path.exists():
        return {}
    
    block_map = {}
    
    for pack_file in evidence_path.glob("*.json"):
        try:
            with open(pack_file, "r", encoding="utf-8") as f:
                pack = json.load(f)

            blocks = pack.get("blocks", [])
            for idx, block in enumerate(blocks, start=1):
                block_id = block.get("block_id", f"B_{idx:03d}")
                if block_id not in block_map:
                    block_map[block_id] = {
                        "chunk_id": block.get("chunk_id", ""),
                        "source_filename": block.get("source_filename", ""),
                        "page": block.get("page", 1),
                    }

            if not blocks:
                results = pack.get("results", [])
                for idx, result in enumerate(results, start=1):
                    block_id = f"B_{idx:03d}"
                    if block_id not in block_map:
                        block_map[block_id] = {
                            "chunk_id": result.get("chunk_id", ""),
                            "source_filename": result.get("source_filename", ""),
                            "page": result.get("page", 1),
                        }
        except (json.JSONDecodeError, IOError):
            continue
    
    return block_map


def extract_last_name(name):
    """Extract the last name (surname) from a full name."""
    parts = name.strip().split()
    return parts[-1] if parts else name


def parse_authors(author_str):
    """Parse author string into a list of individual author names.

    Handles formats:
      - "Shikha G. Mohana Charyulu"          -> ["Shikha G. Mohana Charyulu"]
      - "Shikha and Charyulu"                -> ["Shikha", "Charyulu"]
      - "Smith, Jones, and Brown"            -> ["Smith", "Jones", "Brown"]
      - "Smith, Jones and Brown"             -> ["Smith", "Jones", "Brown"]
      - "Smith et al."                      -> ["Smith"]
    """
    if not author_str:
        return []

    author_str = author_str.strip()

    if re.search(r'\bet\s+al\.?', author_str, re.IGNORECASE):
        first = author_str.split(",")[0].strip() if "," in author_str else author_str.split()[0]
        return [first]

    if " and " in author_str:
        parts = [p.strip() for p in author_str.split(" and ")]
        authors = []
        for part in parts:
            if "," in part:
                authors.extend(p.strip() for p in part.split(",") if p.strip())
            else:
                authors.append(part)
        return authors

    if "," in author_str:
        parts = [p.strip() for p in author_str.split(",")]
        parts = [p for p in parts if p]
        if parts and parts[-1].lower().startswith("and "):
            parts[-1] = parts[-1][4:].strip()
        elif parts and parts[-1].lower() == "and":
            parts.pop()
        return parts if len(parts) > 1 else parts

    return [author_str]


def format_author(author_str):
    """Format author name(s) in MLA style.

    Rules:
      - Single author: LastName
      - Two authors:   LastName1 and LastName2
      - Three+:        LastName1 et al.
    """
    if not author_str:
        return "Unknown"

    authors = parse_authors(author_str)

    if len(authors) == 0:
        return "Unknown"
    elif len(authors) == 1:
        return extract_last_name(authors[0])
    elif len(authors) == 2:
        return f"{extract_last_name(authors[0])} and {extract_last_name(authors[1])}"
    else:
        return f"{extract_last_name(authors[0])} et al."


def format_mla_citation(chunk, page=None):
    """Format a citation in MLA style.

    Returns:
      (filename, Author Year, p. #) — when year and page are available
      (filename, Author, p. #)      — when page available but no year
      (filename, Author Year)       — when year available but no page
      (filename, Author)            — when neither is available
    """
    source_filename = chunk.get("source_filename", "unknown")
    base_name = source_filename.rsplit(".", 1)[0]

    author_str = chunk.get("author", "")
    year = chunk.get("year", "").strip() if chunk.get("year") else ""

    author_formatted = format_author(author_str)

    if year:
        citation = f"{base_name}, {author_formatted} {year}"
    else:
        citation = f"{base_name}, {author_formatted}"

    if page is not None:
        citation = f"{citation}, p. {page}"

    return f"({citation})"


def convert_block_citations(text, evidence_pack_path):
    """
    Load evidence pack from JSON and convert [B_XXX] to MLA.

    For each [B_XXX] found, look up the block in the pack
    and replace with format: (Author Year, p. #)

    Args:
        text: Input text with [B_XXX] citations
        evidence_pack_path: Path to evidence pack JSON from rag_retriever_skill

    Returns:
        Text with [B_XXX] replaced by MLA citations
    """
    pack = load_evidence_pack(evidence_pack_path)
    blocks = pack.get("blocks", [])

    # Build block_id -> block lookup
    block_map = {block["block_id"]: block for block in blocks}

    def replace_block(match):
        block_id = match.group(0)  # e.g. "[B_001]"
        block_num = match.group(1)
        key = f"B_{int(block_num):03d}"

        block = block_map.get(key)
        if not block:
            return block_id  # preserve if not found

        source = block.get("source", "Unknown")
        # Parse "Author Year" from source field
        # e.g. "Butalia 1998" -> author="Butalia", year="1998"
        parts = source.rsplit(" ", 1)
        author = parts[0] if parts else "Unknown"
        year = parts[1] if len(parts) > 1 else ""
        page = block.get("page", "")

        if year:
            return f"({author} {year}, p. {page})"
        else:
            return f"({author}, p. {page})"

    # Pattern: [B_XXX] where XXX is 1-3 digits
    return re.sub(r'\[B_(\d+)\]', replace_block, text)


def generate_works_cited(used_chunks):
    """Generate MLA Works Cited section from cited chunks.

    Groups by source_filename to avoid duplicate entries.
    Returns markdown-formatted Works Cited section.
    """
    if not used_chunks:
        return ""

    # Deduplicate by source_filename, keep first occurrence
    seen = {}
    for chunk in used_chunks:
        src = chunk.get("source_filename", "unknown")
        if src not in seen:
            seen[src] = chunk

    entries = []
    for chunk in seen.values():
        author = chunk.get("author", "").strip()
        title = chunk.get("title", "").strip()
        year = chunk.get("year", "").strip()
        journal = chunk.get("journal", "").strip()
        volume = chunk.get("volume", "").strip()
        issue = chunk.get("issue", "").strip()
        url = chunk.get("url", "").strip()

        # Build MLA entry
        parts = []
        if author:
            parts.append(author + ".")
        if title:
            parts.append(f'"{title}."')
        if journal:
            if volume and issue:
                parts.append(f"*{journal}*, vol. {volume}, no. {issue}")
            elif volume:
                parts.append(f"*{journal}*, vol. {volume}")
            else:
                parts.append(f"*{journal}*")
        if year:
            parts.append(year + ".")
        if url:
            parts.append(url + ".")

        entry = " ".join(parts) if parts else chunk.get("source_filename", "unknown")
        entries.append(entry)

    if not entries:
        return ""

    lines = ["## Works Cited", ""]
    for entry in entries:
        lines.append(entry)
        lines.append("")
    return "\n".join(lines)


def convert_citations(text, chunks_map, block_map):
    """Replace all [chunk_id] and [chunk_id:(mla citation)] citations with MLA format.

    Also handles [B_XXX] block citations by looking up block metadata and converting to MLA.
    Tracks all cited chunks for Works Cited generation.
    """
    used_chunks = []

    def replace_hybrid(match):
        chunk_id = match.group(1)
        mla_cite = match.group(2)

        if chunk_id not in chunks_map:
            print(
                f"Warning: chunk '{chunk_id}' not found in chunks metadata, "
                f"preserving original citation",
                file=sys.stderr,
            )
            return match.group(0)

        return mla_cite

    def replace_simple(match):
        chunk_id = match.group(1)

        chunk = chunks_map.get(chunk_id)
        if chunk is None:
            print(
                f"Warning: chunk '{chunk_id}' not found in chunks metadata, "
                f"preserving original citation",
                file=sys.stderr,
            )
            return match.group(0)

        used_chunks.append(chunk)
        page = chunk.get("page", 1)
        return format_mla_citation(chunk, page=page)

    def replace_block(match):
        block_id = f"B_{int(match.group(1)):03d}"

        block_info = block_map.get(block_id)
        if block_info is None:
            print(
                f"Warning: block '{block_id}' not found in evidence packs, "
                f"preserving original citation",
                file=sys.stderr,
            )
            return block_id

        chunk_id = block_info.get("chunk_id", "")
        chunk = chunks_map.get(chunk_id)
        if chunk is None:
            print(
                f"Warning: chunk '{chunk_id}' for block '{block_id}' not found, "
                f"preserving original citation",
                file=sys.stderr,
            )
            return block_id

        used_chunks.append(chunk)
        page = block_info.get("page", chunk.get("page", 1))
        return format_mla_citation(chunk, page=page)

    text = re.sub(
        r'\[B_(\d+)\]',
        replace_block,
        text
    )

    text = re.sub(
        r'\[([A-Za-z0-9_ %\.\-]+_P\d+C\d+):(\([^)]+\))\]',
        replace_hybrid,
        text
    )
    text = re.sub(
        r'\[([A-Za-z0-9_ %\.\-]+_P\d+C\d+)\]',
        replace_simple,
        text
    )

    # Append Works Cited if any chunks were cited
    if used_chunks:
        works_cited = generate_works_cited(used_chunks)
        if works_cited:
            text = text.rstrip() + "\n\n---\n\n" + works_cited

    return text


def main():
    parser = argparse.ArgumentParser(
        description="Convert [chunk_id] and [chunk_id:(mla citation)] citations to MLA format"
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="Input markdown file with [chunk_id] or [chunk_id:(mla citation)] citations",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Output markdown file (default: overwrite input)",
    )
    parser.add_argument(
        "--chunks", "-c",
        default="chunks/chunks.json",
        help="Path to chunks.json metadata (default: chunks/chunks.json)",
    )
    parser.add_argument(
        "--evidence-dir", "-e",
        default="evidence_packs",
        help="Path to evidence_packs directory (default: evidence_packs)",
    )
    parser.add_argument(
        "--pack", "--evidence-pack", "-p",
        default=None,
        help="Path to specific evidence pack JSON from rag_retriever_skill",
    )

    args = parser.parse_args()

    if not os.path.isfile(args.input):
        print(f"Error: input file '{args.input}' not found", file=sys.stderr)
        sys.exit(1)

    chunks_map = load_chunks(args.chunks)
    print(f"Loaded {len(chunks_map)} chunks from '{args.chunks}'")

    block_map = load_all_evidence_packs(args.evidence_dir)
    print(f"Loaded {len(block_map)} block citations from '{args.evidence_dir}'")

    with open(args.input, "r", encoding="utf-8") as f:
        text = f.read()

    raw_count = len(re.findall(r'\[([A-Za-z0-9_ %\.\-]+_P\d+C\d+)(?::\([^)]+\))?\]', text))
    block_count = len(re.findall(r'\[B_\d+\]', text))
    if raw_count == 0 and block_count == 0:
        print("No citations found in input file.")
        sys.exit(0)

    if args.pack:
        pack_path = Path(args.pack)
        if pack_path.exists():
            text = convert_block_citations(text, str(pack_path))
            print(f"Converted block citations using: {args.pack}")
        else:
            print(f"Warning: evidence pack not found at '{args.pack}'", file=sys.stderr)

    converted = convert_citations(text, chunks_map, block_map)

    mla_count = len(re.findall(r'\([^()]+,\s*p\.\s*\d+\)', converted))

    output_path = args.output if args.output else args.input
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(converted)

    print(f"Processed {args.input}")
    print(f"  Citations found:     {raw_count}")
    print(f"  Block citations:     {block_count}")
    print(f"  MLA citations written: {mla_count}")
    if args.output:
        print(f"  Output:              {args.output}")
    else:
        print(f"  Updated:             {args.input}")


if __name__ == "__main__":
    import os
    main()
