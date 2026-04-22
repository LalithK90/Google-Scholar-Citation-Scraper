"""Duplicate detection and canonicalization helpers.

Provides utilities for identifying duplicate publications based on title,
first author, and publication year, with fuzzy string matching to catch
similar entries that might otherwise be missed.
"""

from typing import Any, Dict, List, Tuple

# Constants
DEFAULT_SIMILARITY_THRESHOLD = 0.85
CONONICAL_KEY_SEPARATOR = "|"

try:
    from rapidfuzz import fuzz
    HAS_RAPIDFUZZ = True
except ImportError:
    import difflib
    HAS_RAPIDFUZZ = False


def canonical_key_for_pub(pub: Dict[str, Any]) -> str:
    """Produce a canonical key for a publication for duplicate detection.

    Creates a normalized key using title, first author, and year. This key
    is used to identify exact duplicates and as input for fuzzy matching.

    Args:
        pub: Dictionary containing publication metadata with optional keys:
            - 'title': Publication title (str)
            - 'authors': Author list (list or comma-separated str)
            - 'year': Publication year (str or int)

    Returns:
        A canonical key in the format: "title|first_author|year" (all lowercase).
        Empty values are included as empty strings to preserve key uniqueness.
    """
    title = (pub.get("title") or "").strip().lower()
    authors = pub.get("authors") or ""
    first_author = ""

    if isinstance(authors, (list, tuple)) and authors:
        first_author = str(authors[0]).strip().lower()
    elif isinstance(authors, str):
        first_author = authors.split(",")[0].strip().lower()

    year = str(pub.get("year") or "").strip()
    return f"{title}{CANONICAL_KEY_SEPARATOR}{first_author}{CANONICAL_KEY_SEPARATOR}{year}"


def fuzzy_similarity(a: str, b: str) -> float:
    """Calculate fuzzy string similarity between two strings.

    Uses rapidfuzz if available for better performance, falls back to
    difflib's SequenceMatcher for environments without rapidfuzz.

    Args:
        a: First string to compare.
        b: Second string to compare.

    Returns:
        Similarity score between 0.0 (completely different) and 1.0 (identical).
    """
    if HAS_RAPIDFUZZ:
        return fuzz.token_sort_ratio(a, b) / 100.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def detect_duplicates(
    pubs: List[Dict[str, Any]], threshold: float = DEFAULT_SIMILARITY_THRESHOLD
) -> Tuple[Dict[str, List[int]], List[Tuple[int, int, float]]]:
    """Detect duplicate and near-duplicate publications.

    First identifies exact duplicates using canonical keys, then performs
    fuzzy matching to find near-duplicates above the similarity threshold.

    Args:
        pubs: List of publication dictionaries to analyze.
        threshold: Similarity threshold for fuzzy matching (0..1).
            Pairs above this threshold are considered duplicates.
            Defaults to 0.85.

    Returns:
        A tuple of:
        - can_map: Dict mapping canonical_key -> list of publication indices
                  with exact duplicates.
        - pairs: List of (key_idx_i, key_idx_j, similarity) tuples for
                fuzzy-matched near-duplicates above threshold.
    """
    if not pubs:
        return {}, []

    can_map: Dict[str, List[int]] = {}
    pairs: List[Tuple[int, int, float]] = []

    # Group exact duplicates by canonical key
    for idx, pub in enumerate(pubs):
        key = canonical_key_for_pub(pub)
        if key in can_map:
            can_map[key].append(idx)
        else:
            can_map[key] = [idx]

    # Fuzzy pair detection for unique keys that are similar
    keys = list(can_map.keys())
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            sim = fuzzy_similarity(keys[i], keys[j])
            if sim >= threshold:
                pairs.append((i, j, sim))

    return can_map, pairs
