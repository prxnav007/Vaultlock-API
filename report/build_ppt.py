"""Fill the PBL Final Review template with the vault-api churn-prediction content.

Reads  : "PBL Final Review Template(1).pptx"  (untouched)
Writes : "vault_api_PBL_final_review.pptx"

Every number comes from artifacts/report_facts.json, artifacts/metrics.json and
the report in vault_api_PBL_report.docx.  The template's own shapes, fonts,
colours, logos and slide order are preserved; only the placeholder text is
replaced and figures from report/ are placed into the content boxes.
"""

from __future__ import annotations

import copy
from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.util import Emu, Inches, Pt
from pptx.oxml.ns import qn

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "PBL Final Review Template(1).pptx"
OUTPUT = ROOT / "vault_api_PBL_final_review.pptx"
FIG = ROOT / "report"
SHOT = FIG / "screenshots"

DATE = "Date: 07/10/2026"

TITLE = (
    "VAULT-API: Idempotent Payment Infrastructure with Explainable "
    "Transaction-Driven Merchant Churn Prediction"
)

# --------------------------------------------------------------------------- #
# low-level helpers
# --------------------------------------------------------------------------- #

HEAD, BODY, NOTE = "head", "body", "note"


def _shapes_by_id(slide):
    return {sh.shape_id: sh for sh in slide.shapes}


def _clear_autofit_scale(tf):
    """Drop a stored fontScale so the sizes we set are the sizes that render."""
    bodyPr = tf._txBody.bodyPr
    for na in bodyPr.findall(qn("a:normAutofit")):
        na.attrib.pop("fontScale", None)
        na.attrib.pop("lnSpcReduction", None)


def _template_paragraphs(tf):
    """Return (head_xml, body_xml): deep-copyable paragraph prototypes."""
    paras = [p for p in tf.paragraphs if p.runs]
    if not paras:
        raise ValueError("no text in template shape")
    head = copy.deepcopy(paras[0]._p)
    body = copy.deepcopy(paras[1]._p) if len(paras) > 1 else copy.deepcopy(paras[0]._p)
    return head, body


def _set_para(p_el, text, *, size, bold=None, italic=None, bullet=False,
              space_before_pt=None, align=None):
    """Keep the first run of a cloned paragraph, retype it, drop the others."""
    runs = p_el.findall(qn("a:r"))
    if not runs:
        return
    first = runs[0]
    for extra in runs[1:]:
        p_el.remove(extra)
    for br in p_el.findall(qn("a:br")):
        p_el.remove(br)
    t = first.find(qn("a:t"))
    t.text = text

    rPr = first.find(qn("a:rPr"))
    rPr.set("sz", str(int(size * 100)))
    if bold is not None:
        rPr.set("b", "1" if bold else "0")
    if italic is not None:
        rPr.set("i", "1" if italic else "0")

    pPr = p_el.find(qn("a:pPr"))
    if pPr is None:
        pPr = p_el.makeelement(qn("a:pPr"), {})
        p_el.insert(0, pPr)
    pPr.set("algn", align if align is not None else "l")

    # bullet / indent
    for tag in ("a:buNone", "a:buChar", "a:buFont", "a:buAutoNum"):
        for el in pPr.findall(qn(tag)):
            pPr.remove(el)
    if bullet:
        pPr.set("marL", "171450")
        pPr.set("indent", "-171450")
        bu_font = pPr.makeelement(
            qn("a:buFont"), {"typeface": "Arial", "pitchFamily": "34", "charset": "0"}
        )
        bu_char = pPr.makeelement(qn("a:buChar"), {"char": "•"})
        pPr.append(bu_font)
        pPr.append(bu_char)
    else:
        pPr.set("marL", "0")
        pPr.set("indent", "0")
        pPr.append(pPr.makeelement(qn("a:buNone"), {}))

    if space_before_pt is not None:
        for el in pPr.findall(qn("a:spcBef")):
            pPr.remove(el)
        spc = pPr.makeelement(qn("a:spcBef"), {})
        pts = spc.makeelement(qn("a:spcPts"), {"val": str(int(space_before_pt * 100))})
        spc.append(pts)
        pPr.insert(0, spc)


def fill(shape, blocks, *, head_pt=18, body_pt=13, note_pt=11, bullets=True):
    """Rewrite a text frame from a list of (kind, text) blocks."""
    tf = shape.text_frame
    tf.word_wrap = True
    _clear_autofit_scale(tf)
    head_xml, body_xml = _template_paragraphs(tf)
    txBody = tf._txBody
    for p in txBody.findall(qn("a:p")):
        txBody.remove(p)

    for i, (kind, text) in enumerate(blocks):
        if kind == HEAD:
            el = copy.deepcopy(head_xml)
            _set_para(el, text, size=head_pt, bold=True, italic=False,
                      bullet=False, space_before_pt=0, align="ctr")
        elif kind == NOTE:
            el = copy.deepcopy(body_xml)
            _set_para(el, text, size=note_pt, bold=False, italic=True,
                      bullet=False, space_before_pt=6)
        else:
            el = copy.deepcopy(body_xml)
            _set_para(el, text, size=body_pt, bold=False, italic=False,
                      bullet=bullets, space_before_pt=0 if i <= 1 else 4)
        txBody.append(el)


def place(slide, name, box, *, fig_dir=FIG):
    """Fit an image inside (left, top, width, height) inches, centred."""
    left, top, width, height = box
    path = fig_dir / name
    iw, ih = Image.open(path).size
    aspect = iw / ih
    w = width
    h = w / aspect
    if h > height:
        h = height
        w = h * aspect
    pic = slide.shapes.add_picture(
        str(path),
        Inches(left + (width - w) / 2),
        Inches(top + (height - h) / 2),
        Inches(w),
        Inches(h),
    )
    return pic


def caption(slide, text, box, *, size=10):
    left, top, width, height = box
    tb = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    p = tf.paragraphs[0]
    p.alignment = 2  # centre
    r = p.add_run()
    r.text = text
    r.font.size = Pt(size)
    r.font.italic = True
    r.font.name = "Times New Roman"
    return tb


def box(shape, left=None, top=None, width=None, height=None):
    if left is not None:
        shape.left = Inches(left)
    if top is not None:
        shape.top = Inches(top)
    if width is not None:
        shape.width = Inches(width)
    if height is not None:
        shape.height = Inches(height)


# --------------------------------------------------------------------------- #
# build
# --------------------------------------------------------------------------- #

prs = Presentation(str(TEMPLATE))
slides = list(prs.slides)

# ---- every slide: date stamp -------------------------------------------- #
for s in slides:
    for sh in s.shapes:
        if sh.has_text_frame and sh.text_frame.text.startswith("Date:"):
            sh.text_frame.paragraphs[0].runs[0].text = DATE

# ======================= SLIDE 1 — title ================================= #
s1 = _shapes_by_id(slides[0])

t = s1[11]                                   # "TITLE OF THE PROJECT"
box(t, left=0.92, top=3.05, width=11.50)
fill(t, [(HEAD, TITLE)], head_pt=20)

fill(
    s1[8],
    [
        (HEAD, "Presentation by"),
        (BODY, "PRANAV KUMAR GATTUPALLI  (2104251040699)"),
        (BODY, "MONIKA P D  (2104251040682)"),
        (BODY, "Dept. of Computer Science and Engineering"),
    ],
    head_pt=20,
    body_pt=16,
    bullets=False,
)
for p in s1[8].text_frame.paragraphs:
    p.alignment = 1  # left

fill(
    s1[12],
    [
        (HEAD, "Mentor"),
        (BODY, "Dr. THIYAGARAJAN, Ph.D."),
        (BODY, "Associate Professor"),
        (BODY, "Dept. of Computer Science and Engineering"),
    ],
    head_pt=20,
    body_pt=16,
    bullets=False,
)
for p in s1[12].text_frame.paragraphs:
    p.alignment = 1

# ======================= SLIDE 2 — problem & objectives ================== #
s2 = _shapes_by_id(slides[1])

box(s2[3], height=2.80)
fill(
    s2[3],
    [
        (HEAD, "Problem Statement"),
        (BODY, "Merchants disengage silently — there is no cancellation event, only "
               "payment attempts that stop. By the time the drop shows up in a revenue "
               "report, the merchant is already gone."),
        (BODY, "Standard churn models, including our base paper [1], learn from a static "
               "customer table: one row per customer, a churn label inherited with the "
               "dataset, and a random train/test split. That classifies a state which "
               "already exists — it does not forecast, and a random split on temporal "
               "data lets the model train on the future and test on the past."),
        (BODY, "Affected: payment platforms and their retention teams, who need a ranked "
               "list of which merchants are leaving — and why — weeks before they go."),
        (BODY, "Why it matters: only 4.0% of merchant-weeks are churn, so a model that "
               "always predicts “active” is 96.0% accurate and completely useless. "
               "The problem demands imbalance-aware metrics and per-merchant explanations."),
        (NOTE, "Prerequisite solved first: retried HTTP requests that commit duplicate "
               "payment rows inflate the transaction-frequency features the model reads, "
               "so the ledger had to be made duplicate-free before any of this was measurable."),
    ],
)

box(s2[6], height=2.86)
fill(
    s2[6],
    [
        (HEAD, "Objective"),
        (BODY, "Reformulate churn as a forward-looking task: one row per merchant per week, "
               "a 90-day observation window, label = zero payment attempts in the next 60 days."),
        (BODY, "Engineer 12 leakage-safe RFM and payment-reliability features, and prove the "
               "leakage rules with tests rather than assuming them."),
        (BODY, "Train an XGBoost classifier under 4% class imbalance with scale_pos_weight, "
               "on chronological splits separated by purge gaps."),
        (BODY, "Benchmark against a majority classifier, a recency-only rule and an "
               "RFM-only model, so any gain is measured against the simpler explanation."),
        (BODY, "Explain every prediction with SHAP and serve it through a churn-risk endpoint."),
    ],
)

box(s2[9], height=2.86)
fill(
    s2[9],
    [
        (HEAD, "Expected Outcome"),
        (BODY, "A leakage-safe, explainable merchant-churn model that beats a recency-only "
               "rule on PR-AUC and F1 under heavy class imbalance."),
        (BODY, "Achieved — PR-AUC 0.289 and F1 0.346 on a test period scored once, "
               "against 0.240 / 0.315 for recency alone and a 0.040 positive-rate floor "
               "(7.2× the floor); ROC-AUC 0.895."),
        (BODY, "A ranked retention list that arrives with its reasons: "
               "GET /merchants/{id}/churn-risk returns churn_score, risk band and the "
               "top SHAP factors with their direction."),
        (NOTE, "Supporting outcome: 50 concurrent duplicate requests commit exactly one "
               "payment row, which is what keeps the frequency features honest."),
    ],
)

# ======================= SLIDE 3 — input, analysis, insights ============= #
s3 = _shapes_by_id(slides[2])

fill(
    s3[6],
    [
        (HEAD, "Input / Data Sources"),
        (BODY, "Reproducible synthetic payment ledger — ml/synthetic/generate.py, "
               "fixed seed 42; no real merchant ledger was available."),
        (BODY, "2,000 merchants · 24 months (2024-06-30 → 2026-06-30) · "
               "925,805 logical payments · 39,229 failed attempts (4.24%)."),
        (BODY, "295 merchants (14.8%) churn, through gradual, abrupt and straggler "
               "disengagement modes, so the trajectories are not all alike."),
        (BODY, "Derived input: 116,464 eligible merchant × snapshot rows, 5,283 "
               "positive (4.54%); cadence 7 d, window 90 d, horizon 60 d."),
        (BODY, "12 features, all computed from ledger facts. industry is stored but "
               "withheld from the model — the generator assigns it, so it would be a shortcut."),
    ],
)

box(s3[13], height=2.80)
fill(
    s3[13],
    [
        (HEAD, "Key Insights"),
        (BODY, "Recency alone is a strong baseline — 0.240 PR-AUC against a 0.040 floor. "
               "Any model has to beat “hasn’t paid in a while.”"),
        (BODY, "Trajectory earns its place: RFM + tenure lifts PR-AUC to 0.275. "
               "frequency_change separates a merchant falling from 30 payments to 8 from one "
               "who always made 8 — same recency, different future."),
        (BODY, "SHAP ranks tx_count_30d above recency_days: the model reads how much activity "
               "remains, not merely how long ago the last payment was."),
        (BODY, "Reliability features add +0.014 PR-AUC, but the merchant-grouped bootstrap CI "
               "[−0.002, +0.031] spans zero — reported as unresolved, not as a win."),
        (BODY, "A leakage test caught recency measured over the uncut frame — a bug that "
               "would have improved every metric in the report."),
    ],
)

fill(
    s3[9],
    [
        (HEAD, "Analysis / Processing"),
        (BODY, "Weekly snapshots: walk each merchant forward in 7-day steps; at snapshot t "
               "use only payments with created_at ≤ t over the preceding 90 days, and look "
               "into (t, t + 60 d] for the label alone."),
        (BODY, "Eligibility: tenure ≥ 90 d, a full 60 d of data after t, and ≥ 1 attempt "
               "in the prior 60 d — keeping the population to merchants who have not already "
               "obviously left. FAILED attempts count as activity, not absence."),
        (BODY, "Chronological split with 9-week purge gaps — train 55,001 / validation "
               "16,860 / test 14,997 rows — so no training label window overlaps a later "
               "decision point. Positive rate stays stable at 4.1% / 5.3% / 4.0%."),
        (BODY, "Imbalance handled by scale_pos_weight = 23.36 (train negatives ÷ positives) "
               "rather than SMOTEENN: reweighting leaves the temporal structure untouched."),
        (BODY, "Threshold 0.84 chosen on validation for F1, then frozen; the test split was "
               "scored exactly once."),
    ],
)
box(s3[9], height=3.00)
place(slides[2], "fig_class_balance.png", (6.82, 4.15, 5.94, 2.70))
caption(slides[2], "Class balance across the chronological splits — train / validation / test",
        (6.82, 6.86, 5.94, 0.20))

# ======================= SLIDE 4 — technical approach ==================== #
s4 = _shapes_by_id(slides[3])

box(s4[11], top=1.00, height=0.95)
fill(
    s4[11],
    [
        (HEAD, "Architecture"),
        (BODY, "Nginx → 3 stateless FastAPI workers → Redis coordination + PostgreSQL "
               "ledger. The offline ML path (feature generation → XGBoost → SHAP) "
               "runs outside the request path and feeds the churn-risk API."),
    ],
    body_pt=12,
)
place(slides[3], "fig_architecture.png", (0.58, 1.98, 5.94, 3.50))
caption(slides[3], "Figure 4.1 — Target system architecture of vault-api",
        (0.58, 5.50, 5.94, 0.20))

box(s4[17], top=5.80, height=1.15)
fill(
    s4[17],
    [
        (HEAD, "Technology Stack"),
        (BODY, "ML: Python 3.12, XGBoost, SHAP, scikit-learn, pandas, NumPy"),
        (BODY, "Serving: FastAPI, Pydantic v2, SQLAlchemy 2.x (async), Uvicorn"),
        (BODY, "Infra: PostgreSQL 16, Redis 7, Nginx, Docker Compose, Alembic"),
        (BODY, "Testing: pytest, pytest-asyncio, httpx; Parquet model artifacts"),
    ],
    head_pt=16,
    body_pt=12,
)

box(s4[13], top=1.00, height=2.55)
fill(
    s4[13],
    [
        (HEAD, "ML Methodology and Implementation Process"),
        (BODY, "Pipeline: generate ledger → build merchant × snapshot features → "
               "chronological split with purge gaps → train XGBoost (scale_pos_weight "
               "23.36) → freeze the threshold on validation → score the test split once "
               "→ SHAP → serve GET /merchants/{id}/churn-risk."),
        (BODY, "Model D (selected): max_depth 3, learning_rate 0.05, n_estimators 300, "
               "min_child_weight 1, subsample 0.8, colsample_bytree 0.8, reg_lambda 1, reg_alpha 0."),
        (BODY, "Leakage control is the method, not a detail: features see created_at ≤ t "
               "only; the label alone may read (t, t + 60 d]; five tests enforce it."),
    ],
    body_pt=12,
)
place(slides[3], "fig_temporal.png", (6.82, 3.58, 5.94, 3.05))
caption(slides[3], "Figure 4.4 — Temporal formulation on one merchant timeline: "
                   "90-day window, 60-day forward label, weekly cadence",
        (6.82, 6.66, 5.94, 0.30))

# ======================= SLIDE 5 — feasibility, risk, mitigation ========= #
s5 = _shapes_by_id(slides[4])

box(s5[11], height=2.50)
fill(
    s5[11],
    [
        (HEAD, "Feasibility"),
        (BODY, "No paid API, no cloud account and no dataset-access delay — the whole "
               "ledger regenerates from seed 42 in minutes."),
        (BODY, "116,464 × 12 tabular rows train with XGBoost in minutes on an 8 GB "
               "laptop CPU; no GPU is required anywhere in the pipeline."),
        (BODY, "The full stack — Nginx, three API workers, PostgreSQL and Redis — "
               "comes up from one docker-compose.yml on a single machine."),
        (BODY, "Reproducible by construction: xgboost_model.json plus model_metadata.json "
               "pin the feature order, window, horizon and frozen threshold."),
    ],
)

box(s5[13], height=4.55)
fill(
    s5[13],
    [
        (HEAD, "Risk and Challenges"),
        (BODY, "Label leakage — the largest ML risk, and one we hit. recency_days was "
               "first computed over the merchant’s whole history, so for exactly the "
               "merchants about to churn it read the future. It would have raised every "
               "score, and no metric would have revealed it."),
        (BODY, "Severe class imbalance — 4.0% positives, so accuracy is meaningless and "
               "ROC-AUC is visually optimistic with 14,391 negatives against 606 positives."),
        (BODY, "A trivially easy problem — our first generator produced data a recency "
               "threshold almost solved; a synthetic world can be accidentally separable."),
        (BODY, "Temporal structure — a shuffled split would place a merchant’s later "
               "snapshots in training and its earlier ones in test."),
        (BODY, "Unresolved effect size — the +0.014 PR-AUC from reliability features sits "
               "inside bootstrap noise at a single generator seed."),
        (BODY, "Uncalibrated output — churn_score orders merchants; it is not a probability."),
        (BODY, "Duplicate behavioural events — retried requests inflate transaction counts "
               "and corrupt the frequency features at source."),
    ],
)

box(s5[15], top=3.75, height=3.10)
fill(
    s5[15],
    [
        (HEAD, "Mitigation"),
        (BODY, "Five leakage tests, including the blunt one that caught the bug: insert a "
               "payment strictly after t and assert that no feature value changes."),
        (BODY, "scale_pos_weight instead of SMOTEENN, PR-AUC as the headline metric, and "
               "accuracy not reported at all."),
        (BODY, "Chronological splits with 9-week purge gaps, threshold frozen on validation, "
               "test split scored exactly once."),
        (BODY, "A four-model ladder (A–D) plus a merchant-grouped bootstrap, so a small "
               "gain is published with its confidence interval rather than as a headline."),
        (BODY, "Duplicates stopped at the database: a unique (merchant_id, idempotency_key) "
               "constraint is the authority, with Redis as coordination only."),
    ],
)

# ======================= SLIDE 6 — results & applications ================ #
s6 = _shapes_by_id(slides[5])

box(s6[11], top=0.92, height=0.76)
fill(
    s6[11],
    [
        (HEAD, "Project Output"),
        (BODY, "Model D, test period scored once (14,997 snapshots): PR-AUC 0.289 · "
               "F1 0.346 · ROC-AUC 0.895 · precision 0.272 · recall 0.475  —  "
               "recency-only baseline 0.240 / 0.315 · positive-rate floor 0.040."),
        ],
    body_pt=12,
    bullets=False,
)
for p in s6[11].text_frame.paragraphs[1:]:
    p.alignment = 2

ROW1, ROW2, IMG_H, CAP_H = 1.74, 3.86, 1.90, 0.18
LEFT_C, RIGHT_C = 3.63, 9.72
place(slides[5], "fig_pr_curves.png", (LEFT_C - 2.8, ROW1, 5.6, IMG_H))
place(slides[5], "fig_shap_beeswarm.png", (RIGHT_C - 2.8, ROW1, 5.6, IMG_H))
caption(slides[5], "Precision–recall curves for Models A–D with their frozen "
                   "operating points", (LEFT_C - 2.9, ROW1 + IMG_H, 5.8, CAP_H), size=9)
caption(slides[5], "SHAP summary for Model D — tx_count_30d outranks recency_days",
        (RIGHT_C - 2.9, ROW1 + IMG_H, 5.8, CAP_H), size=9)

place(slides[5], "fig_confusion_matrix.png", (LEFT_C - 2.8, ROW2, 5.6, IMG_H))
place(slides[5], "fig_churn_risk_json.png", (RIGHT_C - 2.8, ROW2, 5.6, IMG_H), fig_dir=SHOT)
caption(slides[5], "Confusion matrix at the frozen threshold 0.84 "
                   "(288 TP / 770 FP / 318 FN / 13,621 TN)",
        (LEFT_C - 2.9, ROW2 + IMG_H, 5.8, CAP_H), size=9)
caption(slides[5], "GET /merchants/{id}/churn-risk — score, risk band and top SHAP factors",
        (RIGHT_C - 2.9, ROW2 + IMG_H, 5.8, CAP_H), size=9)

box(s6[7], top=5.99, height=0.96)
fill(
    s6[7],
    [
        (HEAD, "Applications"),
        (BODY, "Retention targeting — rank merchants weekly and route the HIGH band to "
               "account managers with the contributing factors already attached."),
        (BODY, "Churn-cause diagnostics (failure-driven vs. engagement-driven decline) · "
               "revenue-at-risk forecasting · onboarding-cohort health monitoring · "
               "targeted pricing and incentive experiments · support triage for merchants "
               "whose payment-failure rate is rising."),
    ],
    body_pt=12,
)

# ======================= SLIDE 7 — conclusion, limits, future ============ #
s7 = _shapes_by_id(slides[6])

box(s7[11], height=2.05)
fill(
    s7[11],
    [
        (HEAD, "Conclusion"),
        (BODY, "We reformulated merchant churn from a static flag into 116,464 "
               "forward-looking merchant × weekly snapshot observations, each summarising "
               "a 90-day window and labelled by whether the merchant makes zero payment "
               "attempts in the following 60 days."),
        (BODY, "An XGBoost classifier over 12 leakage-safe RFM and payment-reliability "
               "features, trained with scale_pos_weight 23.36 on chronological splits with "
               "9-week purge gaps, reached 0.289 PR-AUC and 0.346 F1 on a test period scored "
               "once — against 0.240 and 0.315 for a recency-only rule and a 0.040 floor."),
        (BODY, "SHAP ranks tx_count_30d above recency_days and supplies the per-merchant "
               "factors returned by the churn-risk endpoint, so every score arrives with its reasons."),
        (BODY, "The most useful outcome was not a score: it was the recency leak the tests "
               "caught — a defect that would have improved every metric in this report and "
               "been invisible in all of them."),
    ],
)

box(s7[7], top=3.35, height=2.70)
fill(
    s7[7],
    [
        (HEAD, "Limitations"),
        (BODY, "Synthetic data. The generator was written to be difficult, but we wrote it: "
               "the result is evidence about the method, not about real merchants."),
        (BODY, "A single generator seed — no confidence interval should be inferred for "
               "differences of a point or two of PR-AUC."),
        (BODY, "The +0.014 PR-AUC from reliability features is statistically unresolved "
               "(bootstrap CI [−0.002, +0.031])."),
        (BODY, "Uncalibrated: a churn_score of 0.84 is a rank, not an 84% probability; no "
               "reliability curve was fitted and the reweighting distorts the output by design."),
        (BODY, "Precision 0.272 — a retention list of 1,058 merchants contains 288 real "
               "leavers; cost-sensitive thresholding is untouched."),
    ],
)

box(s7[5], top=3.35, height=2.70)
fill(
    s7[5],
    [
        (HEAD, "Future Scope"),
        (BODY, "Survival analysis in place of a fixed 60-day flag — estimate time-to-churn "
               "and compare 30, 60 and 90-day horizons directly."),
        (BODY, "Repeat across many generator seeds and report confidence intervals, so small "
               "PR-AUC differences can be quoted responsibly."),
        (BODY, "Calibrate with isotonic or Platt scaling so churn_score becomes a probability "
               "and the threshold can be chosen on cost."),
        (BODY, "Reproduce the base paper’s SMOTEENN resampling and GA-tuned XGBoost on our "
               "chronological splits, for a like-for-like comparison."),
        (BODY, "Validate on real merchant transaction data; stream events through Kafka for "
               "incremental features and online retraining under drift."),
    ],
)

# ======================= SLIDE 8 — thank you ============================= #
s8 = _shapes_by_id(slides[7])
box(s8[15], left=3.17, width=7.00)
fill(
    s8[15],
    [
        (BODY, "PRANAV KUMAR GATTUPALLI, MONIKA P D"),
        (BODY, "Dept. of Computer Science and Engineering"),
    ],
    body_pt=18,
    bullets=False,
)
for p in s8[15].text_frame.paragraphs:
    p.alignment = 2

# the two link cards are groups; fill their inner text boxes
for sh in slides[7].shapes:
    if sh.shape_type == 6:  # GROUP
        for sub in sh.shapes:
            if not sub.has_text_frame:
                continue
            head = sub.text_frame.paragraphs[0].text
            if head.startswith("GitHub"):
                fill(sub, [(HEAD, "GitHub Repository Link"),
                           (BODY, "github.com/prxnav007/Vaultlock-API")],
                     head_pt=16, body_pt=12, bullets=False)
            elif head.startswith("Project Video"):
                fill(sub, [(HEAD, "Project Video Link"),
                           (BODY, "<paste the demo video link here>")],
                     head_pt=16, body_pt=12, bullets=False)

prs.save(str(OUTPUT))
print(f"wrote {OUTPUT}")
