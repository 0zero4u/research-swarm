#!/usr/bin/env python3
"""
Chunk cleaned text with full provenance tracking.
Soft target 800-1000 tokens, hard max 1500, 50 token overlap.
Token estimation: chars / 4

Strategy:
1. Parse pages via [PAGE_BREAK: N] markers
2. Strip footer lines ("Vol. 2 Issue IV ...") and blank lines
3. Unwrap hard-wrapped lines within each page (join continuation lines)
4. Split unwrapped text into sentence-groups at paragraph/sentence boundaries
5. Group sentence groups into chunks respecting token limits
6. Add 50-token overlap from previous chunk tail
"""

import json
import re
import os
import sys

# --- Configuration ---
SOURCE_ID = "PRI_001"
AUTHOR = "Priyanka Gupta"
SOFT_MIN_TOKENS = 800
SOFT_MAX_TOKENS = 1000
HARD_MAX_TOKENS = 1500
OVERLAP_TOKENS = 50
CHARS_PER_TOKEN = 4
OVERLAP_CHARS = OVERLAP_TOKENS * CHARS_PER_TOKEN

INPUT_TEXT = "/home/arshhtripathi/research-swarm/corpus/PRI_001/cleaned.txt"
INPUT_PAGE_MAP = "/home/arshhtripathi/research-swarm/corpus/PRI_001/page_mapping.json"
OUTPUT = "/home/arshhtripathi/research-swarm/chunks.json"

SECTION_BY_PAGE = {
    1: "Introduction",
    2: "Analysis of Train to Pakistan",
    3: "Analysis of Train to Pakistan",
    4: "Analysis of A Bend in the Ganges",
    5: "Analysis of A Bend in the Ganges",
    6: "Works Cited",
}

FOOTER_PATTERN = re.compile(r'Vol\.\s*\d+\s+Issue\s+IV\s+November,\s*\d{4}')

# --- Helpers ---


def estimate_tokens(text: str) -> int:
    """Chars/4 as token estimate."""
    return max(1, len(text) // CHARS_PER_TOKEN)


def parse_pages(text: str) -> list[tuple[int, str]]:
    """
    Split text on [PAGE_BREAK: N] markers.
    Returns list of (page_number, clean_page_text).
    """
    # Split preserving the markers and content between them
    pattern = re.compile(r'\[PAGE_BREAK:\s*(\d+)\]\s*\n?')
    parts = pattern.split(text)

    pages = []
    # parts[0] is anything before first marker (empty or header)
    # Then pattern repeats: page_num, content, page_num, content...
    for i in range(1, len(parts), 2):
        page_num = int(parts[i])
        page_content = parts[i + 1] if i + 1 < len(parts) else ""
        pages.append((page_num, page_content))

    return pages


def clean_page_text(page_text: str) -> str:
    """
    Clean a page's text: remove footer lines, blank lines, trim whitespace.
    """
    lines = page_text.split('\n')
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        # Remove footer line
        if FOOTER_PATTERN.match(stripped):
            continue
        # Skip blank lines
        if not stripped:
            continue
        cleaned_lines.append(stripped)

    return '\n'.join(cleaned_lines)


def unwrap_text(page_text: str) -> str:
    """
    Unwrap hard-wrapped lines: join continuation lines into flowing paragraphs.
    A line is a continuation if the next line starts with lowercase (mid-sentence wrap).
    """
    lines = page_text.split('\n')
    if not lines:
        return ''

    result_lines = []
    buffer = lines[0]

    for line in lines[1:]:
        # If this line starts with a lowercase letter (or opening paren/quote)
        # and the buffer doesn't end with a sentence-ending punctuation sequence,
        # it's a continuation (hard-wrap), not a new paragraph.
        if (line and line[0].islower()) or (line and line[0] in ',;:(' and not re.match(r'[,;:]\s', line)):
            # Continuation: join with space
            if buffer and not buffer.endswith('-'):
                buffer += ' ' + line
            else:
                buffer += line
        else:
            # This is a new paragraph/section boundary
            result_lines.append(buffer)
            buffer = line

    result_lines.append(buffer)
    return '\n\n'.join(result_lines)


def split_sentence_groups(text: str) -> list[str]:
    """
    Split unwrapped text into sentence groups (small paragraph-like units).
    Each group ends at a sentence boundary and starts a new topic/paragraph.
    For continuous prose, split at every 2-3 sentences to get small units
    that we can group into token-sized chunks.
    """
    # If text is short enough, return as-is
    if estimate_tokens(text) <= SOFT_MAX_TOKENS:
        return [text]

    # Split on paragraph boundaries first
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]

    # If we have multiple paragraphs, use them
    if len(paragraphs) > 1:
        return paragraphs

    # Single long paragraph - split at sentence boundaries
    ends = []
    for m in re.finditer(r'[.!?](?:\s|$)', text):
        ends.append(m.end())

    if len(ends) <= 1:
        return [text]

    # Group 2-3 sentences per group
    group_size = max(2, min(3, len(ends) // 3))
    for i in range(0, len(ends), group_size):
        j = min(i + group_size, len(ends))
        end_pos = ends[j - 1] if j <= len(ends) else len(text)
        segment = text[last_end:end_pos].strip()
        if segment:
            groups.append(segment)
        last_end = end_pos

    # Add any remaining text
    remaining = text[last_end:].strip()
    if remaining:
        if groups:
            groups[-1] += ' ' + remaining
        else:
            groups.append(remaining)

    return groups


def extract_citation_refs(text: str) -> list[str]:
    """Extract author names from parenthetical and narrative citations."""
    refs = set()
    # (Author, Year) or (Author et al., Year)
    for m in re.finditer(
        r'\(([A-Z][a-zA-Z]+(?:\s+(?:and|&)\s+[A-Z][a-zA-Z]+)?(?:\s+et\s+al\.?)?)\s*,?\s*\d{4}\)',
        text
    ):
        name = m.group(1).strip()
        if name and len(name) > 2:  # Skip short matches (e.g. "R.")
            refs.add(name)

    # Author (Year) - narrative citation
    for m in re.finditer(
        r'([A-Z][a-z]+(?:\s+(?:and|&)\s+[A-Z][a-z]+)?)\s*\(\d{4}\)',
        text
    ):
        name = m.group(1).strip()
        if name and len(name) > 2:
            refs.add(name)

    return sorted(refs)


def determine_section(page_set: set) -> str:
    """Determine section from the set of pages a chunk spans."""
    if not page_set:
        return "General"
    return SECTION_BY_PAGE.get(min(page_set), "General")


def build_chunks(pages: list[tuple[int, str]]) -> list[dict]:
    """
    Build chunks from cleaned and unwrapped page text.
    Chunks are built by grouping sentence-groups, respecting token limits.
    """
    # Step 1: For each page, clean, unwrap, and split into sentence groups
    all_groups = []  # (page_num, group_text)
    for page_num, page_text in pages:
        cleaned = clean_page_text(page_text)
        if not cleaned.strip():
            continue
        unwrapped = unwrap_text(cleaned)
        groups = split_sentence_groups(unwrapped)

        # Merge very small groups with the next one
        merged = []
        buffer = None
        buf_page = page_num
        for group in groups:
            if buffer is None:
                buffer = group
            else:
                # If buffer is small (< 100 tokens), merge
                if estimate_tokens(buffer) < 100:
                    buffer = buffer + ' ' + group
                else:
                    merged.append((buf_page, buffer))
                    buffer = group
        if buffer is not None:
            merged.append((buf_page, buffer))
        all_groups.extend(merged)

    print(f"Total sentence-groups across all pages: {len(all_groups)}", file=sys.stderr)
    for gi, (pn, txt) in enumerate(all_groups):
        t = estimate_tokens(txt)
        print(f"  group {gi}: page={pn}, {t} tok, {len(txt)} chars", file=sys.stderr)

    # Step 2: Group into chunks
    chunks = []
    chunk_idx = 0
    i = 0

    while i < len(all_groups):
        chunk_idx += 1
        chunk_groups = []
        chunk_pages = set()
        chunk_tokens = 0

        while i < len(all_groups):
            pn, grp_text = all_groups[i]
            grp_tokens = estimate_tokens(grp_text)

            # Would adding this group exceed hard max?
            if chunk_tokens + grp_tokens > HARD_MAX_TOKENS and chunk_tokens > 0:
                break

            chunk_groups.append(grp_text)
            chunk_pages.add(pn)
            chunk_tokens += grp_tokens
            i += 1

            # Check if we're in the sweet spot
            if SOFT_MIN_TOKENS <= chunk_tokens <= SOFT_MAX_TOKENS:
                # Try to add next group if it fits within soft max
                if i < len(all_groups):
                    next_tok = estimate_tokens(all_groups[i][1])
                    if chunk_tokens + next_tok <= SOFT_MAX_TOKENS:
                        continue
                break
            elif chunk_tokens > SOFT_MAX_TOKENS:
                # Check if adding one more would hit hard max
                if i < len(all_groups):
                    next_tok = estimate_tokens(all_groups[i][1])
                    if chunk_tokens + next_tok > HARD_MAX_TOKENS:
                        break
                else:
                    break

        # Safety: if we only got one group and it's huge, force split later
        chunk_text = '\n\n'.join(chunk_groups)
        primary_page = min(chunk_pages) if chunk_pages else 1
        section = determine_section(chunk_pages)

        chunk = {
            "chunk_id": f"{SOURCE_ID}_C{chunk_idx:03d}",
            "source_id": SOURCE_ID,
            "author": AUTHOR,
            "page": primary_page,
            "section": section,
            "themes": [],
            "citation_refs": extract_citation_refs(chunk_text),
            "text": chunk_text,
        }
        chunks.append(chunk)

        t = estimate_tokens(chunk_text)
        print(f"  {chunk['chunk_id']}: page={primary_page}, {t} tok, {len(chunk_text)} chars", file=sys.stderr)

    return chunks


def add_overlap(chunks: list[dict]) -> list[dict]:
    """
    Add 50-token overlap by prepending the tail of the previous chunk
    to the current chunk with a separator marker.
    """
    if len(chunks) <= 1:
        return chunks

    for idx in range(1, len(chunks)):
        prev_chunk = chunks[idx - 1]
        curr_chunk = chunks[idx]

        # Extract tail from previous chunk (~50 tokens worth)
        prev_text = prev_chunk["text"]
        # Find a sentence boundary near OVERLAP_CHARS from the end
        tail_start = max(0, len(prev_text) - OVERLAP_CHARS * 2)
        tail_candidate = prev_text[tail_start:]

        # Find a clean sentence boundary to start from
        # Look for a sentence-ending period followed by space
        sentence_starts = list(re.finditer(r'(?<=[.!?])\s+(?=[A-Z"\u201c])', tail_candidate))
        if sentence_starts:
            # Start from the last good sentence boundary, or use the first one
            # We want the overlap to be the LAST ~50 tokens worth
            overlap_text = tail_candidate
            for m in sentence_starts:
                if len(tail_candidate) - m.start() <= OVERLAP_CHARS * 2:
                    overlap_text = tail_candidate[m.start() + 1:]
                    break
                overlap_text = tail_candidate[m.start() + 1:]
        else:
            # Fallback: last N chars
            overlap_text = prev_text[-OVERLAP_CHARS:] if len(prev_text) > OVERLAP_CHARS else prev_text

        overlap_text = overlap_text.strip()
        if not overlap_text:
            continue

        overlap_tokens = estimate_tokens(overlap_text)

        # Prepend overlap to current chunk text with marker
        curr_chunk["text"] = overlap_text + "\n\n[OVERLAPPING: from previous chunk]\n\n" + curr_chunk["text"]

        # Update page for current chunk (keep original page as primary)
        # No change needed - primary page stays the same

        print(f"  OVERLAP: {chunks[idx]['chunk_id']} <- ~{overlap_tokens} tok from {chunks[idx-1]['chunk_id']}", file=sys.stderr)

    return chunks


def main():
    with open(INPUT_TEXT, 'r', encoding='utf-8') as f:
        raw_text = f.read()

    print(f"Input: {len(raw_text)} chars", file=sys.stderr)

    pages = parse_pages(raw_text)
    print(f"Pages: {len(pages)}", file=sys.stderr)
    for pn, pt in pages:
        print(f"  Page {pn}: {len(pt)} chars", file=sys.stderr)

    print("\nBuilding chunks...", file=sys.stderr)
    chunks = build_chunks(pages)

    print("\nAdding overlap...", file=sys.stderr)
    chunks = add_overlap(chunks)

    output = {"chunks": chunks}
    os.makedirs(os.path.dirname(OUTPUT) or '.', exist_ok=True)
    with open(OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nDone. {len(chunks)} chunks -> {OUTPUT}", file=sys.stderr)

    warnings = 0
    for c in chunks:
        t = estimate_tokens(c["text"])
        if t > HARD_MAX_TOKENS:
            print(f"  WARN: {c['chunk_id']} exceeds hard max ({t} tok)", file=sys.stderr)
            warnings += 1
        elif t < SOFT_MIN_TOKENS:
            print(f"  INFO: {c['chunk_id']} below soft min ({t} tok)", file=sys.stderr)

    if warnings == 0:
        print("  All chunks within limits ✓", file=sys.stderr)
    else:
        print(f"  {warnings} chunk(s) exceed hard max ✗", file=sys.stderr)


if __name__ == "__main__":
    main()
