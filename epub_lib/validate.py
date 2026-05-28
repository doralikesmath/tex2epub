"""epub_lib.validate -- optional epubcheck pass."""
from __future__ import annotations

from pathlib import Path


def run(epub: Path) -> tuple[bool, int, int]:
    """Validate `epub` with epubcheck.

    Returns (valid, n_errors, n_warnings). Prints up to 15 messages.
    Requires the `epubcheck` python package (pip install epubcheck); if it
    is missing, returns (True, 0, 0) and prints a notice.
    """
    try:
        from epubcheck import EpubCheck
    except ImportError:
        print("      (epubcheck package not installed -- skipping; "
              "pip install epubcheck)")
        return (True, 0, 0)

    result = EpubCheck(str(epub))
    errors = [m for m in result.messages if m.level == "ERROR"]
    warnings = [m for m in result.messages if m.level == "WARNING"]
    for m in result.messages[:15]:
        print(f"        {m.level}: {m.message[:90]}")
    if len(result.messages) > 15:
        print(f"        ... and {len(result.messages) - 15} more")
    return (result.valid, len(errors), len(warnings))
