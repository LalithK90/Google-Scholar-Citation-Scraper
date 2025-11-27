"""Validation helpers: check citation counts and produce reports.
"""
from typing import Any, Dict, List, Tuple


def validate_citation_counts(pubs: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Validate that each publication's reported citation_count equals the number of saved citations.

    Returns (valid_list, invalid_list), where invalid entries include a 'mismatch' field.
    """
    valid = []
    invalid = []
    for p in pubs:
        reported = int(p.get("citation_count") or 0)
        citations = p.get("citations") or []
        found = len(citations)
        if reported == found:
            valid.append(p)
        else:
            p2 = dict(p)
            p2["mismatch"] = {"reported": reported, "found": found}
            invalid.append(p2)
    return valid, invalid
