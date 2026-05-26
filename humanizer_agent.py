#!/usr/bin/env python3
"""
Humanizer Agent
===============
Removes AI writing patterns from formatted dissertation chapters.
Applies the humanizer skill's 29 pattern categories to produce natural prose.
"""

import argparse
import os
import sys
from pathlib import Path

import requests


# ============================================================================
# CONFIGURATION
# ============================================================================

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_MODEL = "qwen/qwen3.5-plus-20260420"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

SYSTEM_PROMPT = """You are an academic writing editor specializing in removing AI-generated text patterns.
Your task: make text sound like a human wrote it — natural, varied, with personality.

RULES (apply ALL of these):
1. PRESERVE all MLA citations exactly as-is — do not modify any (Author Year, p. #) patterns
2. PRESERVE all headings, section structure, and paragraph breaks
3. REMOVE significance inflation: avoid "pivotal", "landmark", "monumental", "cataclysmic", "unprecedented"
4. REMOVE -ing filler phrases: "highlighting", "underscoring", "showcasing", "reflecting", "symbolizing"
5. REMOVE copula avoidance: replace "serves as", "stands as", "represents", "underscores" with "is", "shows", "proves"
6. REMOVE promotional language: "groundbreaking", "breathtaking", "nestled", "vibrant", "renowned"
7. REMOVE vague attributions: "experts believe", "researchers argue" — use specific citations instead
8. REMOVE rule of three overuse
9. REMOVE negative parallelisms: "Not only X, but Y", "It's not just about"
10. REMOVE excessive em dashes — rewrite with commas or periods
11. REMOVE passive voice where active is clearer
12. REMOVE excessive hedging: "could potentially", "it may be that", "some suggest"
13. REMOVE filler phrases: "In order to" → "To", "Due to the fact that" → "Because"
14. REMOVE AI vocabulary: "additionally", "crucial", "intricate", "pivotal", "tapestry", "testament"
15. REMOVE curly quotes ("...") — use straight quotes
16. REMOVE emojis from text
17. FIX title case headings — use sentence case
18. REMOVE generic upbeat conclusions
19. REMOVE signposting: "Let's explore", "Diving into", "Here's what"
20. REMOVE collaborative artifacts: "I hope this helps", "Let me know if..."
21. REMOVE knowledge-cutoff disclaimers: "as of my knowledge cutoff"
22. REMOVE sycophantic tone

ADD SOUL:
- Vary sentence length: mix short punchy sentences with longer flowing ones
- Have opinions where appropriate
- Be specific — avoid vague claims
- Let some personality through

WORKFLOW (4 passes):
Pass 1: Draft rewrite applying all rules above
Pass 2: Self-audit — ask "What makes this obviously AI generated?"
Pass 3: Revise based on audit
Pass 4: Final review for naturalness

OUTPUT FORMAT:
Return ONLY the humanized chapter text. No explanations of changes made.
Start directly with the content (no preamble like "Here is the humanized version").
"""


# ============================================================================
# HUMANIZER
# ============================================================================

class HumanizerAgent:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or OPENROUTER_API_KEY
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY environment variable not set")

    def humanize(self, input_text: str) -> str:
        """Apply humanizer skill to input text."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": OPENROUTER_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Humanize this dissertation chapter. Preserve all MLA citations and headings exactly as-is:\n\n{input_text}"}
            ],
            "temperature": 0.7,
        }

        response = requests.post(
            f"{OPENROUTER_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
            timeout=180,
        )

        if response.status_code != 200:
            raise Exception(f"OpenRouter API error: {response.status_code} — {response.text}")

        data = response.json()
        return data["choices"][0]["message"]["content"]


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Humanize AI-generated academic prose")
    parser.add_argument("--input", "-i", required=True, help="Input chapter file (formatted)")
    parser.add_argument("--output", "-o", default=None, help="Output file (default: input path with _h suffix)")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    if args.output:
        output_path = Path(args.output)
    else:
        output_path = input_path.parent / f"{input_path.stem}_h{input_path.suffix}"

    print(f"Reading: {input_path}")
    input_text = input_path.read_text(encoding="utf-8")

    print(f"Humanizing with {OPENROUTER_MODEL}...")
    agent = HumanizerAgent()
    humanized = agent.humanize(input_text)

    output_path.write_text(humanized, encoding="utf-8")
    print(f"Written: {output_path}")


if __name__ == "__main__":
    main()
