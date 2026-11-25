"""
Interactive version of the chip binning simulator.

    python -m streamlit run app.py
"""

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle
from matplotlib.collections import PatchCollection
import streamlit as st

import binsim as bs

st.set_page_config(page_title="Chip Binning Simulator", layout="wide")
st.title("Why an i5 and an i7 are often the same chip")
st.caption("Simulates manufacturing variation across wafers, works out each chip's speed and power, "
           "and sorts the chips into product tiers.")

BIN_COLORS = ["#2b4c7e", "#4a8fc2", "#9cc5e0", "#e3a857"]
SCRAP = "#c8553d"

with st.sidebar:
    st.header("Factory")
    var_scale = st.slider("Manufacturing variation (× default)", 0.25, 2.5, 1.0, 0.05)
    d0 = st.slider("Defect density (per cm²)", 0.0, 0.5, 0.10, 0.01)
    n_wafers = st.slider("Wafers to simulate", 5, 50, 20, 5)
    st.header("Products")
    tdp = st.slider("8-core power limit (W)", 70, 120, 85, 1)
    p_pro = st.number_input("Pro 8-core price ($)", 0, 2000, 450, 10)
    p_plus = st.number_input("Plus 8-core price ($)", 0, 2000, 330, 10)
    p_base = st.number_input("Base 8-core price ($)", 0, 2000, 250, 10)
    p_lite = st.number_input("Lite 6-core price ($)", 0, 2000, 180, 10)
    seed = st.number_input("Random seed", 0, 9999, 0)

skus = [
    ("Pro 8-core", 8, 3.80, float(tdp), float(p_pro)),
    ("Plus 8-core", 8, 3.50, float(tdp), float(p_plus)),
    ("Base 8-core", 8, 3.20, float(tdp), float(p_base)),
    ("Lite 6-core", 6, 3.20, float(tdp) * 0.765, float(p_lite)),
]


@st.cache_data
def run(n_wafers, seed, var_scale, d0):
    return bs.simulate(n_wafers=n_wafers, seed=seed, var_scale=var_scale, d0=d0)


sim = run(n_wafers, int(seed), var_scale, d0)
bins = bs.assign_bins(sim, skus)
strat = bs.strategies(sim, skus)
best_single = max(v for k, v in strat.items() if k.startswith("Only"))
full = strat["Binning + core harvesting"]

pro = skus[0]
good8 = (sim["dead_cores"] == 0) & ~sim["uncore_dead"]
fast = good8 & (sim["fmax"] >= pro[2])
power_limited = fast & (bs.power_at(pro[2], sim["p_leak"], 8) > pro[3])

m1, m2, m3 = st.columns(3)
m1.metric("Revenue per wafer, binning + harvesting", f"${full:,.0f}",
          f"{100 * (full / best_single - 1):+.0f}% vs best single product")
m2.metric("Chips in the top tier", f"{np.mean(bins == 0):.0%}")
m3.metric("Top-speed chips downgraded for leaking too much",
          f"{power_limited.sum() / max(fast.sum(), 1):.0%}")

c1, c2 = st.columns(2)

# wafer map
w = sim["wafer"] == 0
cw, ch = bs.CHIP["die_w"], bs.CHIP["die_h"]
fig, ax = plt.subplots(figsize=(5, 5))
rects = [Rectangle((x - cw / 2, y - ch / 2), cw, ch) for x, y in zip(sim["x"][w], sim["y"][w])]
ax.add_collection(PatchCollection(rects, facecolor=[BIN_COLORS[b] if b >= 0 else SCRAP for b in bins[w]],
                                  edgecolor="white", linewidth=0.4))
ax.add_patch(Circle((0, 0), 150, fill=False, color="#888"))
for i, s in enumerate(skus):
    ax.scatter([], [], marker="s", s=50, color=BIN_COLORS[i], label=s[0])
ax.scatter([], [], marker="s", s=50, color=SCRAP, label="Scrap")
ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.01), ncol=3, frameon=False, fontsize=8)
ax.set_xlim(-155, 155); ax.set_ylim(-155, 155); ax.set_aspect("equal"); ax.axis("off")
ax.set_title("One wafer, sorted into products", fontsize=10)
c1.pyplot(fig)

# speed vs leakage
rng = np.random.default_rng(1)
pick = rng.choice(len(bins), min(5000, len(bins)), replace=False)
fig, ax = plt.subplots(figsize=(5, 5))
for b in [-1, 3, 2, 1, 0]:
    k = pick[bins[pick] == b]
    ax.scatter(sim["p_leak"][k], sim["fmax"][k], s=4, alpha=0.6,
               color=SCRAP if b < 0 else BIN_COLORS[b], label="Scrap" if b < 0 else skus[b][0])
leak_limit = pro[3] - bs.CHIP["p_dyn_nominal"] * pro[2] / bs.CHIP["f_nominal"]
ax.axhline(pro[2], color="k", lw=0.8, ls="--")
ax.axvline(leak_limit, color="k", lw=0.8)
ax.set_xlabel("Leakage power (W)"); ax.set_ylabel("Maximum frequency (GHz)")
ax.set_title("Fast chips are leaky chips", fontsize=10)
ax.spines[["top", "right"]].set_visible(False)
ax.legend(frameon=False, fontsize=8, markerscale=3, loc="lower right")
c2.pyplot(fig)

st.subheader("Revenue per wafer by product strategy")
fig, ax = plt.subplots(figsize=(8, 3))
names = list(strat)
vals = [strat[k] for k in names]
ax.barh(names[::-1], vals[::-1], color=(["#bbbbbb"] * 3 + ["#4a8fc2", "#2b4c7e"])[::-1])
for i, v in enumerate(vals[::-1]):
    ax.text(v, i, f"  ${v / 1000:.0f}k", va="center", fontsize=8)
ax.set_xlim(0, max(vals) * 1.15)
ax.set_xlabel("USD per wafer")
ax.spines[["top", "right"]].set_visible(False)
st.pyplot(fig)

with st.expander("Share of chips in each tier"):
    st.table({"Tier": [s[0] for s in skus] + ["Scrap"],
              "Share of chips": [f"{np.mean(bins == i):.1%}" for i in range(len(skus))] + [f"{np.mean(bins == -1):.1%}"]})
