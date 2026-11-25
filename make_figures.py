"""
make_figures.py — runs the binning study and saves figures + results summary.

    python make_figures.py
"""

import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle
from matplotlib.collections import PatchCollection

import binsim as bs

OUT = "figures"
os.makedirs(OUT, exist_ok=True)
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
BIN_COLORS = ["#2b4c7e", "#4a8fc2", "#9cc5e0", "#e3a857"]
SCRAP = "#c8553d"
lines = []


def log(s=""):
    print(s)
    lines.append(s)


sim = bs.simulate(n_wafers=50, seed=0)
bins = bs.assign_bins(sim)
N = len(bins)
log(f"Simulated {sim['n_wafers']} wafers x {sim['dies_per_wafer']} dies = {N} dies")
for i, sku in enumerate(bs.SKUS):
    log(f"  {sku[0]:12s} {np.mean(bins == i):6.1%}")
log(f"  {'Scrap':12s} {np.mean(bins == -1):6.1%}")

# ---------------------------------------------------------------------------
# Figure 1: one wafer coloured by bin
# ---------------------------------------------------------------------------
w = 3
m = sim["wafer"] == w
cw, ch = bs.CHIP["die_w"], bs.CHIP["die_h"]
fig, (ax, ax2) = plt.subplots(1, 2, figsize=(11, 5.4), gridspec_kw={"width_ratios": [1.1, 1]})
rects = [Rectangle((x - cw / 2, y - ch / 2), cw, ch) for x, y in zip(sim["x"][m], sim["y"][m])]
cols = [BIN_COLORS[b] if b >= 0 else SCRAP for b in bins[m]]
ax.add_collection(PatchCollection(rects, facecolor=cols, edgecolor="white", linewidth=0.4))
ax.add_patch(Circle((0, 0), 150, fill=False, color="#888"))
ax.set_xlim(-155, 155); ax.set_ylim(-155, 155); ax.set_aspect("equal"); ax.axis("off")
ax.set_title("One simulated wafer, every chip sorted into a product", fontsize=10)

# tier mix by distance from the wafer centre, across all wafers
edges = [0, 0.25, 0.5, 0.75, 1.0]
labels = ["Centre\n(0-25%)", "25-50%", "50-75%", "Edge\n(75-100%)"]
bottom = np.zeros(4)
order = [(0, BIN_COLORS[0], bs.SKUS[0][0]), (1, BIN_COLORS[1], bs.SKUS[1][0]),
         (2, BIN_COLORS[2], bs.SKUS[2][0]), (3, BIN_COLORS[3], bs.SKUS[3][0]), (-1, SCRAP, "Scrap")]
for b, col, lab in order:
    share = np.array([np.mean(bins[(sim["r_norm"] >= lo) & (sim["r_norm"] < hi)] == b)
                      for lo, hi in zip(edges[:-1], edges[1:])])
    ax2.bar(labels, share * 100, bottom=bottom, color=col, label=lab, width=0.65)
    if b == 0:
        for i, s in enumerate(share):
            ax2.text(i, s * 50, f"{s:.0%}", ha="center", va="center", color="white", fontsize=9)
    bottom += share * 100
ax2.set_ylabel("Share of chips (%)"); ax2.set_ylim(0, 100)
ax2.set_xlabel("Distance from wafer centre (% of radius)")
ax2.set_title(f"Across all {N:,} chips: top-tier chips come from the centre", fontsize=10)
ax2.legend(frameon=False, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=5)
fig.tight_layout(); fig.savefig(f"{OUT}/1_wafer_bin_map.png", dpi=160); plt.close(fig)

centre, edge = sim["r_norm"] < 0.5, sim["r_norm"] > 0.85
log(f"\nTop-bin share: centre of wafer {np.mean(bins[centre] == 0):.0%}, outer edge {np.mean(bins[edge] == 0):.0%}")

# ---------------------------------------------------------------------------
# Figure 2: fast chips are leaky chips
# ---------------------------------------------------------------------------
pro = bs.SKUS[0]
leak_limit = pro[3] - bs.CHIP["p_dyn_nominal"] * pro[2] / bs.CHIP["f_nominal"]   # leakage budget at Pro speed
good8 = (sim["dead_cores"] == 0) & ~sim["uncore_dead"]
fast = good8 & (sim["fmax"] >= pro[2])
power_limited = fast & (bs.power_at(pro[2], sim["p_leak"], 8) > pro[3])
log(f"\nDies fast enough for {pro[0]}: {fast.mean():.1%} of all dies")
log(f"  of those, {power_limited.sum() / fast.sum():.0%} were downgraded because they leak too much")
log(f"  correlation between max speed and leakage: {np.corrcoef(sim['fmax'], sim['p_leak'])[0, 1]:.2f}")

rng = np.random.default_rng(1)
pick = rng.choice(N, 6000, replace=False)
fig, ax = plt.subplots(figsize=(7, 4.8))
for b in [-1, 3, 2, 1, 0]:
    k = pick[bins[pick] == b]
    ax.scatter(sim["p_leak"][k], sim["fmax"][k], s=4, alpha=0.6,
               color=SCRAP if b < 0 else BIN_COLORS[b], label="Scrap" if b < 0 else bs.SKUS[b][0])
for sku, col in zip(bs.SKUS[:3], BIN_COLORS):
    ax.axhline(sku[2], color=col, lw=0.8, ls="--")
ax.plot([leak_limit, leak_limit], [pro[2], ax.get_ylim()[1]], color="k", lw=1.2)
ax.text(leak_limit + 0.5, pro[2] + 0.45, f"{pro[0]} power limit ({pro[3]:.0f} W):\nchips to the right are fast\nbut leak too much", fontsize=8.5, bbox=dict(facecolor="white", edgecolor="none", alpha=0.85))
ax.set_xlabel("Leakage power (W)"); ax.set_ylabel("Maximum stable frequency (GHz)")
ax.set_title("Fast chips are leaky chips: the top tier is limited by power, not just speed")
ax.legend(frameon=False, fontsize=8, markerscale=3, loc="lower right")
fig.tight_layout(); fig.savefig(f"{OUT}/2_speed_vs_leakage.png", dpi=160); plt.close(fig)

# ---------------------------------------------------------------------------
# Figure 3: revenue per wafer by strategy
# ---------------------------------------------------------------------------
strat = bs.strategies(sim)
best_single = max(v for k, v in strat.items() if k.startswith("Only"))
log("\nRevenue per wafer:")
for k, v in strat.items():
    log(f"  {k:28s} ${v:>9,.0f}   ({100 * (v / best_single - 1):+.0f}% vs best single product)")
fig, ax = plt.subplots(figsize=(7.5, 3.8))
names = list(strat)
vals = [strat[k] for k in names]
colors = ["#bbbbbb"] * 3 + ["#4a8fc2", "#2b4c7e"]
ax.barh(names[::-1], vals[::-1], color=colors[::-1])
for i, v in enumerate(vals[::-1]):
    ax.text(v + 1500, i, f"${v / 1000:.0f}k", va="center", fontsize=9)
ax.set_xlabel("Revenue per wafer (USD)")
ax.set_title("Same wafers, different product strategy")
ax.set_xlim(0, max(vals) * 1.15)
fig.tight_layout(); fig.savefig(f"{OUT}/3_revenue_by_strategy.png", dpi=160); plt.close(fig)

# ---------------------------------------------------------------------------
# Figure 4: binning matters more as variation grows
# ---------------------------------------------------------------------------
scales = np.array([0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0])
single, binned = [], []
for sc in scales:
    s = bs.simulate(n_wafers=30, seed=2, var_scale=sc)
    st = bs.strategies(s)
    single.append(max(v for k, v in st.items() if k.startswith("Only")))
    binned.append(st["Binning + core harvesting"])
single, binned = np.array(single), np.array(binned)
log("\nVariation sensitivity (x default variation -> uplift of binning+harvesting over best single product):")
for sc, a, b in zip(scales, single, binned):
    log(f"  {sc:.2f}x: single ${a:,.0f}, binned ${b:,.0f}, uplift {100 * (b / a - 1):.0f}%")
fig, ax = plt.subplots(figsize=(7, 4))
ax.plot(scales, single, "o-", color="#999", label="Best single product")
ax.plot(scales, binned, "o-", color="#2b4c7e", label="Binning + core harvesting")
ax.fill_between(scales, single, binned, color="#2b4c7e", alpha=0.1)
ax.set_xlabel("Manufacturing variation (× default)"); ax.set_ylabel("Revenue per wafer (USD)")
ax.set_title("Binning recovers the most value at moderate variation")
ax.legend(frameon=False)
fig.tight_layout(); fig.savefig(f"{OUT}/4_variation_sensitivity.png", dpi=160); plt.close(fig)

with open(f"{OUT}/results.txt", "w") as f:
    f.write("\n".join(lines) + "\n")
print("\nSaved figures to", OUT)
