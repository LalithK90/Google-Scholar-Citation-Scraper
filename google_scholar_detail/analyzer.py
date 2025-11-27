"""Duplicate detection and canonicalization helpers extracted from app.py.
"""
from typing import Any, Dict, List, Tuple
try:
    from rapidfuzz import fuzz
    _HAS_RAPIDFUZZ = True
except Exception:
    import difflib
    _HAS_RAPIDFUZZ = False


def canonical_key_for_pub(pub: Dict[str, Any]) -> str:
    """Produce a canonical key for a publication used by duplicate detection.

    Uses title + first author + year (when available).
    """
    title = (pub.get("title") or "").strip().lower()
    authors = pub.get("authors") or ""
    first_author = ""
    if isinstance(authors, (list, tuple)) and authors:
        first_author = str(authors[0]).strip().lower()
    elif isinstance(authors, str):
        first_author = authors.split(",")[0].strip().lower()
    year = str(pub.get("year") or "").strip()
    return f"{title}|{first_author}|{year}"


def fuzzy_similarity(a: str, b: str) -> float:
    if _HAS_RAPIDFUZZ:
        return fuzz.token_sort_ratio(a, b) / 100.0
    else:
        return difflib.SequenceMatcher(a=a, b=b).ratio()


def detect_duplicates(pubs: List[Dict[str, Any]], threshold: float = 0.85) -> Tuple[Dict[str, List[int]], List[Tuple[int, int, float]]]:
    """Return a mapping from canonical_key -> list of indices and a list of duplicate pairs.

    - pubs: list of publication dicts
    - threshold: similarity threshold (0..1)
    """
    can_map = {}
    pairs = []
    for idx, pub in enumerate(pubs):
        key = canonical_key_for_pub(pub)
        if key in can_map:
            can_map[key].append(idx)
        else:
            can_map[key] = [idx]

    # fuzzy pair detection for keys that are unique but similar
    keys = list(can_map.keys())
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            sim = fuzzy_similarity(keys[i], keys[j])
            if sim >= threshold:
                # combine indices
                pairs.append((i, j, sim))
    return can_map, pairs
