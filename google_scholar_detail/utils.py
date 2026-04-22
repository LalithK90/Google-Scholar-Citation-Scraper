"""Utility functions for filename sanitization and Excel sheet naming."""

import re
from typing import Any, Set

# Constants
INVALID_FILENAME_CHARS = r"[\\/:*?\"<>|]"
DEFAULT_AUTHOR_NAME = "author"
MAX_SHEET_NAME_LENGTH = 31
WHITESPACE_PATTERN = r"\s+"
UNDERSCORE = "_"


def sanitize_filename(name: str) -> str:
    """Sanitize string to a safe filename token.

    Removes invalid path characters and collapses whitespace to underscores.

    Args:
        name: String to sanitize for use as a filename.

    Returns:
        Sanitized filename string with invalid characters removed and spaces replaced
        with underscores. Returns 'author' if the result is empty.
    """
    sanitized = re.sub(INVALID_FILENAME_CHARS, "", str(name or "")).strip()
    sanitized = re.sub(WHITESPACE_PATTERN, UNDERSCORE, sanitized)
    return sanitized or DEFAULT_AUTHOR_NAME


def unique_sheet_name(writer: Any, base_name: str) -> str:
    """Return a unique sheet name for an Excel workbook.

    Ensures the sheet name is unique within the workbook and respects Excel's
    31-character limit for sheet names. Appends a numeric suffix if the base
    name already exists.

    Args:
        writer: openpyxl ExcelWriter instance with a 'book' attribute.
        base_name: Desired base name for the sheet.

    Returns:
        A unique sheet name (max 31 characters) not in writer.book.sheetnames.
    """
    base = str(base_name)[:MAX_SHEET_NAME_LENGTH]
    sheet_nm = base
    suffix = 1
    try:
        existing: Set[str] = set(writer.book.sheetnames)
    except (AttributeError, TypeError):
        existing = set()
    while sheet_nm in existing:
        sheet_nm = f"{base}_{suffix}"[:MAX_SHEET_NAME_LENGTH]
        suffix += 1
    return sheet_nm
