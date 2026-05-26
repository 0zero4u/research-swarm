import json
import re

# Load chunks
with open("/home/arshhtripathi/research-swarm/chunks.json", "r") as f:
    data = json.load(f)

# Controlled vocabulary
themes = [
    "partition",
    "Gandhi",
    "communal riots",
    "violence",
    "migration",
    "gender",
    "freedom movement",
    "nationalism",
    "memory",
    "identity",
    "partition literature",
    "postcolonialism",
    "Train to Pakistan",
    "A Bend in the Ganges",
]


def word_stem_match(text_lower, term):
    words = re.findall(r"\b\w+", text_lower)
    for w in words:
        if w.startswith(term) or term.startswith(w):
            return True
    return False


def matches_theme(text_lower, theme):
    words = theme.lower().split()
    if len(words) == 1:
        return word_stem_match(text_lower, words[0])
    else:
        if theme.lower() in text_lower:
            return True
        return all(word_stem_match(text_lower, w) for w in words)


# Build theme -> chunk_ids mapping
theme_index = {}
for chunk in data["chunks"]:
    chunk_id = chunk["chunk_id"]
    text_lower = chunk["text"].lower()

    for theme in themes:
        if matches_theme(text_lower, theme):
            theme_index.setdefault(theme, []).append(chunk_id)

# Remove duplicates and sort
for theme in theme_index:
    theme_index[theme] = sorted(set(theme_index[theme]))

# Write output
output_path = "/home/arshhtripathi/research-swarm/graphs/theme_index.json"
with open(output_path, "w") as f:
    json.dump(theme_index, f, indent=2)

print("Done. theme_index.json rebuilt with chunk IDs.")
print(f"Themes found: {len(theme_index)}/{len(themes)} in controlled vocabulary")
not_found = [t for t in themes if t not in theme_index]
if not_found:
    print(f"Themes NOT found in any chunk: {not_found}")
for theme, chunks in sorted(theme_index.items()):
    print(f"  {theme}: {chunks}")
