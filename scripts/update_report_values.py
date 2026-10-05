#!/usr/bin/env python
"""Replace the report's drafted numbers with the measured ones.

Every unverified value in the document is wrapped in a run carrying the
`DraftValue` character style, which makes them locatable without guessing at
paragraph indices. This script walks those runs in order within an anchored
paragraph or table cell, checks each one still holds the value it expects, and
swaps in the measured figure. A verified value also loses the `DraftValue`
style, so the count of remaining draft runs is an honest measure of what is
still unsubstantiated.

Values come from the artifacts written by scripts/run_pipeline.py.

Backend numbers -- concurrency storms, duplicate rows, Redis lock behaviour --
are deliberately left marked as drafts: this project measures no such result,
and the sections asserting them are to be removed rather than filled in.

    python scripts/update_report_values.py --check
    python scripts/update_report_values.py
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from docx import Document

ROOT = Path(__file__).resolve().parents[1]
DRAFT_STYLE = "DraftValue"

# --- paragraph anchor -> ordered (expected draft, replacement) --------------
# `None` as a replacement means "leave it, and keep it marked as a draft".
PARAGRAPH_EDITS: list[tuple[str, list[tuple[str, str | None]]]] = [
    # Abstract. The concurrency figures stay drafted.
    (
        "Retries and timeouts make the same logical payment reach",
        [
            ("Fifty", None), ("17", None), ("20", None),
            ("141,208", "116,464"), ("3.9%", "4.0%"),
            ("0.66", "0.289"), ("0.62", "0.346"),
            ("0.41", "0.240"), ("0.46", "0.315"), ("+0.08", "+0.014"),
        ],
    ),
    # 6.1 Evaluation metrics
    (
        "Churn here is a rare event",
        [("3.9%", "4.0%"), ("96.1%", "96.0%")],
    ),
    (
        "PR-AUC is the headline metric",
        [("0.039", "0.040"), ("20,352", "14,391"), ("829", "606")],
    ),
    # 6.2 Splits — these were drafted but turn out to be correct as written.
    (
        "Table 6.2 gives the chronological split",
        [("9-week", "9-week"), ("2026-04-26", "2026-04-26"),
         ("2026-06-30", "2026-06-30")],
    ),
    # Model D configuration and confusion matrix
    (
        "Model D was selected",
        [
            ("4", "3"), ("0.05", "0.05"), ("400", "300"), ("5", "1"),
            ("0.8", "0.8"), ("0.8", "0.8"), ("1.0", "1.0"), ("0", "0"),
            ("24.59", "23.36"), ("0.38", "0.84"),
            ("539", "288"), ("359", "770"), ("290", "318"),
            ("19,993", "13,621"), ("21,181", "14,997"),
            ("898", "1,058"), ("539", "288"), ("290", "318"),
        ],
    ),
    # 6.3 Discussion
    (
        "The central question was whether trajectory and reliability",
        [("0.41", "0.240"), ("0.039", "0.040"), ("0.58", "0.275")],
    ),
    (
        "Reliability features added a further",
        [("+0.08", "+0.014"), ("0.58", "0.275"), ("0.66", "0.289")],
    ),
    (
        "The comparison with the base paper",
        [("0.62", "0.35"), ("0.93", "0.90")],
    ),
    (
        "The churn_score is uncalibrated",
        [("0.38", "0.84")],
    ),
    # 7.3 Course outcomes
    ("CO2 – Supervised learning", [("3.9%", "4.0%")]),
    ("CO4 – Ensemble methods", [("+0.08", "+0.014")]),
    # 8.1 Conclusion. Concurrency figures stay drafted.
    (
        "vault-api set out to ask whether a duplicate-free payment ledger",
        [
            ("50", None), ("17", None), ("20", None),
            ("141,208", "116,464"),
            ("0.66", "0.289"), ("0.62", "0.346"),
            ("0.41", "0.240"), ("0.46", "0.315"), ("+0.08", "+0.014"),
        ],
    ),
]

# Code 5.3 quotes the chosen hyperparameters. Its draft runs are
# syntax-highlighting fragments rather than one run per value, so these are
# matched on run text instead of by position.
CODE_EDITS: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "max_depth=4, learning_rate=0.05, n_estimators=400",
        [("=4, ", "=3, "), ("=400,", "=300,")],
    ),
    (
        "min_child_weight=5, subsample=0.8",
        [("=5, subsample=0.8, ", "=1, subsample=0.8, ")],
    ),
    (
        "scale_pos_weight=negatives / positives",
        [("# 24.59, training split only", "# 23.36, training split only")],
    ),
    (
        "threshold = max(np.arange",
        [("(0.05, 0.95, 0.01),", "(0.01, 1.00, 0.01),")],
    ),
]

# --- table cell overwrites: (header marker, row label, column, value) -------
TABLE_EDITS: list[tuple[str, str, int, str]] = [
    # Table 6.1 — the generated dataset
    ("Property", "History covered", 1, "24 months (2024-06-30 to 2026-06-30)"),
    ("Property", "Merchant-level churn", 1, "295 merchants (14.8%)"),
    ("Property", "Logical payments generated", 1, "925,805"),
    ("Property", "Failed attempts", 1, "39,229 (4.24% overall failure rate)"),
    ("Property", "Eligible merchant × snapshot rows", 1, "116,464"),
    ("Property", "Snapshot-level positive rate", 1, "5,283 positives (4.54%)"),
    # Table 6.2 — chronological splits
    ("Split", "Train", 3, "55,001"),
    ("Split", "Train", 4, "2,258"),
    ("Split", "Train", 5, "4.11%"),
    ("Split", "Validation", 3, "16,860"),
    ("Split", "Validation", 4, "895"),
    ("Split", "Validation", 5, "5.31%"),
    ("Split", "Test", 3, "14,997"),
    ("Split", "Test", 4, "606"),
    ("Split", "Test", 5, "4.04%"),
    ("Split", "Total", 2, "65"),
    ("Split", "Total", 3, "86,858"),
    ("Split", "Total", 4, "3,759"),
    ("Split", "Total", 5, "4.33%"),
    # Table 6.3 — the four models on the test split
    ("Model", "A — Majority / dummy", 1, "0.040"),
    ("Model", "A — Majority / dummy", 2, "0.000"),
    ("Model", "A — Majority / dummy", 4, "0.000"),
    ("Model", "A — Majority / dummy", 5, "—"),
    ("Model", "B — Recency-only threshold", 1, "0.240"),
    ("Model", "B — Recency-only threshold", 2, "0.315"),
    ("Model", "B — Recency-only threshold", 3, "0.245"),
    ("Model", "B — Recency-only threshold", 4, "0.442"),
    ("Model", "B — Recency-only threshold", 5, "0.851"),
    ("Model", "C — RFM + tenure XGBoost", 1, "0.275"),
    ("Model", "C — RFM + tenure XGBoost", 2, "0.333"),
    ("Model", "C — RFM + tenure XGBoost", 3, "0.250"),
    ("Model", "C — RFM + tenure XGBoost", 4, "0.500"),
    ("Model", "C — RFM + tenure XGBoost", 5, "0.892"),
    ("Model", "D — RFM + failure XGBoost", 1, "0.289"),
    ("Model", "D — RFM + failure XGBoost", 2, "0.346"),
    ("Model", "D — RFM + failure XGBoost", 3, "0.272"),
    ("Model", "D — RFM + failure XGBoost", 4, "0.475"),
    ("Model", "D — RFM + failure XGBoost", 5, "0.895"),
]

# The SHAP sentence is rewritten rather than substituted: the measured ordering
# puts a different feature first, so swapping names inside the old sentence
# would leave a claim that no longer follows from the figure beside it.
SHAP_SENTENCE_ANCHOR = "Figure 6.4 is the SHAP beeswarm over the test split"
SHAP_SENTENCE_NEW = (
    "Figure 6.4 is the SHAP beeswarm over the test split and Figure 6.5 a "
    "waterfall for a single high-risk merchant. Ranked by mean absolute SHAP "
    "value, the global ordering is tx_count_30d, recency_days, tx_count_90d, "
    "tx_count_prev_30d, tenure_days, frequency_change, avg_success_amount_30d, "
    "avg_success_amount_prev_30d, failure_rate_30d, failure_rate_change, "
    "monetary_change and failure_rate_prev_30d. That recent transaction count "
    "outranks recency is the more interesting half of this result: the model is "
    "not simply re-deriving how long ago the merchant last paid, which is what "
    "the recency baseline already does, but reading how much activity remains "
    "in the recent window. The reliability features sit mid-table, consistent "
    "with the small and statistically unresolved improvement they give in "
    "Table 6.3."
)


def draft_runs(container):
    out = []
    for paragraph in container:
        for run in paragraph.runs:
            if run.style is not None and run.style.name == DRAFT_STYLE:
                out.append(run)
    return out


def clear_draft(run, document) -> None:
    run.style = document.styles["Default Paragraph Font"]


def apply_paragraph_edits(document, dry: bool) -> tuple[int, list[str]]:
    changed, problems = 0, []
    for anchor, pairs in PARAGRAPH_EDITS:
        target = next(
            (p for p in document.paragraphs if anchor in p.text), None
        )
        if target is None:
            problems.append(f"anchor not found: {anchor[:50]!r}")
            continue
        runs = draft_runs([target])
        if len(runs) != len(pairs):
            problems.append(
                f"{anchor[:40]!r}: expected {len(pairs)} draft runs, found "
                f"{len(runs)} -> {[r.text for r in runs]}"
            )
            continue
        for run, (expected, replacement) in zip(runs, pairs):
            if run.text != expected:
                problems.append(
                    f"{anchor[:40]!r}: expected {expected!r}, found {run.text!r}"
                )
                continue
            if replacement is None:
                continue
            if not dry:
                run.text = replacement
                clear_draft(run, document)
            changed += 1
    return changed, problems


def apply_code_edits(document, dry: bool) -> tuple[int, list[str]]:
    """Replace exact run text inside the code listings."""
    changed, problems = 0, []
    for anchor, pairs in CODE_EDITS:
        target = next((p for p in document.paragraphs if anchor in p.text), None)
        if target is None:
            problems.append(f"code anchor not found: {anchor[:50]!r}")
            continue
        for old, new in pairs:
            hit = False
            for run in target.runs:
                if run.text == old:
                    if not dry:
                        run.text = new
                        clear_draft(run, document)
                    hit = True
                    changed += 1
                    break
            if not hit:
                problems.append(f"{anchor[:34]!r}: no run equal to {old!r}")
    return changed, problems


def apply_table_edits(document, dry: bool) -> tuple[int, list[str]]:
    changed, problems = 0, []
    for header, label, column, value in TABLE_EDITS:
        table = next(
            (t for t in document.tables if t.rows[0].cells[0].text.strip() == header),
            None,
        )
        if table is None:
            problems.append(f"no table with header {header!r}")
            continue
        row = next(
            (r for r in table.rows if r.cells[0].text.strip() == label), None
        )
        if row is None:
            problems.append(f"table {header!r}: no row {label!r}")
            continue
        cell = row.cells[column]
        if dry:
            changed += 1
            continue
        paragraph = cell.paragraphs[0]
        if paragraph.runs:
            first = paragraph.runs[0]
            first.text = value
            clear_draft(first, document)
            for extra in paragraph.runs[1:]:
                extra.text = ""
        else:
            paragraph.add_run(value)
        for extra_paragraph in cell.paragraphs[1:]:
            for run in extra_paragraph.runs:
                run.text = ""
        changed += 1
    return changed, problems


def apply_shap_rewrite(document, dry: bool) -> bool:
    target = next(
        (p for p in document.paragraphs if SHAP_SENTENCE_ANCHOR in p.text), None
    )
    if target is None:
        return False
    if not dry:
        target.runs[0].text = SHAP_SENTENCE_NEW
        clear_draft(target.runs[0], document)
        for run in target.runs[1:]:
            run.text = ""
    return True


def count_drafts(document) -> int:
    total = len(draft_runs(document.paragraphs))
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                total += len(draft_runs(cell.paragraphs))
    return total


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docx", default=str(ROOT / "vault_api_PBL_report.docx"))
    parser.add_argument("--check", action="store_true", help="validate, change nothing")
    args = parser.parse_args(argv)

    path = Path(args.docx)
    document = Document(str(path))
    before = count_drafts(document)

    para_changed, para_problems = apply_paragraph_edits(document, args.check)
    code_changed, code_problems = apply_code_edits(document, args.check)
    table_changed, table_problems = apply_table_edits(document, args.check)
    shap_ok = apply_shap_rewrite(document, args.check)

    for problem in para_problems + code_problems + table_problems:
        print(f"  ! {problem}", file=sys.stderr)
    if not shap_ok:
        print("  ! SHAP sentence anchor not found", file=sys.stderr)

    print(f"\nparagraph values: {para_changed}")
    print(f"code listing:     {code_changed}")
    print(f"table cells:      {table_changed}")
    print(f"SHAP sentence:    {'rewritten' if shap_ok else 'NOT FOUND'}")

    if args.check:
        print(f"\ncheck only; {before} draft runs currently in the document")
        return 1 if (para_problems or code_problems or table_problems) else 0

    shutil.copy2(path, path.with_suffix(".docx.bak"))
    document.save(str(path))
    after = count_drafts(Document(str(path)))
    print(f"\ndraft runs: {before} -> {after} (remaining are backend claims)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
