"""Render Figure 4.1 — vault-api target architecture (README 'Target architecture')."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

fig, ax = plt.subplots(figsize=(10.4, 8.4), dpi=200)
fig.patch.set_facecolor("white")
ax.set_facecolor("white")
ax.set_xlim(0, 100)
ax.set_ylim(0, 100)
ax.axis("off")

FS, FSS = 9.6, 8.0
EDGE = "#2f3b52"
INFRA, STORE, ML, CLIENT = "#eef2f8", "#e8f1ea", "#fdf1e3", "#f1eef7"


def box(cx, cy, w, h, label, sub=None, fc=INFRA):
    ax.add_patch(FancyBboxPatch(
        (cx - w / 2, cy - h / 2), w, h,
        boxstyle="round,pad=0.35,rounding_size=1.2",
        linewidth=1.25, edgecolor=EDGE, facecolor=fc, zorder=2))
    if sub:
        ax.text(cx, cy + h * 0.18, label, ha="center", va="center",
                fontsize=FS, fontweight="bold", color="#16202e", zorder=3)
        ax.text(cx, cy - h * 0.25, sub, ha="center", va="center",
                fontsize=FSS, color="#4a5568", zorder=3, linespacing=1.3)
    else:
        ax.text(cx, cy, label, ha="center", va="center", fontsize=FS,
                fontweight="bold", color="#16202e", zorder=3)
    return (cx, cy, w, h)


def arrow(p0, p1, rad=0.0, style="-", double=False):
    ax.add_patch(FancyArrowPatch(
        p0, p1, arrowstyle="<|-|>" if double else "-|>", mutation_scale=11,
        linewidth=1.15, color=EDGE, zorder=1, shrinkA=0, shrinkB=0,
        linestyle=style, connectionstyle=f"arc3,rad={rad}"))


def note(x, y, s, ha="center", rot=0):
    ax.text(x, y, s, ha=ha, va="center", fontsize=FSS, color="#3d4a5c",
            zorder=4, rotation=rot, linespacing=1.3)


def bot(b): return (b[0], b[1] - b[3] / 2)
def top(b): return (b[0], b[1] + b[3] / 2)


client = box(42, 95, 22, 7, "Client", fc=CLIENT)
nginx = box(42, 83, 26, 8, "Nginx", "load balancer")
w1 = box(14, 68.5, 20, 8.5, "FastAPI #1", "stateless")
w2 = box(42, 68.5, 20, 8.5, "FastAPI #2", "stateless")
w3 = box(70, 68.5, 20, 8.5, "FastAPI #3", "stateless")
redis = box(17, 50, 30, 10, "Redis", "coordination\n+ lock leases", fc=STORE)
pg = box(63, 50, 32, 10, "PostgreSQL", "durable ledger\n+ constraints", fc=STORE)
feat = box(63, 33, 36, 9, "Feature Generation", "merchant × snapshot", fc=ML)
xgb = box(63, 20, 30, 7.5, "XGBoost Classifier", fc=ML)
shap = box(40, 7, 24, 7.5, "SHAP Analysis", fc=ML)
capi = box(84, 7, 26, 7.5, "Churn-Risk API", fc=ML)

arrow(bot(client), top(nginx))
note(46.5, 89, "HTTP", ha="left")
for w in (w1, w2, w3):
    arrow(bot(nginx), top(w))

# workers -> stores
arrow((14, 64.25), (14, 55))
arrow((38, 64.25), (24, 55))
arrow((46, 64.25), (56, 55))
arrow((70, 64.25), (70, 55))
note(10.5, 59.5, "acquire /\nrelease lock", ha="right")
note(73.5, 59.5, "atomic commit:\npayment + idempotency", ha="left")

# redis <-> postgres relationship
arrow((32, 50), (47, 50), style="--")
note(39.5, 54.0, "coordination\nonly")

arrow(bot(pg), top(feat))
note(65.5, 40.5, "historical facts (logical payments)", ha="left")
arrow(bot(feat), top(xgb))
note(65.5, 25, "90-day window, 60-day horizon", ha="left")
arrow((56, 16.25), (44, 10.75))
arrow((70, 16.25), (80, 10.75))

# churn-risk API served back through the workers
arrow((97, 10.75), (97, 64.25), rad=0.0)
ax.plot([97, 97], [10.75, 10.75], color=EDGE)
arrow((84, 10.75), (97, 10.75))
arrow((97, 64.25), (80, 68.5))
note(99.0, 38, "churn score + top factors", rot=90)

note(2, 1.5, "Offline training path (Feature Generation → XGBoost → SHAP) runs outside the request path.",
     ha="left")
ax.texts[-1].set_style("italic")
ax.texts[-1].set_color("#6b7280")

fig.savefig("report/fig_4_1_architecture.png", dpi=200,
            facecolor="white", bbox_inches="tight", pad_inches=0.12)
print("wrote report/fig_4_1_architecture.png")
