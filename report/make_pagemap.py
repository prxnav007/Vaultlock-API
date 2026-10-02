#!/usr/bin/env python
"""Read the rendered PDF and record the printed page number of every TOC entry.

The document already carries real page numbering (roman for the front matter,
arabic for the body) in its footer, and the footer is the first line of text on
each page, so the printed label is read straight off the page rather than
inferred from the PDF page index.
"""
import json
import re
import sys
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent
PDF = ROOT / "vault_api_PBL_report.pdf"
OUT = ROOT / ".pagemap.json"

# key -> text that must appear on the page where that entry starts
ANCHORS = {
    "abstract": "ABSTRACT",
    "lot": "LIST OF TABLES",
    "lof": "LIST OF FIGURES",
    "loa": "LIST OF ABBREVIATIONS",
    "c1": "1.1 BACKGROUND",
    "1.2": "1.2 DRIVING QUESTION",
    "1.3": "1.3 OBJECTIVES",
    "1.4": "1.4 SCOPE AND LIMITATIONS",
    "c2": "2.1 RELATED APPROACHES",
    "2.1.2": "2.1.2 Behavioural and RFM Churn Modelling",
    "2.1.3": "2.1.3 Idempotency in Payment APIs",
    "2.2": "2.2 SUMMARY TABLE",
    "2.3": "2.3 WHAT THIS TOLD US",
    "c3": "3.1 WEEKLY PBL PROGRESS LOG",
    "3.2": "3.2 REQUIREMENTS",
    "3.3": "3.3 FEASIBILITY",
    "c4": "4.1 SYSTEM ARCHITECTURE",
    "4.2": "4.2 BASELINE",
    "4.3": "4.3 PROJECT REFINEMENT",
    "4.4": "4.4 FINAL APPROACH",
    "4.5": "4.5 TESTING AND EXECUTION",
    "c5": "5.1 MODULE DESCRIPTION",
    "5.2": "5.2 KEY CODE SNIPPETS",
    "5.3": "5.3 USER INTERFACE / DEMO",
    "c6": "6.1 EVALUATION METRICS",
    "6.2": "6.2 RESULTS AND MODEL COMPARISON",
    "6.3": "6.3 DISCUSSION",
    "6.4": "6.4 LIMITATIONS",
    "c7": "7.1 INDIVIDUAL REFLECTIONS",
    "7.2": "7.2 TEAM LEARNING",
    "7.3": "7.3 COURSE OUTCOMES",
    "c8": "8.1 CONCLUSION",
    "8.2": "8.2 FUTURE SCOPE",
    "refs": "REFERENCES",
    "appendix": "A.1 PROJECT REPOSITORY",
    "t2.1": "Table 2.1",
    "t3.1": "Table 3.1  Weekly PBL Progress Log",
    "t3.2": "Table 3.2",
    "t6.1": "Table 6.1",
    "t6.2": "Table 6.2",
    "t6.3": "Table 6.3",
    "t6.4": "Table 6.4",
    "t6.5": "Table 6.5",
    "tA.1": "Table A.1",
}
for n in ("4.1", "4.2", "4.3", "4.4", "5.1", "5.2", "5.3", "5.4",
          "6.1", "6.2", "6.3", "6.4", "6.5", "6.6", "6.7"):
    ANCHORS["f" + n] = f"Figure {n}"


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def main():
    doc = pymupdf.open(PDF)
    pages = []
    for page in doc:
        raw = page.get_text().strip()
        label = raw.split("\n")[0].strip() if raw else ""
        pages.append((label, norm(raw)))

    # Every chapter heading, caption and table title is also printed in the
    # front-matter lists, so body anchors must only be searched in the body.
    body_start = next(i for i, (_, b) in enumerate(pages) if "CHAPTER 1" in b)

    def find(needle, lo=0, hi=None):
        n = norm(needle)
        for label, body in pages[lo:hi if hi is not None else len(pages)]:
            if n in body:
                return label
        return None

    mapping, missing = {}, []
    front = {
        "abstract": "Retries and timeouts",     # first words, i.e. the heading page
        "lot": "TABLE NO.",
        "lof": "FIGURE NO.",
        "loa": "Abbreviation Full Form",
    }
    for key, needle in ANCHORS.items():
        if key in front:
            label = find(front[key], 0, body_start)
        else:
            label = find(needle, body_start)
        if label is None:
            missing.append(key)
            label = "—"
        mapping[key] = label

    OUT.write_text(json.dumps(mapping, indent=1, sort_keys=True))
    print(f"wrote {OUT} ({len(mapping) - len(missing)}/{len(ANCHORS)} resolved)")
    if missing:
        print("UNRESOLVED:", ", ".join(missing))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
