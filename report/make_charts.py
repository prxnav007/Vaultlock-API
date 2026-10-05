#!/usr/bin/env python
"""Render Chapter 6's result charts from the measured artifacts.

Every value here is read from `artifacts/`, which is produced by
`scripts/run_pipeline.py`. Nothing is hardcoded and nothing is synthesised:

  6.1  class balance per split    <- metrics.json (label_balance)
  6.2  PR curves A-D              <- predictions_test.parquet (per-row scores)
  6.3  confusion matrix, Model D  <- metrics.json (model D at the frozen threshold)
  6.4  SHAP beeswarm              <- shap_test.npz (per-row SHAP over the test split)
  6.5  SHAP waterfall             <- exemplars.json (the pinned high-risk merchant)

An earlier version of this file drew the same five charts from draft constants
copied out of build_report.py, inventing the curve shape for 6.2 and the entire
point cloud for 6.4 and 6.5. If an artifact is missing the chart now fails
loudly rather than falling back to numbers nobody measured.

The visual language -- palette, helpers, footnotes -- is unchanged.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

ROOT = Path(__file__).resolve().parent
ARTIFACTS = ROOT.parent / "artifacts"
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

MODEL_STYLE = {
    "A": ("A — Majority", C_A, (0, (1, 1.6))),
    "B": ("B — Recency-only", C_B, (0, (5, 2))),
    "C": ("C — RFM + tenure", C_C, (0, (7, 1.6, 1.6, 1.6))),
    "D": ("D — RFM + failure", C_D, "solid"),
}


def load(name: str):
    path = ARTIFACTS / name
    if not path.exists():
        raise SystemExit(
            f"missing artifact {path}. Run scripts/run_pipeline.py first -- these "
            "charts are no longer allowed to fall back to draft numbers."
        )
    if path.suffix == ".json":
        return json.loads(path.read_text())
    return path


METRICS = load("metrics.json")
METADATA = load("model_metadata.json")
THRESHOLD = float(METADATA["classification_threshold"])
CM = METRICS["test"]["D"]["confusion_matrix"]
BASE_RATE = METRICS["test"]["D"]["n_positives"] / METRICS["test"]["D"]["n_rows"]

SPLITS = {
    label: (entry["rows"], entry["positives"])
    for label, key in (("Train", "train"), ("Validation", "validation"), ("Test", "test"))
    for entry in [METRICS["label_balance"]["splits"][key]]
}


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
    top = max(neg) * 60
    ax.set_ylim(100, top)
    ax.set_xticks(x, names)
    ax.set_ylabel("Snapshots (log scale)")
    tidy(ax)

    for xi, (n, p) in zip(x, zip(neg, pos)):
        ax.text(xi - w / 2, n * 1.18, f"{n:,}", ha="center", fontsize=7.4, color=MUTED)
        ax.text(xi + w / 2, p * 1.18, f"{p:,}", ha="center", fontsize=7.4, color=MUTED)
        ax.text(xi, top / 8, f"{p / (n + p) * 100:.2f}% positive", ha="center",
                fontsize=8, color=INK, fontweight="bold")

    ratio = sum(neg) / sum(pos)
    ax.legend(frameon=False, loc="lower center", bbox_to_anchor=(0.5, 1.0),
              fontsize=7.6, ncol=2)
    footnote(fig, f"A log scale is used because the classes differ by a factor of "
                  f"~{ratio:.0f}; the positive rate is printed above each split.")
    save(fig, "fig_class_balance.png")


# --------------------------------------------------------------------------
# 6.2  Precision-recall curves, computed from the saved test-split scores
# --------------------------------------------------------------------------
def fig_6_2():
    import pandas as pd
    from sklearn.metrics import average_precision_score, precision_recall_curve

    predictions = pd.read_parquet(load("predictions_test.parquet"))
    y = predictions["y_true"].to_numpy()

    fig, ax = plt.subplots(figsize=(6.3, 3.9), dpi=200)
    for key, (label, colour, style) in MODEL_STYLE.items():
        scores = predictions[f"score_{key.lower()}"].to_numpy()
        ap = average_precision_score(y, scores)
        if np.ptp(scores) == 0:
            # The majority model emits one constant score, so it has no curve:
            # its precision is the positive rate at every recall.
            ax.plot([0, 1], [BASE_RATE, BASE_RATE], color=colour, linewidth=1.6,
                    linestyle=style, zorder=3, label=f"{label}  (PR-AUC {ap:.3f})")
            continue
        precision, recall, _ = precision_recall_curve(y, scores)
        ax.plot(recall, precision, color=colour, linewidth=1.8, linestyle=style,
                zorder=3, label=f"{label}  (PR-AUC {ap:.2f})")

        row = METRICS["test"][key]
        ax.plot(row["recall"], row["precision"], marker="o", markersize=5,
                color=colour, markeredgecolor="white", markeredgewidth=1.0, zorder=5)

    ax.axhline(BASE_RATE, color=C_A, linewidth=1.0, linestyle=(0, (2, 2)), zorder=2)
    ax.text(0.985, BASE_RATE + 0.022, f"positive-rate baseline = {BASE_RATE:.3f}",
            ha="right", fontsize=7.2, color=MUTED)

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1.02)
    ax.set_xlabel("Recall")
    ax.set_ylabel("Precision")
    tidy(ax, grid_axis="both")
    ax.legend(frameon=False, loc="upper right", fontsize=7.6)
    footnote(fig, "Curves are computed from the saved per-snapshot test scores. "
                  "Filled markers are each model's frozen operating point "
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
                  f"threshold {THRESHOLD:.2f}. "
                  f"Precision {CM['tp'] / (CM['tp'] + CM['fp']):.2f}, "
                  f"recall {CM['tp'] / (CM['tp'] + CM['fn']):.2f}.")
    save(fig, "fig_confusion_matrix.png")


# --------------------------------------------------------------------------
# 6.4  SHAP beeswarm, one point per test snapshot
# --------------------------------------------------------------------------
def fig_6_4():
    bundle = np.load(load("shap_test.npz"), allow_pickle=True)
    values = bundle["values"]
    data = bundle["data"]
    names = [str(n) for n in bundle["feature_names"]]
    index = bundle["subsample_index"]

    order = np.argsort(np.abs(values).mean(axis=0))[::-1]
    fig, ax = plt.subplots(figsize=(6.3, 4.2), dpi=200)
    cmap = LinearSegmentedColormap.from_list("fv", ["#3f72a8", "#cbd3de", "#c0803a"])
    rng = np.random.default_rng(SEED)

    for row, feature in enumerate(order):
        y = len(order) - 1 - row
        shap = values[index, feature]
        raw = data[index, feature].astype(float)
        # Percentile-normalise so colour reads consistently whatever the units.
        finite = np.isfinite(raw)
        colour = np.full(raw.shape, 0.5)
        if finite.sum() > 1:
            ranks = raw[finite].argsort().argsort() / max(finite.sum() - 1, 1)
            colour[finite] = ranks
        jitter = rng.normal(0, 0.11, shap.size)
        ax.scatter(shap, y + jitter, c=colour, cmap=cmap, s=4.2, alpha=0.62,
                   linewidths=0, zorder=3)

    ax.axvline(0, color="#9aa4b4", linewidth=0.9, zorder=2)
    ax.set_yticks(range(len(order)), [names[i] for i in order][::-1], fontsize=7.6)
    ax.set_xlabel("SHAP value  (impact on model output — right = pushes risk up)")
    span = float(np.abs(values[index]).max()) * 1.08
    ax.set_xlim(-span, span)
    ax.set_ylim(-0.7, len(order) - 0.3)
    tidy(ax, grid_axis="x")
    ax.tick_params(axis="y", length=0)

    sm = plt.cm.ScalarMappable(cmap=cmap)
    cb = fig.colorbar(sm, ax=ax, pad=0.015, fraction=0.03, ticks=[0, 1])
    cb.ax.set_yticklabels(["low", "high"], fontsize=7.2, color=MUTED)
    cb.set_label("Feature value", fontsize=7.4, color=MUTED)
    cb.outline.set_visible(False)
    footnote(fig, f"Features ordered by mean |SHAP| over the test split; one point "
                  f"per snapshot ({len(index):,} of "
                  f"{values.shape[0]:,} subsampled for legibility). Grey points are "
                  f"snapshots where the feature is undefined.")
    save(fig, "fig_shap_beeswarm.png")


# --------------------------------------------------------------------------
# 6.5  SHAP waterfall for the pinned high-risk merchant
# --------------------------------------------------------------------------
def fig_6_5(top_n: int = 8):
    exemplar = load("exemplars.json")["high_risk"]
    base = float(exemplar["base_value"])
    features = exemplar["features"]

    ranked = sorted(features.items(), key=lambda kv: abs(kv[1]["shap"]), reverse=True)
    shown, rest = ranked[:top_n], ranked[top_n:]

    def label(name: str, entry: dict) -> str:
        value = entry["value"]
        if value is None:
            return f"{name} = n/a"
        if abs(value) >= 1000:
            return f"{name} = {value:,.0f}"
        if float(value).is_integer():
            return f"{name} = {int(value)}"
        return f"{name} = {value:.2f}"

    rows = [(label(n, e), float(e["shap"])) for n, e in shown]
    if rest:
        rows.append((f"{len(rest)} other features", sum(float(e["shap"]) for _, e in rest)))

    fig, ax = plt.subplots(figsize=(6.3, 3.6), dpi=200)
    labels = [r[0] for r in rows]
    vals = np.array([r[1] for r in rows])
    final = base + vals.sum()

    cum = base + np.concatenate([[0], np.cumsum(vals)[:-1]])
    y = np.arange(len(vals))[::-1]
    for yi, start, v in zip(y, cum, vals):
        ax.barh(yi, v, left=start, height=0.62, zorder=3,
                color=AMBER_INK if v > 0 else BLUE_INK,
                edgecolor="white", linewidth=1.0)
        pad = max(abs(vals).max() * 0.02, 0.02)
        ax.text(start + v + (pad if v > 0 else -pad), yi,
                f"{v:+.2f}", va="center", ha="left" if v > 0 else "right",
                fontsize=7.4, color=INK)

    ax.axvline(base, color="#9aa4b4", linewidth=0.9, linestyle=(0, (3, 2)), zorder=2)
    ax.text(base, len(vals) - 0.15, f"base value  E[f(x)] = {base:.2f}",
            ha="center", fontsize=7.4, color=MUTED)
    ax.axvline(final, color=AMBER_INK, linewidth=1.1, zorder=2)
    score = 1 / (1 + np.exp(-final))
    ax.text(final, -0.9, f"f(x) = {final:.2f}   →   churn_score {score:.2f}",
            ha="center", fontsize=8, color=AMBER_INK, fontweight="bold")

    lo = min(base, cum.min(), final) - abs(vals).max() * 0.9
    hi = max(base, (cum + vals).max(), final) + abs(vals).max() * 0.9
    ax.set_yticks(y, labels, fontsize=7.6)
    ax.set_xlabel("Model output (log-odds)")
    ax.set_xlim(lo, hi)
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
    print("\nall five charts rendered from measured artifacts", file=sys.stderr)
