# REPORT_NOTES — vault-api PBL report (draft for formatting review)

`vault_api_PBL_report.docx` is a **complete-looking draft**, not a submission. Every number in it is a placeholder chosen to be internally consistent and realistic; none of it has been measured. The ML pipeline and the distributed payment path have not been run.

## How to find the draft content in Word

Every draft value carries the character style **`DraftValue`**, which inherits all its formatting from the surrounding text and so is invisible on the page.

> Home → Styles pane → `DraftValue` → right-click → **Select All N Instance(s)**

There are **203 DraftValue runs** in the document: **127 draft numbers and phrases** across 8 sections, plus **76 draft code listing lines** in Section 5.2.

## Regenerating the document

```sh
python report/make_fig41.py        # Figure 4.1 diagram
python report/build_report.py      # edits a copy of report/_template.docx
libreoffice --headless --convert-to pdf report/vault_api_PBL_report.docx \
    --outdir report
python report/make_pagemap.py      # read printed page numbers out of the PDF
python report/build_report.py      # rebuild so the TOC/LoT/LoF carry them
python report/make_notes.py        # regenerate this file
```

Edit the content constants at the top of `build_report.py`, not the `.docx`: rebuilding overwrites it.

## Unfilled CONFIG items

None. Every CONFIG value was supplied, so no `[Square Bracket]` tokens appear in the document.

Two points worth confirming with the supervisor:

- **Project Co-ordinator** in the Acknowledgement is given as Dr. THIYAGARAJAN (per instruction), replacing the template's Dr. R. Kavitha. Dr. Thiyagarajan is therefore named twice — once as Co-ordinator and once in the added sentence thanking him as our supervisor.
- **Class advisors** are given as Mr. Sateesh, Assistant Professor and Ms. Dharani M.E., Assistant Professor. Initials and qualifications should be checked against the department list.

## Deviations from the template

- Cover title set to 13 pt (template used 18 pt): our title is 104 characters and overflowed the cover page at the template size.
- `BACHELOR OF ENGINEERING` on the cover changed from justified to centred — the template's justification spread it across the line.
- Three empty spacer paragraphs removed (two in the Acknowledgement, two around the Abstract) so both sections fit on one page as they do in the template.
- Figure captions sit in a borderless second row of the placeholder's own table. LibreOffice does not keep a caption with the table above it, and a caption alone at the top of a page looked worse. When the real figures replace the boxes, the captions can move back out to ordinary paragraphs.
- Keep-with-next cleared on code listing lines; the template's listings are short enough to carry it on every line, ours are not and whole listings were being pushed to the next page.
- The template's CrypteX screenshots (Figures 4.1, 5.1–5.3, 6.1) were removed. The four institutional logos and the Vision / Mission / PEO / PO / PSO pages are untouched.

## Figures

**4 are finished diagrams** and **11 are empty framed boxes.** The drawn ones describe the design rather than a measured result, so they are built from `README.md` and `PROJECT_SPEC.md` and will not need replacing when the pipeline runs. Regenerate them with `python report/make_diagrams.py`.

| Figure | Title | Source |
|---|---|---|
| 4.1 | Target System Architecture of vault-api | `make_diagrams.py` → `fig_4_1_architecture.png` |
| 4.2 | Idempotent POST /payments Request Flow | `make_diagrams.py` → `fig_4_2_payment_flow.png` |
| 4.3 | Temporal Formulation on One Merchant Timeline | `make_diagrams.py` → `fig_4_3_temporal.png` |
| 4.4 | Twenty HTTP Requests Resolving to One ML Event | `make_diagrams.py` → `fig_4_4_one_event.png` |

Figure 4.4 is the one diagram carrying a draft number: the **17 duplicate rows from 20 requests**. It must be kept in step with Table 6.4 and the Abstract — edit `fig_4_4()` in `make_diagrams.py` when the real stress-test figure is known.

The remaining boxes all need a running system: six screenshots or terminal captures, and five charts that need real model output.

| Figure | Title | Box height | What it must show |
|---|---|---|---|
| 5.1 | Swagger Interactive API Documentation at /docs | 12 cm | Screenshot of the FastAPI Swagger page at /docs with every route group expanded: POST and GET /merchants, POST and GET /payments, GET /health and GET /merchants/{merchant_id}/churn-risk. Capture it through Nginx so the host and port show the load balancer rather than a single worker. |
| 5.2 | Churn-Risk Endpoint Response for a High-Risk Merchant | 7 cm | Screenshot of the JSON response body from GET /merchants/{merchant_id}/churn-risk for a merchant the model scores as high risk, showing merchant_id, snapshot_at, churn_score, risk_band HIGH, predicted_churn true, the top_factors list with feature names and directions, and model_version. |
| 5.3 | Churn-Risk Dashboard — High-Risk Merchant | 12 cm | Screenshot of the demonstration dashboard for the same high-risk merchant: the churn score and risk band, the merchant's recent payment activity, and the top contributing factors with their direction of effect. Capture the state where the risk band reads HIGH. |
| 5.4 | Churn-Risk Dashboard — Low-Risk Merchant | 12 cm | The same dashboard screen captured for a merchant with steady recent activity, so the score, the risk band and the top factors can be compared directly against Figure 5.3. |
| 6.1 | Class Balance Across the Chronological Splits | 7 cm | Grouped bar chart, one group per split (train, validation, test), showing positive and negative snapshot counts on a log scale, with the positive rate printed above each group. The reader should notice both the severity of the imbalance and that the positive rate is stable across the three periods. |
| 6.2 | Precision–Recall Curves for Models A–D | 7 cm | Precision–recall curves for all four models on the test split: recall on the x-axis, precision on the y-axis, one line per model with PR-AUC in the legend, and a horizontal dashed line at the 0.039 positive-rate baseline. The reader should see the gap between the recency baseline and the two gradient-boosted models, and the smaller but consistent separation between Models C and D. |
| 6.3 | Confusion Matrix for Model D at the Frozen Threshold | 7 cm | A 2×2 confusion matrix heatmap for Model D on the test split at threshold 0.38, with raw counts and row-normalised percentages in each cell, predicted class on the x-axis and true class on the y-axis. |
| 6.4 | SHAP Summary (Beeswarm) for Model D | 7 cm | SHAP beeswarm over the test split, features ordered by mean absolute SHAP value, one point per snapshot coloured by feature value. The reader should be able to see both the global ranking and the direction of each feature's effect — high recency_days pushing risk up, negative frequency_change pushing risk up. |
| 6.5 | SHAP Waterfall for One High-Risk Merchant | 7 cm | SHAP waterfall plot for a single high-risk test snapshot, from the base value to the final score, showing each feature's signed contribution. Use the same merchant as Figures 5.2 and 5.3 so the explanation in the API response can be traced back to this plot. |
| 6.6 | Pytest Report — 38 of 38 Tests Passing | 7 cm | Terminal capture of the full pytest run with -v, showing the unit, integration, concurrency and leakage test files and the final summary line reporting 38 passed. |
| 6.7 | Concurrency Test Output With and Without Idempotency | 7 cm | Side-by-side terminal capture of the stress test: the unprotected run reporting 20 requests and 17 committed payment rows, and the protected run reporting 50 requests, 1 payment row and 1 idempotency record with the 201 / replay / 409 breakdown. The contrast between the two row counts is the headline. |

## Draft code listings (Section 5.2)

No ML pipeline or payment-service code exists in the repository yet — `app/` currently holds only configuration, the database session and `/health`. All four listings are therefore **written-to-spec drafts**, consistent with `PROJECT_SPEC.md` but not copied from running code. Replace each one verbatim from the real file once it lands.

| Listing | Target file | Lines |
|---|---|---|
| Code 5.1 | `ml/features/build_snapshots.py` | 12 |
| Code 5.2 | `ml/features/build_snapshots.py` | 14 |
| Code 5.3 | `ml/train.py` | 18 |
| Code 5.4 | `app/services/payment_service.py` | 32 |

## Draft mentor remarks (Table 3.1)

The Mentor Remarks column is **invented**, written in the template's register to show the table working. Every cell must be confirmed with Dr. Thiyagarajan or replaced with what he actually said at each review. The Work Done column is drafted from the real git history plus the milestone order in `PROJECT_SPEC.md` and is closer to accurate, but should still be checked.

## Every draft value

| Section | Context | Appears in | Draft value(s) | Replace from |
|---|---|---|---|---|
| ABSTRACT | — | Fifty concurrent requests sharing a merchant, body and key committed exactly one payment row, where the same storm unprotected produced 17 rows from 2… | `Fifty`, `17`, `20` | Headline figures — must be kept identical to Chapter 6 and Chapter 8 |
| ABSTRACT | — | Churn was then reformulated away from the base paper's static customer snapshot: the ledger became 141,208 weekly merchant × snapshot observations, ea… | `141,208` | Headline figures — must be kept identical to Chapter 6 and Chapter 8 |
| ABSTRACT | — | RFM and reliability features were given to an XGBoost classifier using scale_pos_weight for a 3.9% positive rate, split chronologically with purge gap… | `3.9%` | Headline figures — must be kept identical to Chapter 6 and Chapter 8 |
| ABSTRACT | — | It reached 0.66 PR-AUC and 0.62 F1 against 0.41 and 0.46 for a recency-only baseline, reliability features adding +0.08, and SHAP supplied the factors… | `0.66`, `0.62`, `0.41`, `0.46`, `+0.08` | Headline figures — must be kept identical to Chapter 6 and Chapter 8 |
| 3.1 WEEKLY PBL PROGRESS LOG | Table 3.1  Weekly PBL Progress Log — row “1–2” | Scope approved. Keep the correctness claim narrow and precise. | `Scope approved. Keep the correctness claim narrow and precise.` | **Draft mentor remarks — to be confirmed with Dr. Thiyagarajan**; Work Done columns from git history |
| 3.1 WEEKLY PBL PROGRESS LOG | Table 3.1  Weekly PBL Progress Log — row “3–4” | Rebuild justified. Fix the domain model before adding Redis or ML. | `Rebuild justified. Fix the domain model before adding Redis or ML.` | **Draft mentor remarks — to be confirmed with Dr. Thiyagarajan**; Work Done columns from git history |
| 3.1 WEEKLY PBL PROGRESS LOG | Table 3.1  Weekly PBL Progress Log — row “5–7” | Good that leakage is tested, not assumed. Validate the ML framing early. | `Good that leakage is tested, not assumed. Validate the ML framing early.` | **Draft mentor remarks — to be confirmed with Dr. Thiyagarajan**; Work Done columns from git history |
| 3.1 WEEKLY PBL PROGRESS LOG | Table 3.1  Weekly PBL Progress Log — row “8–10” | Race demonstration is convincing. Report the before-and-after together. | `Race demonstration is convincing. Report the before-and-after together.` | **Draft mentor remarks — to be confirmed with Dr. Thiyagarajan**; Work Done columns from git history |
| 3.1 WEEKLY PBL PROGRESS LOG | Table 3.1  Weekly PBL Progress Log — row “11–12” | ran the resilience cases and the full suite, 38 of 38 tests passing. | `38 of 38` | **Draft mentor remarks — to be confirmed with Dr. Thiyagarajan**; Work Done columns from git history |
| 3.1 WEEKLY PBL PROGRESS LOG | Table 3.1  Weekly PBL Progress Log — row “11–12” | Complete. Ready for final review. | `Complete. Ready for final review.` | **Draft mentor remarks — to be confirmed with Dr. Thiyagarajan**; Work Done columns from git history |
| 4.5 TESTING AND EXECUTION | Figure 4.4  Twenty HTTP Requests Resolving to One ML Event | Thirty-eight pytest tests cover the system in four groups. | `Thirty-eight` | `pytest -v` summary line |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.1  Synthetic Dataset Statistics — row “Merchants” | 2,000 | `2,000` | `ml/synthetic/generate.py` run log → `data/generated/` row counts |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.1  Synthetic Dataset Statistics — row “History covered” | 24 months (2024-07-01 to 2026-06-30) | `24 months (2024-07-01 to 2026-06-30)` | `ml/synthetic/generate.py` run log → `data/generated/` row counts |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.1  Synthetic Dataset Statistics — row “Random seed” | 42 | `42` | `ml/synthetic/generate.py` run log → `data/generated/` row counts |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.1  Synthetic Dataset Statistics — row “Merchant-level churn” | 304 merchants (15.2%) | `304 merchants (15.2%)` | `ml/synthetic/generate.py` run log → `data/generated/` row counts |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.1  Synthetic Dataset Statistics — row “Logical payments generated” | 1,183,416 | `1,183,416` | `ml/synthetic/generate.py` run log → `data/generated/` row counts |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.1  Synthetic Dataset Statistics — row “Failed attempts” | 48,520 (4.10% overall failure rate) | `48,520 (4.10% overall failure rate)` | `ml/synthetic/generate.py` run log → `data/generated/` row counts |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.1  Synthetic Dataset Statistics — row “Eligible merchant × snapshot rows” | 141,208 | `141,208` | `ml/synthetic/generate.py` run log → `data/generated/` row counts |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.1  Synthetic Dataset Statistics — row “Snapshot-level positive rate” | 5,507 positives (3.90%) | `5,507 positives (3.90%)` | `ml/synthetic/generate.py` run log → `data/generated/` row counts |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.2 gives the chronological split. Random shuffling is forbidden here: because the label looks 60 days forward, a shuffled split would place a merchant's later snapshots in training and its earlier ones in test, and the model would be allowed to learn the future. The splits are cut by snapshot date and separated by 9-week purge gaps, slightly wider than the 60-day horizon, so that no training row's label window overlaps a validation or test decision point. The last test snapshot is 2026-04-26, which still leaves a full 60 days before the dataset ends on 2026-06-30, so every test label is genuinely observable. The positive rate is stable across the three periods, which matters: a large drift would mean the test split was measuring a different problem. Figure 6.1 shows the same balance graphically. | The splits are cut by snapshot date and separated by 9-week purge gaps, slightly wider than the 60-day horizon, so that no training row's label window… | `9-week` | `artifacts/model_metadata.json` → `training_/validation_/test_data_time_range`, split row and positive counts |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.2 gives the chronological split. Random shuffling is forbidden here: because the label looks 60 days forward, a shuffled split would place a merchant's later snapshots in training and its earlier ones in test, and the model would be allowed to learn the future. The splits are cut by snapshot date and separated by 9-week purge gaps, slightly wider than the 60-day horizon, so that no training row's label window overlaps a validation or test decision point. The last test snapshot is 2026-04-26, which still leaves a full 60 days before the dataset ends on 2026-06-30, so every test label is genuinely observable. The positive rate is stable across the three periods, which matters: a large drift would mean the test split was measuring a different problem. Figure 6.1 shows the same balance graphically. | The last test snapshot is 2026-04-26, which still leaves a full 60 days before the dataset ends on 2026-06-30, so every test label is genuinely observ… | `2026-04-26`, `2026-06-30` | `artifacts/model_metadata.json` → `training_/validation_/test_data_time_range`, split row and positive counts |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.2  Chronological Splits and Label Balance — row “Train” | 2024-09-29 to 2025-08-10 | `2024-09-29 to 2025-08-10` | `artifacts/model_metadata.json` → `training_/validation_/test_data_time_range`, split row and positive counts |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.2  Chronological Splits and Label Balance — row “Train” | 46 | `46` | `artifacts/model_metadata.json` → `training_/validation_/test_data_time_range`, split row and positive counts |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.2  Chronological Splits and Label Balance — row “Train” | 98,846 | `98,846` | `artifacts/model_metadata.json` → `training_/validation_/test_data_time_range`, split row and positive counts |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.2  Chronological Splits and Label Balance — row “Train” | 3,862 | `3,862` | `artifacts/model_metadata.json` → `training_/validation_/test_data_time_range`, split row and positive counts |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.2  Chronological Splits and Label Balance — row “Train” | 3.91% | `3.91%` | `artifacts/model_metadata.json` → `training_/validation_/test_data_time_range`, split row and positive counts |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.2  Chronological Splits and Label Balance — row “(purge gap)” | 2025-08-17 to 2025-10-12 | `2025-08-17 to 2025-10-12` | `artifacts/model_metadata.json` → `training_/validation_/test_data_time_range`, split row and positive counts |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.2  Chronological Splits and Label Balance — row “(purge gap)” | 9 | `9`, `9` | `artifacts/model_metadata.json` → `training_/validation_/test_data_time_range`, split row and positive counts |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.2  Chronological Splits and Label Balance — row “Validation” | 2025-10-19 to 2025-12-21 | `2025-10-19 to 2025-12-21` | `artifacts/model_metadata.json` → `training_/validation_/test_data_time_range`, split row and positive counts |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.2  Chronological Splits and Label Balance — row “Validation” | 10 | `10` | `artifacts/model_metadata.json` → `training_/validation_/test_data_time_range`, split row and positive counts |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.2  Chronological Splits and Label Balance — row “Validation” | 21,181 | `21,181` | `artifacts/model_metadata.json` → `training_/validation_/test_data_time_range`, split row and positive counts |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.2  Chronological Splits and Label Balance — row “Validation” | 816 | `816` | `artifacts/model_metadata.json` → `training_/validation_/test_data_time_range`, split row and positive counts |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.2  Chronological Splits and Label Balance — row “Validation” | 3.85% | `3.85%` | `artifacts/model_metadata.json` → `training_/validation_/test_data_time_range`, split row and positive counts |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.2  Chronological Splits and Label Balance — row “(purge gap)” | 2025-12-28 to 2026-02-22 | `2025-12-28 to 2026-02-22` | `artifacts/model_metadata.json` → `training_/validation_/test_data_time_range`, split row and positive counts |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.2  Chronological Splits and Label Balance — row “Test” | 2026-03-01 to 2026-04-26 | `2026-03-01 to 2026-04-26` | `artifacts/model_metadata.json` → `training_/validation_/test_data_time_range`, split row and positive counts |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.2  Chronological Splits and Label Balance — row “Test” | 9 | `9` | `artifacts/model_metadata.json` → `training_/validation_/test_data_time_range`, split row and positive counts |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.2  Chronological Splits and Label Balance — row “Test” | 21,181 | `21,181` | `artifacts/model_metadata.json` → `training_/validation_/test_data_time_range`, split row and positive counts |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.2  Chronological Splits and Label Balance — row “Test” | 829 | `829` | `artifacts/model_metadata.json` → `training_/validation_/test_data_time_range`, split row and positive counts |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.2  Chronological Splits and Label Balance — row “Test” | 3.91% | `3.91%` | `artifacts/model_metadata.json` → `training_/validation_/test_data_time_range`, split row and positive counts |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.2  Chronological Splits and Label Balance — row “Total” | 2024-09-29 to 2026-04-26 | `2024-09-29 to 2026-04-26` | `artifacts/model_metadata.json` → `training_/validation_/test_data_time_range`, split row and positive counts |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.2  Chronological Splits and Label Balance — row “Total” | 83 | `83` | `artifacts/model_metadata.json` → `training_/validation_/test_data_time_range`, split row and positive counts |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.2  Chronological Splits and Label Balance — row “Total” | 141,208 | `141,208` | `artifacts/model_metadata.json` → `training_/validation_/test_data_time_range`, split row and positive counts |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.2  Chronological Splits and Label Balance — row “Total” | 5,507 | `5,507` | `artifacts/model_metadata.json` → `training_/validation_/test_data_time_range`, split row and positive counts |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.2  Chronological Splits and Label Balance — row “Total” | 3.90% | `3.90%` | `artifacts/model_metadata.json` → `training_/validation_/test_data_time_range`, split row and positive counts |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.3  Test-Split Results for Models A–D — row “A — Majority / dummy” | 0.039 | `0.039` | `artifacts/metrics.json` → `model_a|b|c|d.{pr_auc,f1,precision,recall,roc_auc}` |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.3  Test-Split Results for Models A–D — row “A — Majority / dummy” | 0.00 | `0.00`, `0.00` | `artifacts/metrics.json` → `model_a|b|c|d.{pr_auc,f1,precision,recall,roc_auc}` |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.3  Test-Split Results for Models A–D — row “A — Majority / dummy” | 0.50 | `0.50` | `artifacts/metrics.json` → `model_a|b|c|d.{pr_auc,f1,precision,recall,roc_auc}` |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.3  Test-Split Results for Models A–D — row “B — Recency-only threshold” | 0.41 | `0.41` | `artifacts/metrics.json` → `model_a|b|c|d.{pr_auc,f1,precision,recall,roc_auc}` |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.3  Test-Split Results for Models A–D — row “B — Recency-only threshold” | 0.46 | `0.46` | `artifacts/metrics.json` → `model_a|b|c|d.{pr_auc,f1,precision,recall,roc_auc}` |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.3  Test-Split Results for Models A–D — row “B — Recency-only threshold” | 0.44 | `0.44` | `artifacts/metrics.json` → `model_a|b|c|d.{pr_auc,f1,precision,recall,roc_auc}` |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.3  Test-Split Results for Models A–D — row “B — Recency-only threshold” | 0.48 | `0.48` | `artifacts/metrics.json` → `model_a|b|c|d.{pr_auc,f1,precision,recall,roc_auc}` |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.3  Test-Split Results for Models A–D — row “B — Recency-only threshold” | 0.83 | `0.83` | `artifacts/metrics.json` → `model_a|b|c|d.{pr_auc,f1,precision,recall,roc_auc}` |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.3  Test-Split Results for Models A–D — row “C — RFM + tenure XGBoost” | 0.58 | `0.58` | `artifacts/metrics.json` → `model_a|b|c|d.{pr_auc,f1,precision,recall,roc_auc}` |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.3  Test-Split Results for Models A–D — row “C — RFM + tenure XGBoost” | 0.57 | `0.57` | `artifacts/metrics.json` → `model_a|b|c|d.{pr_auc,f1,precision,recall,roc_auc}` |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.3  Test-Split Results for Models A–D — row “C — RFM + tenure XGBoost” | 0.55 | `0.55` | `artifacts/metrics.json` → `model_a|b|c|d.{pr_auc,f1,precision,recall,roc_auc}` |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.3  Test-Split Results for Models A–D — row “C — RFM + tenure XGBoost” | 0.59 | `0.59` | `artifacts/metrics.json` → `model_a|b|c|d.{pr_auc,f1,precision,recall,roc_auc}` |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.3  Test-Split Results for Models A–D — row “C — RFM + tenure XGBoost” | 0.90 | `0.90` | `artifacts/metrics.json` → `model_a|b|c|d.{pr_auc,f1,precision,recall,roc_auc}` |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.3  Test-Split Results for Models A–D — row “D — RFM + failure XGBoost” | 0.66 | `0.66` | `artifacts/metrics.json` → `model_a|b|c|d.{pr_auc,f1,precision,recall,roc_auc}` |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.3  Test-Split Results for Models A–D — row “D — RFM + failure XGBoost” | 0.62 | `0.62` | `artifacts/metrics.json` → `model_a|b|c|d.{pr_auc,f1,precision,recall,roc_auc}` |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.3  Test-Split Results for Models A–D — row “D — RFM + failure XGBoost” | 0.60 | `0.60` | `artifacts/metrics.json` → `model_a|b|c|d.{pr_auc,f1,precision,recall,roc_auc}` |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.3  Test-Split Results for Models A–D — row “D — RFM + failure XGBoost” | 0.65 | `0.65` | `artifacts/metrics.json` → `model_a|b|c|d.{pr_auc,f1,precision,recall,roc_auc}` |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.3  Test-Split Results for Models A–D — row “D — RFM + failure XGBoost” | 0.93 | `0.93` | `artifacts/metrics.json` → `model_a|b|c|d.{pr_auc,f1,precision,recall,roc_auc}` |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.3  Test-Split Results for Models A–D | Its chosen parameters were max_depth 4, learning_rate 0.05, n_estimators 400, min_child_weight 5, subsample 0.8, colsample_bytree 0.8, reg_lambda 1.0 … | `4`, `0.05`, `400`, `5`, `0.8`, `0.8`, `1.0`, `0`, `24.59`, `0.38` | `artifacts/metrics.json` → `model_a|b|c|d.{pr_auc,f1,precision,recall,roc_auc}` |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.3  Test-Split Results for Models A–D | At that threshold its test confusion matrix is 539 true positives, 359 false positives, 290 false negatives and 19,993 true negatives, which sums to t… | `539`, `359`, `290`, `19,993`, `21,181`, `539`, `290` | `artifacts/metrics.json` → `model_a|b|c|d.{pr_auc,f1,precision,recall,roc_auc}` |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.3  Test-Split Results for Models A–D | In plain terms, a retention list built from this model would contain 898 merchants, of whom 539 really did stop transacting, and it would miss 290 who… | `898` | `artifacts/metrics.json` → `model_a|b|c|d.{pr_auc,f1,precision,recall,roc_auc}` |
| 6.2 RESULTS AND MODEL COMPARISON | Figure 6.4 is the SHAP beeswarm over the test split and Figure 6.5 a waterfall for a single high-risk merchant. Ranked by mean absolute SHAP value, the global ordering is recency_days, frequency_change, tx_count_30d, failure_rate_change, failure_rate_30d, monetary_change, tx_count_90d and tenure_days, with the remaining features contributing little. | Ranked by mean absolute SHAP value, the global ordering is recency_days, frequency_change, tx_count_30d, failure_rate_change, failure_rate_30d, moneta… | `recency_days, frequency_change, tx_count_30d, failure_rate_change, failure_rate_30d, monetary_change, tx_count_90d and tenure_days` | `artifacts/metrics.json`, `artifacts/model_metadata.json`, `artifacts/shap_global.json` |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.4  Infrastructure and Resilience Results — row “Concurrency storm” | 50 concurrent POST /payments, same merchant, same body, same idempotency key, through Nginx to 3 FastAPI workers | `50` | `pytest tests/concurrency -v` output and `scripts/stress_test.py` summary |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.4  Infrastructure and Resilience Results — row “Concurrency storm” | Exactly 1 payment row and 1 idempotency record. 1 request received 201 Created, 37 received the replayed stored result, 12 received 409 while the winn… | `Exactly 1 payment row and 1 idempotency record. 1 request received 201 Created, 37 received the replayed stored result, 12 received 409 while the winner was in flight.` | `pytest tests/concurrency -v` output and `scripts/stress_test.py` summary |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.4  Infrastructure and Resilience Results — row “Failure state, no idempotency” | 20 concurrent duplicates against a deliberately naive payment path | `20` | `pytest tests/concurrency -v` output and `scripts/stress_test.py` summary |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.4  Infrastructure and Resilience Results — row “Failure state, no idempotency” | 17 duplicate payment rows committed from one logical operation. | `17 duplicate payment rows committed from one logical operation.` | `pytest tests/concurrency -v` output and `scripts/stress_test.py` summary |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.4  Infrastructure and Resilience Results — row “Same storm, protected” | 20 concurrent duplicates with the PostgreSQL invariant and Redis lock enabled | `20` | `pytest tests/concurrency -v` output and `scripts/stress_test.py` summary |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.4  Infrastructure and Resilience Results — row “Same storm, protected” | 1 payment row. | `1 payment row.` | `pytest tests/concurrency -v` output and `scripts/stress_test.py` summary |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.4  Infrastructure and Resilience Results — row “A — crash before commit” | Transaction rolled back; no payment and no completed record committed; a later retry processed normally. Passing. | `Transaction rolled back; no payment and no completed record committed; a later retry processed normally. Passing.` | `pytest tests/concurrency -v` output and `scripts/stress_test.py` summary |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.4  Infrastructure and Resilience Results — row “B — duplicate after commit” | Stored response replayed byte for byte; no second payment row. Passing. | `Stored response replayed byte for byte; no second payment row. Passing.` | `pytest tests/concurrency -v` output and `scripts/stress_test.py` summary |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.4  Infrastructure and Resilience Results — row “C — lock expires early” | Second insert rejected by the unique constraint; the integrity error was caught, rolled back and resolved to the winner's result. Passing. | `Second insert rejected by the unique constraint; the integrity error was caught, rolled back and resolved to the winner's result. Passing.` | `pytest tests/concurrency -v` output and `scripts/stress_test.py` summary |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.4  Infrastructure and Resilience Results — row “D — key reused, different body” | 409 Conflict; the original payment unchanged. Passing. | `409 Conflict; the original payment unchanged. Passing.` | `pytest tests/concurrency -v` output and `scripts/stress_test.py` summary |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.4  Infrastructure and Resilience Results — row “E — loser retries later” | Replayed the winner's stored result. Passing. | `Replayed the winner's stored result. Passing.` | `pytest tests/concurrency -v` output and `scripts/stress_test.py` summary |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.5  Test Suite Breakdown — row “Unit” | 16 | `16` | `pytest --collect-only -q` counts per directory |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.5  Test Suite Breakdown — row “Integration” | 11 | `11` | `pytest --collect-only -q` counts per directory |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.5  Test Suite Breakdown — row “Concurrency” | 6 | `6` | `pytest --collect-only -q` counts per directory |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.5  Test Suite Breakdown — row “Leakage” | 5 | `5` | `pytest --collect-only -q` counts per directory |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.5  Test Suite Breakdown — row “Total” | 38 | `38` | `pytest --collect-only -q` counts per directory |
| 6.2 RESULTS AND MODEL COMPARISON | Table 6.5  Test Suite Breakdown — row “Total” | All passing | `All passing` | `pytest --collect-only -q` counts per directory |
| 6.3 DISCUSSION | Table 6.5  Test Suite Breakdown | Recency alone is a genuinely strong baseline — 0.41 PR-AUC against a 0.039 floor — which is the result we were most prepared to be embarrassed by, sin… | `0.41`, `0.039` | `pytest --collect-only -q` counts per directory |
| 6.3 DISCUSSION | Table 6.5  Test Suite Breakdown | Adding frequency, monetary and tenure trajectory took PR-AUC to 0.58, and the reason is visible in what the two models can express: recency sees a sin… | `0.58` | `pytest --collect-only -q` counts per directory |
| 6.3 DISCUSSION | Table 6.5  Test Suite Breakdown | Reliability features added a further +0.08 PR-AUC, from 0.58 to 0.66. | `+0.08`, `0.58`, `0.66` | `pytest --collect-only -q` counts per directory |
| 6.3 DISCUSSION | Table 6.5  Test Suite Breakdown | The comparison with the base paper's roughly 90% F1 and 99% AUC [1] needs stating carefully, because our 0.62 F1 looks far worse and the two numbers d… | `0.62` | `pytest --collect-only -q` counts per directory |
| 6.3 DISCUSSION | Table 6.5  Test Suite Breakdown | Our ROC-AUC of 0.93 is the closest like-for-like figure we can offer, and even that is not comparable in any strict sense. | `0.93` | `pytest --collect-only -q` counts per directory |
| 6.4 LIMITATIONS | Table 6.5  Test Suite Breakdown | It orders merchants by risk and the frozen threshold turns it into a decision, but a score of 0.38 does not mean a 38% chance of churn; | `0.38` | `pytest --collect-only -q` counts per directory |
| 7.3 COURSE OUTCOMES — EVIDENCE SUMMARY | Table 6.5  Test Suite Breakdown | CO2 – Supervised learning: an XGBoost binary classifier trained on merchant × snapshot rows with scale_pos_weight for a 3.9% positive class and a smal… | `3.9%` | `pytest --collect-only -q` counts per directory |
| 7.3 COURSE OUTCOMES — EVIDENCE SUMMARY | Table 6.5  Test Suite Breakdown | CO4 – Ensemble methods and comparative analysis: gradient-boosted trees compared against a majority classifier, a single-feature recency rule and an R… | `+0.08` | `pytest --collect-only -q` counts per directory |
| 8.1 CONCLUSION | Table 6.5  Test Suite Breakdown | Nginx, three stateless FastAPI workers, Redis lock leases and a PostgreSQL unique constraint reduced 50 concurrent duplicate requests to exactly one l… | `50`, `17`, `20` | `pytest --collect-only -q` counts per directory |
| 8.1 CONCLUSION | Table 6.5  Test Suite Breakdown | Reformulating churn from a static flag into 141,208 forward-looking merchant × weekly snapshot observations produced a problem that is difficult rathe… | `141,208`, `0.66`, `0.62`, `0.41`, `0.46`, `+0.08` | `pytest --collect-only -q` counts per directory |

## Consistency rules to preserve when substituting real numbers

- The Abstract, Section 6.2 and Section 8.1 must quote the same headline figures (PR-AUC, F1, the recency baseline, the reliability gain, the snapshot count).
- Model D's confusion matrix must sum to the test row count and reproduce its stated precision and recall. The draft uses 539 / 359 / 290 / 19,993 = 21,181, giving precision 0.600, recall 0.650, F1 0.624.
- Per-split row counts must sum to the snapshot total and positives to the positive total (98,846 + 21,181 + 21,181 = 141,208; 3,862 + 816 + 829 = 5,507).
- `scale_pos_weight` must equal training negatives / training positives (94,984 / 3,862 = 24.59).
- Model A's PR-AUC is the test positive rate by definition (829 / 21,181 = 0.039).
- The test split must still leave a full 60 days before the dataset ends (last snapshot 2026-04-26 + 60 d = 2026-06-25 ≤ 2026-06-30).
- The test-suite breakdown must sum to the stated total (16 + 11 + 6 + 5 = 38).
