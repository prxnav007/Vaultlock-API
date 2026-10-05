#!/usr/bin/env python
"""Targeted text edits in the report, located by anchor text rather than index.

Paragraph positions shift whenever anything is inserted or removed, so every
edit here matches on a distinctive phrase. Replacements are applied across a
paragraph's runs while keeping the first matched run's formatting, so the
document's styling is preserved.

    python scripts/edit_report_text.py --list
    python scripts/edit_report_text.py
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from docx import Document

ROOT = Path(__file__).resolve().parents[1]

# (anchor, replacement, why)
EDITS: list[tuple[str, str, str]] = [
    (
        ", and Figures 6.6 and 6.7 show the pytest report and the concurrency "
        "test output",
        "",
        "those two figures were removed: both report backend stress-test "
        "results that this project does not measure",
    ),
]


def replace_in_paragraph(paragraph, old: str, new: str) -> bool:
    """Replace text that may be split across several runs.

    python-docx splits a sentence into runs arbitrarily, so a naive per-run
    replacement misses anything spanning a boundary. The whole paragraph text
    is rebuilt into the first affected run and the rest are blanked.
    """
    text = paragraph.text
    if old not in text:
        return False
    updated = text.replace(old, new)
    if not paragraph.runs:
        return False
    paragraph.runs[0].text = updated
    for run in paragraph.runs[1:]:
        run.text = ""
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docx", default=str(ROOT / "vault_api_PBL_report.docx"))
    parser.add_argument("--list", action="store_true", help="show edits, change nothing")
    args = parser.parse_args(argv)

    if args.list:
        for old, new, why in EDITS:
            print(f"- {why}\n    remove: {old!r}\n    insert: {new!r}\n")
        return 0

    path = Path(args.docx)
    shutil.copy2(path, path.with_suffix(".docx.bak"))
    document = Document(str(path))

    applied = 0
    for old, new, why in EDITS:
        hit = False
        for paragraph in document.paragraphs:
            if replace_in_paragraph(paragraph, old, new):
                hit = True
                applied += 1
                print(f"  edited: {why}")
                break
        if not hit:
            print(f"  ! anchor not found: {old[:60]!r}", file=sys.stderr)

    document.save(str(path))
    print(f"\napplied {applied} of {len(EDITS)} edits")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
