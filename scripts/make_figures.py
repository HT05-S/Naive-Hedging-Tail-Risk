"""Draw the figures used in the report.

    python scripts/make_figures.py

Needs results/hedge_ratios/ and results/tables/. Writes results/figures/*.png.
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hedging import analysis, data  # noqa: E402
from hedging.models import MODEL_LABELS, MODELS  # noqa: E402

OUT = data.RESULTS / "figures"
BLUE, ORANGE, GREY = "#2a78d6", "#eb6834", "#b9b8b2"
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"
MAIN = [("paper", "WTI", "original"), ("paper", "GBPUSD", "original"), ("paper", "SP500", "original"),
        ("paper", "GOLD", "original"), ("ours", "BTC", "full"), ("ours", "NATGAS", "full")]

plt.rcParams.update({
    "font.family": "sans-serif", "font.sans-serif": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
    "font.size": 9, "axes.edgecolor": GRID, "axes.labelcolor": MUTED, "text.color": INK,
    "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
    "axes.titlesize": 9.5, "axes.titleweight": "bold", "axes.titlelocation": "left", "figure.dpi": 200,
})


def fig_hedge_ratios():
    """Estimated hedge ratios through time, WTI, 5% CVaR downside: one panel per model."""
    d, B = analysis.aligned("paper", "WTI", "oos")
    B = B[(d["target_wed"] <= data.ORIGINAL_END).to_numpy()]
    models = [m for m in MODELS if m != "naive"]
    fig, axes = plt.subplots(len(models), 1, figsize=(6.5, 6.6), sharex=True, sharey=True)
    for ax, m in zip(axes, models):
        b = B[(m, "down", "CVaR", 0.05)]
        ax.axhline(1.0, color=INK, linewidth=0.9, linestyle=(0, (4, 3)))
        ax.plot(b.index, b.to_numpy(), color=BLUE, linewidth=1.0)
        ax.set_title(f"{MODEL_LABELS[m]}   (standard deviation {b.std():.2f})")
        ax.set_ylim(0.3, 1.9)
        ax.set_yticks([0.5, 1.0, 1.5])
        ax.grid(axis="x", visible=False)
    axes[0].annotate("naïve hedge = 1", xy=(B.index[40], 1.0), xytext=(B.index[40], 1.55), fontsize=8, color=MUTED,
                     arrowprops=dict(arrowstyle="-", color=MUTED, linewidth=0.6))
    axes[-1].set_xlabel("Week of the hedge")
    fig.supylabel("Hedge ratio", fontsize=9, color=MUTED)
    fig.tight_layout()
    fig.savefig(OUT / "fig1_hedge_ratios_wti.png", bbox_inches="tight")
    plt.close(fig)


def fig_in_vs_out(he: pd.DataFrame):
    """Scenarios (of 12) in which the naive hedge is the best model: out-of-sample against in-sample."""
    rows = []
    for st, mk, sm in MAIN:
        for mode in ("oos", "is"):
            x = he[(he.setting == st) & (he.market == mk) & (he["sample"] == sm) & (he["mode"] == mode) & (he.subset == "all")]
            t = x.pivot_table(index="model", columns=["side", "measure", "alpha"], values="he")
            rows.append(dict(market=data.LABELS[mk], mode=mode, wins=int((t.idxmax() == "naive").sum())))
    r = pd.DataFrame(rows).pivot(index="market", columns="mode", values="wins").loc[[data.LABELS[m] for _, m, _ in MAIN]]
    fig, ax = plt.subplots(figsize=(6.5, 2.9))
    x = range(len(r))
    w = 0.34
    for off, mode, color, label in ((-w / 2 - 0.02, "oos", BLUE, "Out-of-sample"), (w / 2 + 0.02, "is", ORANGE, "In-sample")):
        bars = ax.bar([i + off for i in x], r[mode], width=w, color=color, label=label)
        for bar, v in zip(bars, r[mode]):
            ax.text(bar.get_x() + bar.get_width() / 2, v + 0.25, str(v), ha="center", va="bottom", fontsize=8.5, color=INK)
    ax.set_xticks(list(x), r.index)
    ax.set_ylim(0, 12.9)
    ax.set_yticks([0, 3, 6, 9, 12])
    ax.set_ylabel("Scenarios won by the naïve hedge (of 12)")
    ax.grid(axis="x", visible=False)
    ax.tick_params(axis="x", length=0, labelcolor=INK)
    ax.legend(frameon=False, ncols=2, loc="upper right", bbox_to_anchor=(1.0, 1.14), fontsize=8.5)
    fig.tight_layout()
    fig.savefig(OUT / "fig2_naive_wins_in_vs_out.png", bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    he = pd.read_csv(data.RESULTS / "tables" / "effectiveness_long.csv")
    fig_hedge_ratios()
    fig_in_vs_out(he)
    print("figures ->", OUT)
