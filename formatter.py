#!/usr/bin/env python3
"""
Citation Formatter

Converts structured citations [[chunk_id:page]] in Markdown files
to proper MLA format (Author Year, p. #).

Usage:
    python3 formatter.py --input output/chapters/draft.md
    python3 formatter.py --input output/chapters/draft.md --output output/chapters/final.md
"""

import argparse
import json
import re
import sys


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

    # Check for "et al." — treat as single first author
    if re.search(r'\bet\s+al\.?', author_str, re.IGNORECASE):
        first = author_str.split(",")[0].strip() if "," in author_str else author_str.split()[0]
        return [first]

    # Split on " and " first
    if " and " in author_str:
        parts = [p.strip() for p in author_str.split(" and ")]
        # If first part contains commas, it's a list with "and" at end
        authors = []
        for part in parts:
            if "," in part:
                authors.extend(p.strip() for p in part.split(",") if p.strip())
            else:
                authors.append(part)
        return authors

    # Check for comma-separated list with trailing "and"
    if "," in author_str:
        parts = [p.strip() for p in author_str.split(",")]
        # Filter empty strings
        parts = [p for p in parts if p]
        # If last part starts with "and ", remove the "and"
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
    # Extract and strip extension from source_filename
    source_filename = chunk.get("source_filename", "unknown")
    base_name = source_filename.rsplit(".", 1)[0]

    author_str = chunk.get("author", "")
    year = chunk.get("year", "").strip() if chunk.get("year") else ""

    author_formatted = format_author(author_str)

    # Build citation body
    if year:
        citation = f"{base_name}, {author_formatted} {year}"
    else:
        citation = f"{base_name}, {author_formatted}"

    # Add page number if specified
    if page is not None:
        citation = f"{citation}, p. {page}"

    return f"({citation})"


def convert_citations(text, chunks_map):
    """Replace all [[chunk_id:page]] citations with MLA format.

    The pattern matches [[CHUNK_ID:PAGE_NUM]] where chunk_id can contain
    alphanumeric characters and underscores, and page is a digit string.
    """
    # Pattern: [[chunk_id:page]]
    citation_pattern = re.compile(r'\[\[([A-Za-z0-9_]+):(\d+)\]\]')

    def replace_match(match):
        chunk_id = match.group(1)
        page = match.group(2)

        chunk = chunks_map.get(chunk_id)
        if chunk is None:
            # Chunk not found — preserve original citation for review
            print(
                f"Warning: chunk '{chunk_id}' not found in chunks metadata, "
                f"preserving original citation",
                file=sys.stderr,
            )
            return match.group(0)

        return format_mla_citation(chunk, page=page)

    return citation_pattern.sub(replace_match, text)


def main():
    parser = argparse.ArgumentParser(
        description="Convert [[chunk_id:page]] citations to MLA format in Markdown files"
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="Input markdown file with [[chunk_id:page]] citations",
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

    args = parser.parse_args()

    # Validate input file
    if not os.path.isfile(args.input):
        print(f"Error: input file '{args.input}' not found", file=sys.stderr)
        sys.exit(1)

    # Load chunks metadata
    chunks_map = load_chunks(args.chunks)
    print(f"Loaded {len(chunks_map)} chunks from '{args.chunks}'")

    # Read input markdown
    with open(args.input, "r", encoding="utf-8") as f:
        text = f.read()

    # Count citations before conversion
    raw_count = len(re.findall(r'\[\[([A-Za-z0-9_]+):(\d+)\]\]', text))
    if raw_count == 0:
        print("No citations found in input file.")
        sys.exit(0)

    # Convert citations
    converted = convert_citations(text, chunks_map)

    # Count MLA citations after conversion
    mla_count = len(re.findall(r'\([^()]+,\s*p\.\s*\d+\)', converted))

    # Write output
    output_path = args.output if args.output else args.input
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(converted)

    print(f"Processed {args.input}")
    print(f"  Citations found:     {raw_count}")
    print(f"  MLA citations written: {mla_count}")
    if args.output:
        print(f"  Output:              {args.output}")
    else:
        print(f"  Updated:             {args.input}")


if __name__ == "__main__":
    import os
    main()
