import re
from typing import Any


def sanitize_filename(name: str) -> str:
    """Sanitize string to a safe filename-ish token.
    Removes invalid path characters and collapses whitespace to underscores.
    """
    invalid = r"[\\/:*?\"<>|]"
    s = re.sub(invalid, "", str(name or "")).strip()
    s = re.sub(r"\s+", "_", s)
    return s or "author"


def unique_sheet_name(writer: Any, base_name: str) -> str:
    """Return a sheet name (<=31 chars) that's unique within writer.book.sheetnames.
    Trims and appends a numeric suffix when necessary.
    """
    base = str(base_name)[:31]
    sheet_nm = base
    suffix = 1
    try:
        existing = set(writer.book.sheetnames)
    except Exception:
        existing = set()
    while sheet_nm in existing:
        sheet_nm = f"{base}_{suffix}"[:31]
        suffix += 1
    return sheet_nm
