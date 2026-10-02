#!/usr/bin/env python
"""Render Chapter 6's result charts from the report's draft numbers.

NOTHING HERE IS MEASURED. Every value comes from the draft figures in
build_report.py (Tables 6.1-6.3) and must be regenerated from real artifacts
before the final review. The charts fall into two groups:

  Fully determined by the draft numbers — drawing them invents nothing beyond
  what the tables already assert:
      6.1  class balance per split       (per-split row and positive counts)
      6.3  confusion matrix, Model D     (539 / 359 / 290 / 19,993)

  Shape is invented — only a summary statistic is known, so the curve or the
  point cloud is synthesised to be consistent with it:
      6.2  PR curves A-D    only the four PR-AUC scalars and the operating
                            points are fixed; the curve between them is a fit
      6.4  SHAP beeswarm    only the global ranking is fixed; the per-row SHAP
                            values are generated
      6.5  SHAP waterfall   only the ranking is fixed; the contributions are
                            chosen to sum to a score of 0.81

Regenerate all of them from artifacts/metrics.json, artifacts/shap_*.npy and
the test-split predictions once the pipeline runs.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap

ROOT = Path(__file__).resolve().parent
SEED = 42

INK = "#16202e"
MUTED = "#4a5568"
FAINT = "#6b7280"
GRID = "#d8dee8"
# four well-separated series, also distinguished by line style and direct labels
C_A, C_B, C_C, C_D = "#8a94a6", "#3f72a8", "#c0803a", "#2f6b4f"
BLUE, AMBER = "#dbe6f5", "#fbe6cf"
BLUE_INK, AMBER_INK = "#2b4a7a", "#8a5a1f"

plt.rcParams.update({
    "font.size": 8.0,
    "axes.edgecolor": "#9aa4b4",
    "axes.labelcolor": MUTED,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "axes.linewidth": 0.8,
})

# ---- the draft numbers these charts render -------------------------------
SPLITS = {                      # name: (rows, positives)
    "Train": (98846, 3862),
    "Validation": (21181, 816),
    "Test": (21181, 829),
}
BASE_RATE = 0.039               # test positive rate = Model A's PR-AUC
MODELS = {                      # name: (pr_auc, recall, precision, colour, style)
    "A — Majority": (0.039, None, None, C_A, (0, (1, 1.6))),
    "B — Recency-only": (0.41, 0.48, 0.44, C_B, (0, (5, 2))),
    "C — RFM + tenure": (0.58, 0.59, 0.55, C_C, (0, (7, 1.6, 1.6, 1.6))),
    "D — RFM + failure": (0.66, 0.65, 0.60, C_D, "solid"),
}
CM = {"tp": 539, "fp": 359, "fn": 290, "tn": 19993}
FEATURES = [                    # global ranking by mean |SHAP|, then the rest
    ("recency_days", 0.55, +1), ("frequency_change", 0.41, -1),
    ("tx_count_30d", 0.33, -1), ("failure_rate_change", 0.26, +1),
    ("failure_rate_30d", 0.21, +1), ("monetary_change", 0.14, -1),
    ("tx_count_90d", 0.11, -1), ("tenure_days", 0.08, -1),
    ("tx_count_prev_30d", 0.05, -1), ("failure_rate_prev_30d", 0.04, +1),
    ("avg_success_amount_30d", 0.03, -1),
    ("avg_success_amount_prev_30d", 0.02, -1),
]
WATERFALL = [                   # one high-risk merchant; sums to score 0.81
    ("recency_days = 46", +0.92), ("frequency_change = −21", +0.61),
    ("failure_rate_change = +0.18", +0.38), ("tx_count_30d = 4", +0.31),
    ("failure_rate_30d = 0.24", +0.22), ("tenure_days = 612", -0.11),
    ("monetary_change = +1,240", -0.08), ("tx_count_90d = 38", +0.05),
    ("4 other features", +0.02),
]
WATERFALL_BASE = -0.85


def save(fig, name):
    out = ROOT / name
    fig.savefig(out, dpi=200, facecolor="white", bbox_inches="tight", pad_inches=0.1)
    plt.close(fig)
    print(f"wrote {out.relative_to(ROOT.parent)}")


def tidy(ax, grid_axis="y"):
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.grid(axis=grid_axis, color=GRID, linewidth=0.7, zorder=0)
    ax.set_axisbelow(True)


def footnote(fig, text):
    fig.text(0.0, -0.01, text, ha="left", va="top", fontsize=6.8,
             color=FAINT, style="italic")


# --------------------------------------------------------------------------
# 6.1  Class balance across the chronological splits
# --------------------------------------------------------------------------
def fig_6_1():
    fig, ax = plt.subplots(figsize=(6.3, 3.1), dpi=200)
    names = list(SPLITS)
    neg = [SPLITS[n][0] - SPLITS[n][1] for n in names]
    pos = [SPLITS[n][1] for n in names]
    x = np.arange(len(names))
    w = 0.34

    ax.bar(x - w / 2, neg, w, label="Not churning", color="#c3cedd",
           edgecolor="white", linewidth=1.2, zorder=3)
    ax.bar(x + w / 2, pos, w, label="Churning", color=AMBER_INK,
           edgecolor="white", linewidth=1.2, zorder=3)

    ax.set_yscale("log")
    ax.set_ylim(100, 2_500_000)
    ax.set_xticks(x, names)
    ax.set_ylabel("Snapshots (log scale)")
    tidy(ax)

    for xi, (n, p) in zip(x, zip(neg, pos)):
        ax.text(xi - w / 2, n * 1.18, f"{n:,}", ha="center", fontsize=7.4, color=MUTED)
        ax.text(xi + w / 2, p * 1.18, f"{p:,}", ha="center", fontsize=7.4, color=MUTED)
        ax.text(xi, 350_000, f"{p / (n + p) * 100:.2f}% positive", ha="center",
                fontsize=8, color=INK, fontweight="bold")

    ax.legend(frameon=False, loc="lower center", bbox_to_anchor=(0.5, 1.0),
              fontsize=7.6, ncol=2)
    footnote(fig, "A log scale is used because the classes differ by a factor of ~25; "
                  "the positive rate is printed above each split.")
    save(fig, "fig_class_balance.png")


# --------------------------------------------------------------------------
# 6.2  Precision-recall curves  (SHAPE IS SYNTHESISED)
# --------------------------------------------------------------------------
def _fit_pr(ap, r_star, p_star, base=BASE_RATE):
    """Find p(r) = base + (1-base)(1-r^a)^b matching the PR-AUC and the operating point."""
    rs = np.linspace(0, 1, 1501)
    best = None
    for a in np.linspace(0.3, 3.0, 110):
        for b in np.linspace(0.2, 4.0, 150):
            p = base + (1 - base) * (1 - rs ** a) ** b
            err = (np.trapezoid(p, rs) - ap) ** 2 * 6.0
            err += (base + (1 - base) * (1 - r_star ** a) ** b - p_star) ** 2
            if best is None or err < best[0]:
                best = (err, a, b)
    return best[1], best[2]


def fig_6_2():
    fig, ax = plt.subplots(figsize=(6.3, 3.9), dpi=200)
    rs = np.linspace(0, 1, 1501)

    for name, (ap, r_star, p_star, colour, style) in MODELS.items():
        if r_star is None:                     # dummy: precision == positive rate
            ax.plot(rs, np.full_like(rs, BASE_RATE), color=colour, linewidth=1.6,
                    linestyle=style, zorder=3, label=f"{name}  (PR-AUC {ap:.3f})")
            continue
        a, b = _fit_pr(ap, r_star, p_star)
        ax.plot(rs, BASE_RATE + (1 - BASE_RATE) * (1 - rs ** a) ** b, color=colour,
                linewidth=1.8, linestyle=style, zorder=3,
                label=f"{name}  (PR-AUC {ap:.2f})")
        ax.plot(r_star, p_star, marker="o", markersize=5, color=colour,
                markeredgecolor="white", markeredgewidth=1.0, zorder=5)

    ax.axhline(BASE_RATE, color=C_A, linewidth=1.0, linestyle=(0, (2, 2)), zorder=2)
    ax.text(0.985, BASE_RATE + 0.022, f"positive-rate baseline = {BASE_RATE:g}",
            ha="right", fontsize=7.2, color=MUTED)

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1.02)
    ax.set_xlabel("Recall")
    ax.set_ylabel("Precision")
    tidy(ax, grid_axis="both")
    ax.legend(frameon=False, loc="upper right", fontsize=7.6)
    footnote(fig, "Filled markers are each model's frozen operating point "
                  "(threshold chosen on validation).")
    save(fig, "fig_pr_curves.png")


# --------------------------------------------------------------------------
# 6.3  Confusion matrix, Model D
# --------------------------------------------------------------------------
def fig_6_3():
    fig, ax = plt.subplots(figsize=(5.2, 3.0), dpi=200)
    m = np.array([[CM["tp"], CM["fn"]], [CM["fp"], CM["tn"]]], dtype=float)
    rownorm = m / m.sum(axis=1, keepdims=True)

    cmap = LinearSegmentedColormap.from_list("box", ["#ffffff", "#2f6b4f"])
    ax.imshow(rownorm, cmap=cmap, vmin=0, vmax=1, aspect="auto")

    for i in range(2):
        for j in range(2):
            dark = rownorm[i, j] > 0.5
            ax.text(j, i - 0.09, f"{int(m[i, j]):,}", ha="center", va="center",
                    fontsize=13, fontweight="bold",
                    color="white" if dark else INK)
            ax.text(j, i + 0.17, f"{rownorm[i, j] * 100:.1f}% of row", ha="center",
                    va="center", fontsize=7.6,
                    color="#dfe9e3" if dark else MUTED)

    ax.set_xticks([0, 1], ["Predicted\nchurn", "Predicted\nactive"])
    ax.set_yticks([0, 1], ["Actually\nchurned", "Actually\nactive"])
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    footnote(fig, f"Test split, {sum(CM.values()):,} snapshots, Model D at the frozen "
                  f"threshold 0.38. Precision {CM['tp'] / (CM['tp'] + CM['fp']):.2f}, "
                  f"recall {CM['tp'] / (CM['tp'] + CM['fn']):.2f}.")
    save(fig, "fig_confusion_matrix.png")


# --------------------------------------------------------------------------
# 6.4  SHAP beeswarm  (POINT CLOUD IS SYNTHESISED)
# --------------------------------------------------------------------------
def fig_6_4():
    rng = np.random.default_rng(SEED)
    fig, ax = plt.subplots(figsize=(6.3, 4.2), dpi=200)
    n = 420
    cmap = LinearSegmentedColormap.from_list("fv", ["#3f72a8", "#cbd3de", "#c0803a"])

    for row, (name, mean_abs, sign) in enumerate(FEATURES):
        y = len(FEATURES) - 1 - row
        value = rng.random(n)                                 # normalised feature value
        shap = sign * (value - 0.5) * mean_abs * 3.1
        shap += rng.normal(0, mean_abs * 0.42, n)             # unexplained spread
        jitter = rng.normal(0, 0.11, n)
        ax.scatter(shap, y + jitter, c=value, cmap=cmap, s=4.2, alpha=0.62,
                   linewidths=0, zorder=3)

    ax.axvline(0, color="#9aa4b4", linewidth=0.9, zorder=2)
    ax.set_yticks(range(len(FEATURES)), [f[0] for f in reversed(FEATURES)], fontsize=7.6)
    ax.set_xlabel("SHAP value  (impact on model output — right = pushes risk up)")
    ax.set_xlim(-1.5, 1.5)
    ax.set_ylim(-0.7, len(FEATURES) - 0.3)
    tidy(ax, grid_axis="x")
    ax.tick_params(axis="y", length=0)

    sm = plt.cm.ScalarMappable(cmap=cmap)
    cb = fig.colorbar(sm, ax=ax, pad=0.015, fraction=0.03, ticks=[0, 1])
    cb.ax.set_yticklabels(["low", "high"], fontsize=7.2, color=MUTED)
    cb.set_label("Feature value", fontsize=7.4, color=MUTED)
    cb.outline.set_visible(False)
    footnote(fig, "Features ordered by mean |SHAP| over the test split; one point per "
                  "snapshot (subsampled for legibility).")
    save(fig, "fig_shap_beeswarm.png")


# --------------------------------------------------------------------------
# 6.5  SHAP waterfall  (CONTRIBUTIONS ARE SYNTHESISED)
# --------------------------------------------------------------------------
def fig_6_5():
    fig, ax = plt.subplots(figsize=(6.3, 3.6), dpi=200)
    labels = [l for l, _ in WATERFALL]
    vals = np.array([v for _, v in WATERFALL])
    final = WATERFALL_BASE + vals.sum()

    cum = WATERFALL_BASE + np.concatenate([[0], np.cumsum(vals)[:-1]])
    y = np.arange(len(vals))[::-1]
    for yi, start, v in zip(y, cum, vals):
        ax.barh(yi, v, left=start, height=0.62, zorder=3,
                color=AMBER_INK if v > 0 else BLUE_INK,
                edgecolor="white", linewidth=1.0)
        ax.text(start + v + (0.035 if v > 0 else -0.035), yi,
                f"{v:+.2f}", va="center", ha="left" if v > 0 else "right",
                fontsize=7.4, color=INK)

    ax.axvline(WATERFALL_BASE, color="#9aa4b4", linewidth=0.9,
               linestyle=(0, (3, 2)), zorder=2)
    ax.text(WATERFALL_BASE, len(vals) - 0.15,
            f"base value  E[f(x)] = {WATERFALL_BASE:.2f}", ha="center",
            fontsize=7.4, color=MUTED)
    ax.axvline(final, color=AMBER_INK, linewidth=1.1, zorder=2)
    ax.text(final, -0.9, f"f(x) = {final:.2f}   →   churn_score {1 / (1 + np.exp(-final)):.2f}",
            ha="center", fontsize=8, color=AMBER_INK, fontweight="bold")

    ax.set_yticks(y, labels, fontsize=7.6)
    ax.set_xlabel("Model output (log-odds)")
    ax.set_xlim(-1.7, 2.6)
    ax.set_ylim(-1.4, len(vals) + 0.3)
    tidy(ax, grid_axis="x")
    ax.tick_params(axis="y", length=0)
    footnote(fig, "Amber pushes risk up, blue pushes it down. Same merchant as "
                  "Figures 5.2 and 5.3.")
    save(fig, "fig_shap_waterfall.png")


if __name__ == "__main__":
    fig_6_1()
    fig_6_2()
    fig_6_3()
    fig_6_4()
    fig_6_5()
