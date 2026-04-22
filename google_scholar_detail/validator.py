"""Publication validation and citation count verification.

Provides utilities to validate that reported citation counts match
actually saved citation data.
"""

from typing import Any, Dict, List, Tuple


def validate_citation_counts(
    pubs: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Validate that publication citation counts match saved citations.

    Compares each publication's reported citation_count against the number
    of citations actually saved in the data. Mismatches indicate incomplete
    data collection.

    Args:
        pubs: List of publication dictionaries to validate. Each should contain:
            - 'citation_count': Reported number of citations (int-like)
            - 'citations': List of citation objects (list)

    Returns:
        A tuple of:
        - valid_list: Publications where reported count matches saved count.
        - invalid_list: Publications with mismatches. Each invalid entry is
                       augmented with a 'mismatch' field containing:
                       - 'reported': Reported citation count
                       - 'found': Actual number of saved citations

    Example:
        >>> pubs = [
        ...     {'citation_count': 5, 'citations': [{}] * 5},  # valid
        ...     {'citation_count': 10, 'citations': [{}] * 8},  # invalid
        ... ]
        >>> valid, invalid = validate_citation_counts(pubs)
        >>> len(valid)
        1
        >>> invalid[0]['mismatch']
        {'reported': 10, 'found': 8}
    """
    valid: List[Dict[str, Any]] = []
    invalid: List[Dict[str, Any]] = []
    
    for pub in pubs:
        reported = int(pub.get("citation_count") or 0)
        citations = pub.get("citations") or []
        found = len(citations)
        
        if reported == found:
            valid.append(pub)
        else:
            # Create copy to avoid mutating original
            pub_copy = dict(pub)
            pub_copy["mismatch"] = {"reported": reported, "found": found}
            invalid.append(pub_copy)
    
    return valid, invalid
