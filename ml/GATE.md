# Feasibility gate

Written **before** the first model comparison was run, so the criteria cannot be
chosen to fit a result.

The purpose of the gate is to answer one question before any effort goes into
tuning: *is this prediction problem real?* A synthetic generator that makes the
answer obvious would produce excellent-looking metrics that mean nothing.

## Criteria

The project continues past Milestone 5 only if all of these hold on the
chronological test split:

| # | Criterion | Rationale |
|---|---|---|
| 1 | Model A (majority) PR-AUC equals the test positive rate | Sanity check on the evaluation code itself; the floor must be the base rate by definition |
| 2 | **Recency-only baseline PR-AUC is NOT within 0.05 of Model D** | If a single feature matches the full model, the world is a recency lookup and the project claim is empty |
| 3 | **No model has test PR-AUC > 0.95** | Near-perfect separation on synthetic data means leakage or a trivial generator, not a good model |
| 4 | Model D >= Model C | Reliability features should add information, or the research question is answered negatively — which is a valid result, but must be reported as such |
| 5 | Snapshot-level positive rate is in 2%–10% | Below 2% the test split holds too few positives for a stable estimate; above 10% the world is churning implausibly fast |
| 6 | The six leakage proofs in `tests/unit/test_feature_definitions.py` pass | Non-negotiable; a leak invalidates every number downstream |

If criterion 2 or 3 fails, the response is to **inspect the generator and the
feature definitions**, never to add model complexity or swap algorithms.

## Rules

- **Never compare against, or tune toward, the draft numbers in the report.**
  Those were invented placeholders written to be internally consistent. Any
  resemblance between a measured result and a draft value is a coincidence and
  must not be pursued. The report gets rewritten to match the measurements, not
  the other way round.
- The test split is scored **once**, after the threshold is frozen on
  validation.
- Every change to the generator made after the gate is first evaluated must be
  logged below, with its reason.

## Verdict — criterion 2 narrowly FAILED; the result stands as measured

Test-split results, scored once after the threshold was frozen on validation:

| Model | PR-AUC | F1 | Precision | Recall | ROC-AUC |
|---|---|---|---|---|---|
| A — majority | 0.040 | 0.000 | — | 0.000 | — |
| B — recency only | 0.240 | 0.315 | 0.245 | 0.442 | 0.851 |
| C — RFM + tenure | 0.275 | 0.333 | 0.250 | 0.500 | 0.892 |
| D — RFM + failure | 0.289 | 0.346 | 0.272 | 0.475 | 0.895 |

Merchant-grouped bootstrap, 2,000 resamples over the 1,725 test merchants
(resampling merchants, not rows: one merchant contributes up to nine correlated
weekly snapshots, and row resampling would count near-copies as independent
observations). Differences are resampled on the same merchant draw, so each
interval is for the paired difference:

| Quantity | Estimate | 95% CI |
|---|---|---|
| PR-AUC B | 0.240 | [0.191, 0.294] |
| PR-AUC C | 0.275 | [0.214, 0.338] |
| PR-AUC D | 0.289 | [0.227, 0.353] |
| **D − B** | **+0.048** | **[−0.001, +0.097]** |
| **D − C** | **+0.014** | **[−0.002, +0.031]** |

| # | Criterion | Outcome |
|---|---|---|
| 1 | A's PR-AUC equals the test positive rate | **Pass** — 0.040 vs 4.04% |
| 2 | Recency baseline not within 0.05 of Model D | **FAIL** — D − B = +0.048, just under the 0.05 bar |
| 3 | No model above 0.95 PR-AUC | **Pass** — highest is 0.289 |
| 4 | D ≥ C | **Pass** — +0.014, though the interval includes zero |
| 5 | Positive rate in 2–10% | **Pass** — 4.04% on test |
| 6 | Leakage proofs pass | **Pass** — all six |

**Criterion 2 is recorded as failed and criterion 2 is not reinterpreted.** The
bar was set in absolute PR-AUC before the achievable range was known, and it
turned out to demand that trajectory and reliability features add 17% of the
entire usable scale. A relative reading (D is 20% better than B) would pass
comfortably — but changing the measure after seeing the number is how a gate
stops being a gate, so the absolute reading is the one reported.

The generator was **not** revised again in response to this result.

**What the report must say.** The honest statement is that the criterion
narrowly failed and that neither improvement is statistically distinguishable
from zero at 95% confidence: both paired intervals include zero, if only just
(upper bounds +0.097 and +0.031, lower bounds −0.001 and −0.002). Trajectory and
reliability features give a consistently positive but small and
statistically unresolved improvement over recency alone on this synthetic
population. The report must not claim that payment-reliability features
"improve" prediction without that qualification, and must not present +0.048 as
an established effect.

Worth stating alongside it: SHAP ranks `tx_count_30d` **above** `recency_days`
by mean absolute contribution, so the model is not merely re-deriving recency
even though the aggregate gain over a recency rule is small.

## Generator change log

Changes made **before** the first model comparison are calibration of the
world, not tuning toward a result. They are logged here all the same.

### 2026-10-05 — pre-gate: give disengaging merchants an actual departure

**Observed:** the first full build produced a snapshot-level positive rate of
**1.48%** (1,844 positives in 124,722 rows), failing criterion 5.

**Cause:** the label asks whether a merchant makes zero attempts in the next 60
days, while eligibility requires at least one attempt in the previous 60 days.
A merchant only produces a positive row inside the narrow band between those
two conditions. Gradual churners decayed as `exp(-elapsed / halflife)`, which
approaches zero but never reaches it: with a base rate near 0.6/day, even three
half-lives leaves roughly one attempt per fortnight, so they stayed "active"
and never produced a positive. Stragglers kept a 3% residual rate, which was
usually enough to land an attempt inside any 60-day window. Only the abrupt
churners (89 of 295) were generating positives at all.

**Change:** every churn mode now has a `departure_day` after which the rate is
exactly zero — abrupt at `churn_start`, gradual at `churn_start + 3 x halflife`
(so the decline is still visible for 3 half-lives before silence), straggler
after a further 120–240 days of sparse activity. Real churn is eventually
absolute rather than asymptotic, so this makes the world more realistic, not
merely more convenient.

**Not changed:** `churn_fraction` stays at the spec's 0.15, and no feature
definition was touched. No model had been fit at this point, so no measured
metric informed the change.

**Result:** adding a departure alone moved the rate only from 1.48% to 1.52%.
The remaining cause was timing: `churn_start` was drawn uniformly across almost
the whole window, so a merchant's final attempt often fell within 120 days of
the end of history and its positive band was truncated or lost entirely. The
departure date is now sampled first, bounded to `[180, n_days - 130]`, and the
decline worked backwards from it, which guarantees the band is observable.

Final: **121,095 eligible rows, 2,699 positives, 2.23%** — criterion 5 met. The
rate was not pushed any higher; 2.23% is what this world produces at the spec's
15% merchant-level churn, and it is reported as measured. Note this is well
below the 3.90% the report currently drafts, so that figure and everything
derived from it needs rewriting, not reconciling.
