#!/usr/bin/env python
"""Render the report's schematic figures.

These four describe the design rather than any measured result, so they are
drawn from README.md and PROJECT_SPEC.md and will not need replacing when the
pipeline runs. The one draft number that appears is the 17-of-20 duplicate-row
count in Figure 4.4, which must track Table 6.4.

    4.1  Target system architecture
    4.2  Idempotent POST /payments request flow
    4.3  Temporal formulation on one merchant timeline
    4.4  Twenty HTTP requests resolving to one ML event
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Polygon

ROOT = Path(__file__).resolve().parent

EDGE = "#2f3b52"
INK = "#16202e"
MUTED = "#4a5568"
FAINT = "#6b7280"
INFRA = "#eef2f8"
STORE = "#e8f1ea"
ML = "#fdf1e3"
CLIENT = "#f1eef7"
STOP = "#fbeaea"
STOP_EDGE = "#9b4a4a"
FS, FSS = 9.6, 8.0


# --------------------------------------------------------------------------
# shared primitives
# --------------------------------------------------------------------------
def canvas(w, h, xmax=100, ymax=100):
    fig, ax = plt.subplots(figsize=(w, h), dpi=200)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    ax.set_xlim(0, xmax)
    ax.set_ylim(0, ymax)
    ax.axis("off")
    return fig, ax


def box(ax, cx, cy, w, h, label, sub=None, fc=INFRA, ec=EDGE, fs=FS, fss=FSS):
    ax.add_patch(FancyBboxPatch(
        (cx - w / 2, cy - h / 2), w, h,
        boxstyle="round,pad=0.35,rounding_size=1.2",
        linewidth=1.25, edgecolor=ec, facecolor=fc, zorder=2))
    if sub:
        ax.text(cx, cy + h * 0.19, label, ha="center", va="center", fontsize=fs,
                fontweight="bold", color=INK, zorder=3, linespacing=1.25)
        ax.text(cx, cy - h * 0.24, sub, ha="center", va="center", fontsize=fss,
                color=MUTED, zorder=3, linespacing=1.3)
    else:
        ax.text(cx, cy, label, ha="center", va="center", fontsize=fs,
                fontweight="bold", color=INK, zorder=3, linespacing=1.25)
    return (cx, cy, w, h)


def diamond(ax, cx, cy, w, h, label, fc=INFRA):
    ax.add_patch(Polygon([(cx, cy + h / 2), (cx + w / 2, cy),
                          (cx, cy - h / 2), (cx - w / 2, cy)],
                         closed=True, linewidth=1.25, edgecolor=EDGE,
                         facecolor=fc, zorder=2))
    ax.text(cx, cy, label, ha="center", va="center", fontsize=FSS, color=INK,
            zorder=3, linespacing=1.3)
    return (cx, cy, w, h)


def arrow(ax, p0, p1, rad=0.0, style="-", lw=1.15, color=EDGE):
    ax.add_patch(FancyArrowPatch(
        p0, p1, arrowstyle="-|>", mutation_scale=11, linewidth=lw, color=color,
        zorder=1, shrinkA=0, shrinkB=0, linestyle=style,
        connectionstyle=f"arc3,rad={rad}"))


def note(ax, x, y, s, ha="center", va="center", fs=FSS, color=MUTED,
         rot=0, style="normal", weight="normal", bbox=False):
    ax.text(x, y, s, ha=ha, va=va, fontsize=fs, color=color, rotation=rot,
            style=style, fontweight=weight, zorder=4, linespacing=1.3,
            bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none") if bbox else None)


def bot(b): return (b[0], b[1] - b[3] / 2)
def top(b): return (b[0], b[1] + b[3] / 2)
def left(b): return (b[0] - b[2] / 2, b[1])
def right(b): return (b[0] + b[2] / 2, b[1])


def save(fig, name):
    out = ROOT / name
    fig.savefig(out, dpi=200, facecolor="white", bbox_inches="tight",
                pad_inches=0.12)
    plt.close(fig)
    print(f"wrote {out.relative_to(ROOT.parent)}")


# --------------------------------------------------------------------------
# 4.1  Target system architecture  (README "Target architecture")
# --------------------------------------------------------------------------
def fig_4_1():
    fig, ax = canvas(6.3, 7.4, xmax=112, ymax=132)

    client = box(ax, 40, 127, 24, 9, "Client", fc=CLIENT)
    nginx = box(ax, 40, 111, 30, 12, "Nginx", "load balancer")
    w1 = box(ax, 13, 92, 23, 12, "FastAPI #1", "stateless")
    w2 = box(ax, 40, 92, 23, 12, "FastAPI #2", "stateless")
    w3 = box(ax, 67, 92, 23, 12, "FastAPI #3", "stateless")
    redis = box(ax, 16, 70, 32, 15, "Redis", "coordination\n+ lock leases", fc=STORE)
    pg = box(ax, 62, 70, 34, 15, "PostgreSQL", "durable ledger\n+ constraints", fc=STORE)
    feat = box(ax, 62, 48, 38, 12, "Feature Generation", "merchant × snapshot", fc=ML)
    xgb = box(ax, 62, 30, 32, 10, "XGBoost Classifier", fc=ML)
    box(ax, 36, 12, 26, 10, "SHAP Analysis", fc=ML)
    capi = box(ax, 84, 12, 28, 10, "Churn-Risk API", fc=ML)

    arrow(ax, bot(client), top(nginx))
    note(ax, 42.5, 119.5, "HTTP", ha="left")
    for w in (w1, w2, w3):
        arrow(ax, bot(nginx), top(w))
    arrow(ax, (13, 86), (13, 77.5))
    arrow(ax, (35, 86), (24, 77.5))
    arrow(ax, (45, 86), (54, 77.5))
    arrow(ax, (67, 86), (67, 77.5))

    arrow(ax, right(redis), left(pg), style="--")
    note(ax, 20, 59, "coordination only — PostgreSQL is authoritative",
         fs=7.2, color=FAINT, style="italic")

    arrow(ax, bot(pg), top(feat))
    note(ax, 65, 58, "historical facts\n(logical payments)", ha="left")
    arrow(ax, bot(feat), top(xgb))
    note(ax, 65, 38.5, "90-day window,\n60-day horizon", ha="left")
    arrow(ax, (54, 25), (41, 17))
    arrow(ax, (70, 25), (79, 17))

    arrow(ax, right(capi), (105, 12))
    arrow(ax, (105, 12), (105, 92))
    arrow(ax, (105, 92), (78.5, 92))
    note(ax, 109, 52, "churn score + top factors", rot=90)

    note(ax, 2, 2,
         "Offline training path (Feature Generation → XGBoost → SHAP) runs outside "
         "the request path.",
         ha="left", fs=7.4, color=FAINT, style="italic")
    save(fig, "fig_architecture.png")


# --------------------------------------------------------------------------
# 4.2  Idempotent POST /payments flow  (README flow; PROJECT_SPEC §14)
# --------------------------------------------------------------------------
def fig_4_2():
    fig, ax = canvas(6.3, 7.8, xmax=118, ymax=142)
    X = 46                                   # main spine

    start = box(ax, X, 137, 34, 7, "POST /payments", fc=CLIENT)
    val = box(ax, X, 127, 52, 7.5, "Validate body + Idempotency-Key")
    fp = box(ax, X, 116, 56, 9, "Compute request fingerprint",
             "SHA-256(merchant_id, amount_minor, currency)")
    d1 = diamond(ax, X, 101, 52, 16,
                 "PostgreSQL: is there a record for\n(merchant_id, idempotency_key)?")
    box(ax, 98, 110, 38, 10, "Replay stored result",
        "same fingerprint, COMPLETED", fc=STORE)
    box(ax, 98, 94, 38, 10, "409 Conflict",
        "same key, different payload", fc=STOP, ec=STOP_EDGE)

    d2 = diamond(ax, X, 82, 50, 15,
                 "Redis: SET idem:{merchant}:{key}\nowner_token NX EX")
    box(ax, 98, 72, 38, 11, "Recheck DB", "lock not acquired:\nreplay it, else 409", fc=STORE)
    recheck = box(ax, X, 65, 42, 7.5, "Recheck PostgreSQL")

    txn = box(ax, X, 46, 58, 22, "BEGIN TRANSACTION",
              "verify merchant exists\nINSERT logical payment\ndetermine outcome\n"
              "INSERT idempotency record + response", fc=STORE)
    commit = box(ax, X, 28, 30, 7.5, "COMMIT")
    rel = box(ax, X, 17, 52, 7.5, "Release lock only if still owner")
    done = box(ax, X, 7, 30, 7, "201 Created", fc=CLIENT)

    arrow(ax, bot(start), top(val))
    arrow(ax, bot(val), top(fp))
    arrow(ax, bot(fp), top(d1))
    arrow(ax, (X + 26, 101), (79, 110))      # right vertex -> replay
    arrow(ax, (X + 26, 101), (79, 94))       # right vertex -> conflict

    arrow(ax, bot(d1), top(d2))
    note(ax, X + 3, 90.5, "no completed record", ha="left", fs=7.4)
    arrow(ax, (X + 25, 82), (79, 76))        # right vertex -> recheck/409
    arrow(ax, bot(d2), top(recheck))
    note(ax, X + 3, 71.5, "lock acquired", ha="left", fs=7.4)
    arrow(ax, bot(recheck), top(txn))
    note(ax, X + 3, 59.5, "still nothing committed", ha="left", fs=7.4)
    arrow(ax, bot(txn), top(commit))
    arrow(ax, bot(commit), top(rel))
    arrow(ax, bot(rel), top(done))

    note(ax, 1, 101, "DB check 1\ncheap replay\nbefore locking", ha="left",
         fs=7.4, color=FAINT, style="italic")
    note(ax, 1, 65, "DB check 2\nanother worker\nmay have won", ha="left",
         fs=7.4, color=FAINT, style="italic")

    ax.add_patch(FancyBboxPatch((79, 22), 37, 17,
                                boxstyle="round,pad=0.4,rounding_size=1.0",
                                linewidth=1.0, edgecolor=STOP_EDGE,
                                facecolor="#fdf6f6", zorder=2))
    note(ax, 97.5, 30.5,
         "UNIQUE (merchant_id,\nidempotency_key)\n\nFinal guard. On conflict:\n"
         "roll back and return the\nwinner's stored result.",
         fs=7.4, color="#7a3b3b")
    arrow(ax, (79, 30.5), (61.5, 28.5), color=STOP_EDGE, lw=1.0)

    note(ax, 1, 1, "Redis reduces duplicate work; PostgreSQL decides what is true.",
         ha="left", color=FAINT, style="italic")
    save(fig, "fig_payment_flow.png")


# --------------------------------------------------------------------------
# 4.3  Core domain schema  (PROJECT_SPEC §§8-13)
# --------------------------------------------------------------------------
def entity(ax, cx, top, w, title, fields, fc=INFRA):
    """An entity box: a title bar over rows of [badge] name ......... type."""
    rh, hh = 4.6, 7.0
    h = hh + rh * len(fields)
    bot_y = top - h
    ax.add_patch(FancyBboxPatch((cx - w / 2, bot_y), w, h,
                                boxstyle="round,pad=0.3,rounding_size=1.0",
                                linewidth=1.25, edgecolor=EDGE, facecolor="white",
                                zorder=2))
    ax.add_patch(FancyBboxPatch((cx - w / 2, top - hh), w, hh,
                                boxstyle="square,pad=0", linewidth=0,
                                facecolor=fc, zorder=3))
    ax.text(cx, top - hh / 2, title, ha="center", va="center", fontsize=8.6,
            fontweight="bold", color=INK, zorder=4)
    for i, (name, typ, badge) in enumerate(fields):
        y = top - hh - rh * (i + 0.5)
        if badge:
            ax.text(cx - w / 2 + 2, y, badge, ha="left", va="center", fontsize=6.0,
                    color=STOP_EDGE, fontweight="bold", zorder=4)
        ax.text(cx - w / 2 + 8, y, name, ha="left", va="center", fontsize=7.0,
                color=INK, zorder=4)
        ax.text(cx + w / 2 - 2, y, typ, ha="right", va="center", fontsize=6.6,
                color=FAINT, zorder=4)
    return cx, top, bot_y, w


def fig_4_3_schema():
    fig, ax = canvas(6.3, 6.2, xmax=114, ymax=112)

    entity(ax, 26, 110, 50, "merchants", [
        ("merchant_id", "UUID", "PK"),
        ("joined_at", "TIMESTAMPTZ", ""),
        ("industry", "VARCHAR  NULL", ""),
        ("created_at", "TIMESTAMPTZ", ""),
    ], fc=STORE)

    entity(ax, 26, 78, 50, "payments", [
        ("payment_id", "UUID", "PK"),
        ("merchant_id", "UUID", "FK"),
        ("amount_minor", "BIGINT", ""),
        ("currency", "VARCHAR(3)", ""),
        ("status", "PaymentStatus", ""),
        ("failure_code", "VARCHAR  NULL", ""),
        ("created_at", "TIMESTAMPTZ", ""),
        ("processed_at", "TIMESTAMPTZ  NULL", ""),
        ("updated_at", "TIMESTAMPTZ", ""),
    ], fc=INFRA)

    entity(ax, 86, 110, 52, "idempotency_records", [
        ("id", "UUID", "PK"),
        ("merchant_id", "UUID", "FK"),
        ("idempotency_key", "VARCHAR(128)", ""),
        ("request_fingerprint", "CHAR(64)", ""),
        ("state", "IdempotencyState", ""),
        ("payment_id", "UUID  NULL", "FK"),
        ("response_status_code", "INTEGER  NULL", ""),
        ("response_body", "JSONB  NULL", ""),
        ("created_at", "TIMESTAMPTZ", ""),
        ("updated_at", "TIMESTAMPTZ", ""),
    ], fc=INFRA)

    arrow(ax, (26, 84.6), (26, 78))                 # merchants 1 -- * payments
    note(ax, 28, 81.3, "1 : many", ha="left", fs=6.6)
    arrow(ax, (51, 97), (60, 97))                   # merchants 1 -- * idempotency
    note(ax, 55.5, 97, "1 : many", fs=6.2, bbox=True)
    arrow(ax, (60, 66), (51, 66))                   # idempotency 0/1 -- 1 payment
    note(ax, 55.5, 66, "0/1 : 1", fs=6.2, bbox=True)

    ax.add_patch(FancyBboxPatch((3, 9), 108, 15,
                                boxstyle="round,pad=0.4,rounding_size=1.0",
                                linewidth=1.0, edgecolor=STOP_EDGE,
                                facecolor="#fdf6f6", zorder=2))
    note(ax, 57, 19.5, "UNIQUE (merchant_id, idempotency_key)      "
                       "CHECK amount_minor > 0      INDEX (merchant_id, created_at)",
         fs=6.8, color="#7a3b3b", weight="bold")
    note(ax, 57, 13,
         "No ML feature and no churn flag is stored on any core table: features are derived "
         "from these facts,\nso the model can change without a migration.",
         fs=7.0, color="#7a3b3b", style="italic")
    save(fig, "fig_schema.png")


# --------------------------------------------------------------------------
# 4.3  Temporal formulation  (PROJECT_SPEC §§22-27)
# --------------------------------------------------------------------------
def fig_4_3():
    fig, ax = canvas(6.3, 4.4, ymax=72)
    OBS, HOR = "#dbe6f5", "#fbe6cf"
    OBS_INK, HOR_INK = "#2b4a7a", "#8a5a1f"

    x0, obs0, xt, x1 = 4, 30, 64, 94          # start, t-90d, t, t+60d
    y, h = 50, 12                             # band centre and height
    base = y - h / 2

    ax.add_patch(FancyBboxPatch((obs0, base), xt - obs0, h, boxstyle="square,pad=0",
                                linewidth=0, facecolor=OBS, zorder=1))
    ax.add_patch(FancyBboxPatch((xt, base), x1 - xt, h, boxstyle="square,pad=0",
                                linewidth=0, facecolor=HOR, zorder=1))
    ax.plot([x0, x1 + 2], [base, base], color=EDGE, linewidth=1.2, zorder=3)

    attempts = [7, 11, 15, 19, 23, 27, 32, 36, 40, 44, 48, 52, 57, 61]
    fails = {36, 52, 61}
    for a_ in attempts:
        ax.plot([a_, a_], [base, base + 3.6], color=EDGE, linewidth=1.3, zorder=4)
        if a_ in fails:
            ax.plot(a_, base + 4.8, marker="x", markersize=3.4, color=STOP_EDGE,
                    markeredgewidth=1.1, zorder=4)

    ax.plot([xt, xt], [base - 1.5, y + h / 2 + 4], color=EDGE, linewidth=1.6, zorder=5)
    note(ax, xt, 61.5, "snapshot t", fs=FS, weight="bold", color=INK)
    note(ax, (obs0 + xt) / 2, 58, "90-day observation window", color=MUTED)
    note(ax, (xt + x1) / 2, 58, "60-day prediction horizon", color=MUTED)
    note(ax, (xt + x1) / 2, 52.5, "zero payment attempts", color=HOR_INK, style="italic")
    note(ax, (xt + x1) / 2, 47.5, "→  churn_next_60d = 1", color=HOR_INK, weight="bold")
    note(ax, (obs0 + xt) / 2, 40, "features: created_at ≤ t",
         fs=7.4, color=OBS_INK, weight="bold")
    note(ax, (xt + x1) / 2, 40, "label only — never a feature",
         fs=7.4, color=HOR_INK, weight="bold")
    note(ax, x0, 34, "│ payment attempt        ✕ FAILED (still counts as activity)",
         ha="left", fs=7.2, color=FAINT)

    # the same construction repeats every 7 days
    note(ax, x0, 27, "Weekly cadence — one row per merchant per snapshot:",
         ha="left", color=MUTED)
    mo, mh = 34, 22                            # compressed window / horizon widths
    for i, lbl in enumerate(("t", "t + 7 d", "t + 14 d")):
        yy, sx = 20 - i * 5.5, 26 + i * 6.0
        ax.add_patch(FancyBboxPatch((sx, yy - 1.7), mo, 3.4, boxstyle="square,pad=0",
                                    linewidth=0, facecolor=OBS, zorder=1))
        ax.add_patch(FancyBboxPatch((sx + mo, yy - 1.7), mh, 3.4, boxstyle="square,pad=0",
                                    linewidth=0, facecolor=HOR, zorder=1))
        ax.plot([sx + mo, sx + mo], [yy - 2.8, yy + 2.8], color=EDGE,
                linewidth=1.2, zorder=3)
        note(ax, sx - 2, yy, lbl, ha="right", fs=7.4, color=MUTED)

    note(ax, x0, 2,
         "Eligible only if tenure ≥ 90 d, a full 60 d of data follows t, and the merchant "
         "attempted ≥ 1 payment in the prior 60 d.",
         ha="left", fs=7.2, color=FAINT, style="italic")
    save(fig, "fig_temporal.png")


# --------------------------------------------------------------------------
# 4.4  Twenty requests → one ML event  (README; draft 17/20 tracks Table 6.4)
# --------------------------------------------------------------------------
def fig_4_4():
    fig, ax = canvas(6.3, 4.3, ymax=72)
    BAD, GOOD = "#fbeaea", "#e8f1ea"
    BAD_E, GOOD_E = "#9b4a4a", "#3f6b4f"
    L, R, W = 25, 75, 46

    note(ax, L, 69, "Without idempotency", fs=FS, weight="bold", color=INK)
    note(ax, R, 69, "With idempotency  (vault-api)", fs=FS, weight="bold", color=INK)

    for cx in (L, R):
        box(ax, cx, 59, W, 10, "20 duplicate HTTP requests",
            "same merchant, body and key", fc=INFRA)
        for i in range(20):
            x = cx - 20 + i * 2.1
            ax.plot([x, x], [53.0, 50.5], color=EDGE, linewidth=1.0, zorder=3)
        arrow(ax, (cx, 38), (cx, 32))
        arrow(ax, (cx, 22), (cx, 16))

    box(ax, L, 44, W, 11, "3 stateless FastAPI workers", "no shared state", fc=INFRA)
    box(ax, R, 44, W, 12, "3 workers + Redis lock",
        "PostgreSQL UNIQUE\n(merchant_id, idempotency_key)", fc=GOOD)

    box(ax, L, 27, W, 10, "17 payment rows", "one logical payment, 17 times",
        fc=BAD, ec=BAD_E)
    box(ax, R, 27, W, 10, "1 payment row", "one logical payment, once",
        fc=GOOD, ec=GOOD_E)
    box(ax, L, 11, W, 10, "17 behavioural events", "tx_count_30d inflated 17×",
        fc=BAD, ec=BAD_E)
    box(ax, R, 11, W, 10, "1 behavioural event", "tx_count_30d correct",
        fc=GOOD, ec=GOOD_E)

    note(ax, 1, 1.5,
         "A retry is not a new business event. Idempotency protects the payment and the "
         "behavioural data with one mechanism.",
         ha="left", fs=7.2, color=FAINT, style="italic")
    save(fig, "fig_one_event.png")


if __name__ == "__main__":
    fig_4_1()
    fig_4_2()
    fig_4_3_schema()
    fig_4_3()
    fig_4_4()
