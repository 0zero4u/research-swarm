#!/usr/bin/env python3
"""Build citation graph and theme graph for PRI_001 corpus."""

import json
import re
from pathlib import Path

# ============ PHASE 3A: CITATION GRAPH ============

# Based on bibliography parsing from cleaned.txt:
# Primary sources (lines 249-251):
#   Malgonkar, Manohar. A Bend in the Ganges → REF_001
#   Singh, Khushwant. Train to Pakistan → REF_002
# Secondary sources (lines 253-272):
#   Bruschi, Isabella → REF_003
#   Butalia, Urvashi → REF_004
#   Daiya, Kavita → REF_005
#   Fazilla-Yacoobali Zamindar, Vazira → REF_006
#   Lapierre, Dominique and Larry Collins → REF_007
#   Lerner, Gerda → REF_008
#   Menon, Ritu and Kamla Bhasin → REF_009
#   Scott, Joan Wallach → REF_010
#   Sharma, K. K. and B. K. Johri → REF_011
#   Shaikh, Firoz A. → REF_012
# Web sources (lines 274-280):
#   URL 1 → REF_013
#   URL 2 → REF_014
#   URL 3 → REF_015
#   URL 4 → REF_016

citation_graph = {
    "PRI_001": [
        "REF_001",  # Malgonkar - A Bend in the Ganges
        "REF_002",  # Singh - Train to Pakistan
        "REF_003",  # Bruschi - Partition in Fiction Gendered Perspectives
        "REF_004",  # Butalia - The Other Side of Silence
        "REF_005",  # Daiya - Violent Belongings
        "REF_006",  # Fazilla-Yacoobali Zamindar - The Long Partition
        "REF_007",  # Lapierre & Collins - Freedom at Midnight
        "REF_008",  # Lerner - The Majority Finds Its Past
        "REF_009",  # Menon & Bhasin - Borders and Boundaries
        "REF_010",  # Scott - Women's History and the Rewriting of History
        "REF_011",  # Sharma & Johri - The Partition in Indian English Novels
        "REF_012",  # Shaikh - Partition a Human Tragedy
        "REF_013",  # Web source 1
        "REF_014",  # Web source 2
        "REF_015",  # Web source 3
        "REF_016",  # Web source 4
    ]
}

# Write citation_graph.json
with open('/home/arshhtripathi/research-swarm/graphs/citation_graph.json', 'w') as f:
    json.dump(citation_graph, f, indent=2)

print("Created citation_graph.json")

# ============ REFERENCES.JSON ============

# Existing references from metadata.json with lineage_depth
# Since PRI_001 doesn't cite any other corpus papers (all refs are external),
# lineage_depth = 1 for all (direct citations from PRI_001)

references = {
    "REF_001": {
        "author": "Manohar Malgonkar",
        "title": "A Bend in the Ganges",
        "year": 2009,
        "publisher": "Roli books",
        "resolved": False,
        "lineage_depth": 1
    },
    "REF_002": {
        "author": "Khushwant Singh",
        "title": "Train to Pakistan",
        "year": 2007,
        "publisher": "Ravi Dayal Publisher: Akash Press",
        "resolved": False,
        "lineage_depth": 1
    },
    "REF_003": {
        "author": "Isabella Bruschi",
        "title": "Partition in Fiction Gendered Perspectives",
        "year": 2010,
        "publisher": "Atlantic Publishers",
        "resolved": False,
        "lineage_depth": 1
    },
    "REF_004": {
        "author": "Urvashi Butalia",
        "title": "The Other Side of Silence Voices from the Partition of India",
        "year": 1998,
        "publisher": "Repro India Ltd",
        "resolved": False,
        "lineage_depth": 1
    },
    "REF_005": {
        "author": "Kavita Daiya",
        "title": "Violent Belongings Partition, Gender, and National Culture in Postcolonial India",
        "year": 2008,
        "publisher": "Yoda Press",
        "resolved": False,
        "lineage_depth": 1
    },
    "REF_006": {
        "author": "Vazira Fazilla-Yacoobali Zamindar",
        "title": "The Long Partition and the Making of Modern South Asia. Refugees, Boundaries, Histories",
        "year": 2008,
        "publisher": "Penguin Books",
        "resolved": False,
        "lineage_depth": 1
    },
    "REF_007": {
        "author": "Dominique Lapierre and Larry Collins",
        "title": "Freedom at Midnight",
        "year": 2007,
        "publisher": "Vikas Publishing House",
        "resolved": False,
        "lineage_depth": 1
    },
    "REF_008": {
        "author": "Gerda Lerner",
        "title": "The Majority Finds Its Past",
        "year": None,
        "publisher": None,
        "resolved": False,
        "lineage_depth": 1
    },
    "REF_009": {
        "author": "Ritu Menon and Kamla Bhasin",
        "title": "Borders and Boundaries Women in India's Partition",
        "year": 2011,
        "publisher": "De Unique",
        "resolved": False,
        "lineage_depth": 1
    },
    "REF_010": {
        "author": "Joan Wallach Scott",
        "title": "Women's History and the Rewriting of History",
        "year": 1987,
        "publisher": "Indiana University Press",
        "resolved": False,
        "lineage_depth": 1
    },
    "REF_011": {
        "author": "K. K. Sharma and B. K. Johri",
        "title": "The Partition in Indian English Novels",
        "year": 1984,
        "publisher": "Vimal Prakashan",
        "resolved": False,
        "lineage_depth": 1
    },
    "REF_012": {
        "author": "Firoz A. Shaikh",
        "title": "Partition a Human Tragedy",
        "year": 2009,
        "publisher": "Sarup Book Publishers",
        "resolved": False,
        "lineage_depth": 1
    },
    "REF_013": {
        "author": None,
        "title": None,
        "year": None,
        "publisher": None,
        "resolved": False,
        "lineage_depth": 1
    },
    "REF_014": {
        "author": None,
        "title": None,
        "year": None,
        "publisher": None,
        "resolved": False,
        "lineage_depth": 1
    },
    "REF_015": {
        "author": None,
        "title": None,
        "year": None,
        "publisher": None,
        "resolved": False,
        "lineage_depth": 1
    },
    "REF_016": {
        "author": None,
        "title": None,
        "year": None,
        "publisher": None,
        "resolved": False,
        "lineage_depth": 1
    }
}

with open('/home/arshhtripathi/research-swarm/graphs/references.json', 'w') as f:
    json.dump(references, f, indent=2)

print("Created references.json")

# ============ PHASE 3B: THEME EXTRACTION ============

# Controlled vocabulary
VOCABULARY = [
    "partition", "Gandhi", "communal riots", "violence", "migration", "gender",
    "freedom movement", "nationalism", "memory", "identity", "literature",
    "postcolonialism", "Train to Pakistan", "A Bend in the Ganges"
]

# Read cleaned.txt
with open('/home/arshhtripathi/research-swarm/corpus/PRI_001/cleaned.txt', 'r') as f:
    content = f.read()

# Parse into paragraphs, tracking page numbers
# Page breaks are marked as [PAGE_BREAK: N]
lines = content.split('\n')

paragraphs = []  # List of (page_num, text)
current_page = 1
current_para = []
in_bibliography = False

for line in lines:
    stripped = line.strip()
    
    # Check for page break
    page_match = re.match(r'\[PAGE_BREAK:\s*(\d+)\]', stripped)
    if page_match:
        current_page = int(page_match.group(1))
        continue
    
    # Start of bibliography section
    if stripped.startswith('Working bibliography:') or stripped.startswith('Primary sources:') or stripped.startswith('Secondary sources:') or stripped.startswith('Web Sources:'):
        in_bibliography = True
        if current_para:
            text = ' '.join(current_para).strip()
            if text:
                paragraphs.append((current_page, text))
            current_para = []
        continue
    
    # Skip bibliography content
    if in_bibliography:
        continue
    
    if not stripped:
        if current_para:
            text = ' '.join(current_para).strip()
            if text and len(text) > 50:
                paragraphs.append((current_page, text))
            current_para = []
        continue
    
    current_para.append(stripped)

# Close last paragraph
if current_para:
    text = ' '.join(current_para).strip()
    if text and len(text) > 50:
        paragraphs.append((current_page, text))

# Extract themes for each paragraph
def extract_themes(text):
    """Extract themes from paragraph text using vocabulary matching."""
    text_lower = text.lower()
    found = []
    
    for vocab in VOCABULARY:
        # Use word boundary matching for better accuracy
        # Create pattern that matches the vocab as a whole word/phrase
        pattern = re.escape(vocab.lower())
        if re.search(r'\b' + pattern + r'\b', text_lower):
            found.append(vocab)
    
    return found[:5]  # Max 5 themes

# Build theme_graph and theme_index
theme_graph = []
theme_index = {}  # inverted index: theme -> [chunk_ids]

for idx, (page, text) in enumerate(paragraphs, start=1):
    chunk_id = f"PRI_001_P{idx:03d}"
    paragraph_num = idx
    themes = extract_themes(text)
    
    entry = {
        "chunk_id": chunk_id,
        "paragraph_num": paragraph_num,
        "page": page,
        "themes": themes
    }
    theme_graph.append(entry)
    
    # Update inverted index
    for theme in themes:
        if theme not in theme_index:
            theme_index[theme] = []
        theme_index[theme].append(chunk_id)

# Write theme_graph.json
with open('/home/arshhtripathi/research-swarm/graphs/theme_graph.json', 'w') as f:
    json.dump(theme_graph, f, indent=2)

print(f"Created theme_graph.json with {len(theme_graph)} paragraphs")

# Write theme_index.json
with open('/home/arshhtripathi/research-swarm/graphs/theme_index.json', 'w') as f:
    json.dump(theme_index, f, indent=2)

print(f"Created theme_index.json with {len(theme_index)} themes")
print(f"Themes found: {list(theme_index.keys())}")