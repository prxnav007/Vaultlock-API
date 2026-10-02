#!/usr/bin/env python
"""Generate report/REPORT_NOTES.md by walking the built document.

Every run carrying the DraftValue character style is a value that must be
replaced with real pipeline output before the final review. This script finds
them all rather than relying on a hand-kept list.
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import docx
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

ROOT = Path(__file__).resolve().parent
DOCX = ROOT / "vault_api_PBL_report.docx"
OUT = ROOT / "REPORT_NOTES.md"

spec = importlib.util.spec_from_file_location("br", ROOT / "build_report.py")
br = importlib.util.module_from_spec(spec)
spec.loader.exec_module(br)

# Where the real value will come from, matched against the section heading.
SOURCES = [
    (r"^Table 6\.1|Synthetic Dataset", "`ml/synthetic/generate.py` run log → `data/generated/` row counts"),
    (r"^Table 6\.2|Chronological Splits", "`artifacts/model_metadata.json` → `training_/validation_/test_data_time_range`, split row and positive counts"),
    (r"^Table 6\.3|Test-Split Results", "`artifacts/metrics.json` → `model_a|b|c|d.{pr_auc,f1,precision,recall,roc_auc}`"),
    (r"^Table 6\.4|Infrastructure and Resilience", "`pytest tests/concurrency -v` output and `scripts/stress_test.py` summary"),
    (r"^Table 6\.5|Test Suite Breakdown", "`pytest --collect-only -q` counts per directory"),
    (r"^Table 3\.1|Weekly PBL", "**Draft mentor remarks — to be confirmed with Dr. Thiyagarajan**; Work Done columns from git history"),
    (r"^Code 5\.", "Replace the listing verbatim with the real file once it exists"),
    (r"6\.1 EVALUATION METRICS", "`artifacts/metrics.json` and `artifacts/model_metadata.json`"),
    (r"6\.2 RESULTS", "`artifacts/metrics.json`, `artifacts/model_metadata.json`, `artifacts/shap_global.json`"),
    (r"6\.3 DISCUSSION", "`artifacts/metrics.json` → PR-AUC per model; `artifacts/shap_global.json` → mean |SHAP| ranking"),
    (r"6\.4 LIMITATIONS", "`artifacts/model_metadata.json` → `classification_threshold`"),
    (r"4\.5 TESTING", "`pytest -v` summary line"),
    (r"7\.3 COURSE OUTCOMES", "`artifacts/metrics.json` and `artifacts/model_metadata.json`"),
    (r"ABSTRACT", "Headline figures — must be kept identical to Chapter 6 and Chapter 8"),
    (r"8\.1 CONCLUSION", "Headline figures — must be kept identical to the Abstract and Chapter 6"),
]
HEADINGS = re.compile(r"^(\d+\.\d+(\.\d+)?\s+[A-Z]|CHAPTER \d|ABSTRACT$|REFERENCES$|APPENDIX$|A\.\d)")


def source_for(section: str, caption: str) -> str:
    for pat, src in SOURCES:
        if re.search(pat, caption or "") or re.search(pat, section or ""):
            return src
    return "—"


def row_label(p_el) -> str | None:
    """First-cell text of the table row a paragraph sits in, if any."""
    el = p_el.getparent()
    while el is not None and el.tag != qn("w:tr"):
        el = el.getparent()
    if el is None:
        return None
    tc = el.find(qn("w:tc"))
    if tc is None:
        return None
    return " ".join("".join(t.text or "" for t in tc.iter(qn("w:t"))).split())[:60]


def walk(body, doc):
    """Flat, document-order pass over every paragraph, table cells included."""
    section = caption = None
    for el in body.iter(qn("w:p")):
        p = Paragraph(el, doc)
        t = p.text.strip()
        label = row_label(el)
        if label is None:                 # headings never live in a table
            if HEADINGS.match(t):
                section = t
            if re.match(r"^(Table|Code|Figure) ", t):
                caption = t
            yield p, section, caption
        else:
            yield p, section, f"{caption} — row “{label}”" if caption else f"row “{label}”"


def sentence_of(text: str, value: str) -> str:
    """The sentence containing value, trimmed for the notes table."""
    parts = re.split(r"(?<=[.;])\s+", text)
    for s in parts:
        if value in s:
            s = s.strip()
            return (s[:150] + "…") if len(s) > 150 else s
    t = text.strip()
    return (t[:150] + "…") if len(t) > 150 else t


def main():
    doc = docx.Document(str(DOCX))
    rows, code_listings = [], []
    for p, section, caption in walk(doc.element.body, doc):
        vals = [r.text for r in p.runs
                if r.style is not None and r.style.name == br.DRAFT_STYLE and r.text.strip()]
        if not vals:
            continue
        if caption and caption.startswith("Code "):
            code_listings.append((caption, p.text, len(vals)))
            continue
        for v in vals:
            rows.append((section or "—", caption or "—", sentence_of(p.text, v), v))

    total = len(rows) + sum(n for _, _, n in code_listings)
    import zipfile
    xml = zipfile.ZipFile(DOCX).read("word/document.xml").decode("utf8")
    expected = xml.count('w:val="%s"' % br.DRAFT_STYLE)
    assert total == expected, f"accounted {total} draft runs but the file has {expected}"

    # collapse identical (section, context, sentence) groups
    grouped: dict[tuple, list[str]] = {}
    for section, caption, sentence, v in rows:
        key = (section, caption, sentence)
        grouped.setdefault(key, []).append(v)

    lines = []
    w = lines.append
    w("# REPORT_NOTES — vault-api PBL report (draft for formatting review)")
    w("")
    w("`vault_api_PBL_report.docx` is a **complete-looking draft**, not a submission. Every "
      "number in it is a placeholder chosen to be internally consistent and realistic; none of "
      "it has been measured. The ML pipeline and the distributed payment path have not been run.")
    w("")
    w("## How to find the draft content in Word")
    w("")
    w("Every draft value carries the character style **`DraftValue`**, which inherits all its "
      "formatting from the surrounding text and so is invisible on the page.")
    w("")
    w("> Home → Styles pane → `DraftValue` → right-click → **Select All N Instance(s)**")
    w("")
    w(f"There are **{expected} DraftValue runs** in the document: **{len(rows)} draft "
      f"numbers and phrases** across {len(set(k[0] for k in grouped))} sections, plus "
      f"**{expected - len(rows)} draft code listing lines** in Section 5.2.")
    w("")
    w("## Regenerating the document")
    w("")
    w("```sh")
    w("python report/make_fig41.py        # Figure 4.1 diagram")
    w("python report/build_report.py      # edits a copy of report/_template.docx")
    w("libreoffice --headless --convert-to pdf report/vault_api_PBL_report.docx \\")
    w("    --outdir report")
    w("python report/make_pagemap.py      # read printed page numbers out of the PDF")
    w("python report/build_report.py      # rebuild so the TOC/LoT/LoF carry them")
    w("python report/make_notes.py        # regenerate this file")
    w("```")
    w("")
    w("Edit the content constants at the top of `build_report.py`, not the `.docx`: rebuilding "
      "overwrites it.")
    w("")
    w("## Unfilled CONFIG items")
    w("")
    w("None. Every CONFIG value was supplied, so no `[Square Bracket]` tokens appear in the "
      "document.")
    w("")
    w("Two points worth confirming with the supervisor:")
    w("")
    w("- **Project Co-ordinator** in the Acknowledgement is given as Dr. THIYAGARAJAN (per "
      "instruction), replacing the template's Dr. R. Kavitha. Dr. Thiyagarajan is therefore "
      "named twice — once as Co-ordinator and once in the added sentence thanking him as our "
      "supervisor.")
    w("- **Class advisors** are given as Mr. Sateesh, Assistant Professor and Ms. Dharani M.E., "
      "Assistant Professor. Initials and qualifications should be checked against the "
      "department list.")
    w("")
    w("## Deviations from the template")
    w("")
    w("- Cover title set to 13 pt (template used 18 pt): our title is 104 characters and "
      "overflowed the cover page at the template size.")
    w("- `BACHELOR OF ENGINEERING` on the cover changed from justified to centred — the "
      "template's justification spread it across the line.")
    w("- Three empty spacer paragraphs removed (two in the Acknowledgement, two around the "
      "Abstract) so both sections fit on one page as they do in the template.")
    w("- Figure captions sit in a borderless second row of the placeholder's own table. "
      "LibreOffice does not keep a caption with the table above it, and a caption alone at the "
      "top of a page looked worse. When the real figures replace the boxes, the captions can "
      "move back out to ordinary paragraphs.")
    w("- Keep-with-next cleared on code listing lines; the template's listings are short enough "
      "to carry it on every line, ours are not and whole listings were being pushed to the next "
      "page.")
    w("- The template's CrypteX screenshots (Figures 4.1, 5.1–5.3, 6.1) were removed. The four "
      "institutional logos and the Vision / Mission / PEO / PO / PSO pages are untouched.")
    w("")
    w("## Figures")
    w("")
    drawn = [n for n in ["4.1"] + list(br.FIGURES) if n in br.DRAWN]
    boxes = [n for n in br.FIGURES if n not in br.DRAWN]
    w(f"**{len(drawn)} are finished diagrams** and **{len(boxes)} are empty framed boxes.** "
      f"The drawn ones describe the design rather than a measured result, so they are built "
      f"from `README.md` and `PROJECT_SPEC.md` and will not need replacing when the pipeline "
      f"runs. Regenerate them with `python report/make_diagrams.py`.")
    w("")
    w("| Figure | Title | Source |")
    w("|---|---|---|")
    w("| 4.1 | Target System Architecture of vault-api | `make_diagrams.py` → "
      "`fig_4_1_architecture.png` |")
    for n in drawn:
        if n == "4.1":
            continue
        w(f"| {n} | {br.FIGURES[n][0]} | `make_diagrams.py` → `{br.DRAWN[n][0]}` |")
    w("")
    w("Figure 4.4 is the one diagram carrying a draft number: the **17 duplicate rows from 20 "
      "requests**. It must be kept in step with Table 6.4 and the Abstract — edit `fig_4_4()` "
      "in `make_diagrams.py` when the real stress-test figure is known.")
    w("")
    w("The remaining boxes all need a running system: six screenshots or terminal captures, "
      "and five charts that need real model output.")
    w("")
    w("| Figure | Title | Box height | What it must show |")
    w("|---|---|---|---|")
    for n in boxes:
        title, desc, h = br.FIGURES[n]
        w(f"| {n} | {title} | {h:g} cm | {desc} |")
    w("")
    w("## Draft code listings (Section 5.2)")
    w("")
    w("No ML pipeline or payment-service code exists in the repository yet — `app/` currently "
      "holds only configuration, the database session and `/health`. All four listings are "
      "therefore **written-to-spec drafts**, consistent with `PROJECT_SPEC.md` but not copied "
      "from running code. Replace each one verbatim from the real file once it lands.")
    w("")
    w("| Listing | Target file | Lines |")
    w("|---|---|---|")
    counts: dict[str, int] = {}
    for cap, _, n in code_listings:
        counts[cap] = counts.get(cap, 0) + n
    for cap, n in counts.items():
        m = re.search(r"\(([^)]+)\)\s*$", cap)
        w(f"| {cap.split('  ')[0]} | `{m.group(1) if m else '—'}` | {n} |")
    w("")
    w("## Draft mentor remarks (Table 3.1)")
    w("")
    w("The Mentor Remarks column is **invented**, written in the template's register to show "
      "the table working. Every cell must be confirmed with Dr. Thiyagarajan or replaced with "
      "what he actually said at each review. The Work Done column is drafted from the real git "
      "history plus the milestone order in `PROJECT_SPEC.md` and is closer to accurate, but "
      "should still be checked.")
    w("")
    w("## Every draft value")
    w("")
    w("| Section | Context | Appears in | Draft value(s) | Replace from |")
    w("|---|---|---|---|---|")
    for (section, caption, sentence) in grouped:
        vals = grouped[(section, caption, sentence)]
        cap = caption if caption != section else "—"
        esc = lambda s: s.replace("|", "\\|")
        w(f"| {esc(section)} | {esc(cap)} | {esc(sentence)} | "
          f"{esc(', '.join('`%s`' % v for v in vals))} | {source_for(section, caption)} |")
    w("")
    w("## Consistency rules to preserve when substituting real numbers")
    w("")
    w("- The Abstract, Section 6.2 and Section 8.1 must quote the same headline figures "
      "(PR-AUC, F1, the recency baseline, the reliability gain, the snapshot count).")
    w("- Model D's confusion matrix must sum to the test row count and reproduce its stated "
      "precision and recall. The draft uses 539 / 359 / 290 / 19,993 = 21,181, giving "
      "precision 0.600, recall 0.650, F1 0.624.")
    w("- Per-split row counts must sum to the snapshot total and positives to the positive "
      "total (98,846 + 21,181 + 21,181 = 141,208; 3,862 + 816 + 829 = 5,507).")
    w("- `scale_pos_weight` must equal training negatives / training positives "
      "(94,984 / 3,862 = 24.59).")
    w("- Model A's PR-AUC is the test positive rate by definition (829 / 21,181 = 0.039).")
    w("- The test split must still leave a full 60 days before the dataset ends "
      "(last snapshot 2026-04-26 + 60 d = 2026-06-25 ≤ 2026-06-30).")
    w("- The test-suite breakdown must sum to the stated total (16 + 11 + 6 + 5 = 38).")
    w("")

    OUT.write_text("\n".join(lines))
    print(f"wrote {OUT}: {len(rows)} draft values, {len(code_listings)} code lines, "
          f"{len(br.FIGURES)} figure boxes")


if __name__ == "__main__":
    main()
