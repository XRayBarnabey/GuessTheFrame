"""Text normalisation shared by answer matching, search and sync."""

from __future__ import annotations

import re
import unicodedata


def normalize(value: str | None) -> str:
    if not value:
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold()
    replacements = {
        "œ": "oe",
        "æ": "ae",
        "ß": "ss",
        "ø": "o",
        "đ": "d",
        "ł": "l",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    text = text.replace("&", " et ")
    text = re.sub(r"['’‘`´]", " ", text)
    text = re.sub(r"[‐‑‒–—−]", " ", text)
    text = re.sub(r"[^\w\s]", " ", text)
    text = text.replace("_", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def build_search_text(*values: str | None) -> str:
    normalized = []
    for value in values:
        norm = normalize(value)
        if norm and norm not in normalized:
            normalized.append(norm)
    return " | ".join(normalized)
