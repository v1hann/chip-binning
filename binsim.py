"""
binsim.py — process variation, speed binning and core harvesting.

Core idea
---------
No two chips come out of a fab identical. Tiny variations in transistor
dimensions (channel length L) and threshold voltage (Vth) make some chips
faster than others, and the faster ones also tend to leak more current.

Chipmakers test every die and sort it into product tiers ("bins"). A die
that can't hit the top tier's speed, or would burn too much power doing it,
gets sold as a cheaper tier. A die with a defect in one of its cores can have
that core switched off and be sold as a lower core-count part ("harvesting").

This module simulates a wafer's worth of dies from the transistor level up,
bins them, and measures how much revenue binning and harvesting recover
compared to selling a single product.

Physics used (all standard, simplified):
- Drive current: alpha-power law, I_on ∝ (Vdd - Vth)^a / L   (Sakurai & Newton)
- Short-channel effect (DIBL): shorter L lowers the effective Vth
- Chip speed is set by its slowest critical path (min over many paths)
- Leakage: subthreshold current ∝ exp(-Vth / (n·kT/q)) / L
- Dynamic power ∝ frequency (C·V²·f at fixed voltage)
"""

import numpy as np

# ---------------------------------------------------------------------------
# Parameters (all assumptions, chosen to be in a realistic range)
# ---------------------------------------------------------------------------

PROCESS = dict(
    vdd=0.90,            # supply voltage (V)
    vth0=0.30,           # nominal threshold voltage (V)
    alpha=1.3,           # alpha-power-law exponent for short-channel devices
    dibl=0.30,           # Vth drop per unit fractional shortening of L (V)
    n_vt=0.046,          # n·kT/q at ~85 °C (V): leakage e-folds per 46 mV of Vth
    # systematic across-wafer pattern ("bowl"): edge dies have longer L, higher Vth
    sys_L_edge=0.03,     # +3% L at the wafer edge
    sys_vth_edge=0.015,  # +15 mV Vth at the wafer edge
    # wafer-to-wafer variation
    w2w_L=0.010, w2w_vth=0.008,
    # die-to-die random variation
    d2d_L=0.015, d2d_vth=0.012,
    # within-die variation of each critical path
    n_paths=200, path_vth=0.010,
)

CHIP = dict(
    f_nominal=4.0,       # GHz a perfectly nominal path would run at
    p_dyn_nominal=65.0,  # W of switching power at f_nominal (8 cores)
    p_leak_nominal=15.0, # W of leakage for a nominal die (8 cores)
    die_w=12.5, die_h=12.0,
    core_area_frac=0.60, n_cores=8,   # cores take 60% of the die, the rest is shared
)

# product line: name, cores, min GHz, max watts, price USD
SKUS = [
    ("Pro 8-core",  8, 3.80, 85.0, 450.0),
    ("Plus 8-core", 8, 3.50, 85.0, 330.0),
    ("Base 8-core", 8, 3.20, 85.0, 250.0),
    ("Lite 6-core", 6, 3.20, 65.0, 180.0),
]
DEFECT = dict(d0=0.10)   # killer defects per cm²


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------

def die_centres(die_w, die_h, wafer_d=300.0, edge_excl=3.0, scribe=0.1):
    """Centres (x, y) in mm of all complete dies on the wafer, best of a few grid offsets."""
    R = wafer_d / 2 - edge_excl
    px, py = die_w + scribe, die_h + scribe
    n = int(R / min(px, py)) + 2
    ii, jj = np.meshgrid(np.arange(-n, n + 1), np.arange(-n, n + 1))
    best = None
    for ox in np.linspace(0, px, 6, endpoint=False):
        for oy in np.linspace(0, py, 6, endpoint=False):
            x0, y0 = ox + ii.ravel() * px, oy + jj.ravel() * py
            fx = np.maximum(abs(x0), abs(x0 + die_w))
            fy = np.maximum(abs(y0), abs(y0 + die_h))
            ok = fx ** 2 + fy ** 2 <= R ** 2
            if best is None or ok.sum() > len(best[0]):
                best = (x0[ok] + die_w / 2, y0[ok] + die_h / 2)
    return best[0], best[1], R


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------

def simulate(n_wafers=50, seed=0, var_scale=1.0, process=PROCESS, chip=CHIP, d0=DEFECT["d0"]):
    """
    Simulate n_wafers wafers. Returns a dict of per-die arrays:
        wafer, x, y, r_norm, L, vth, fmax (GHz), p_leak (W), dead_cores, uncore_dead
    var_scale multiplies every random variation (1 = default fab, 2 = twice as noisy).
    """
    p, c = process, chip
    rng = np.random.default_rng(seed)
    xc, yc, R = die_centres(c["die_w"], c["die_h"])
    nd = len(xc)
    N = nd * n_wafers
    wafer = np.repeat(np.arange(n_wafers), nd)
    x, y = np.tile(xc, n_wafers), np.tile(yc, n_wafers)
    rn2 = (x ** 2 + y ** 2) / R ** 2                     # 0 at centre, 1 at edge
    s = var_scale

    # channel length (relative to nominal) and threshold voltage per die
    L = (1 + p["sys_L_edge"] * rn2
         + s * p["w2w_L"] * rng.standard_normal(n_wafers)[wafer]
         + s * p["d2d_L"] * rng.standard_normal(N))
    vth = (p["vth0"] + p["sys_vth_edge"] * rn2
           + s * p["w2w_vth"] * rng.standard_normal(n_wafers)[wafer]
           + s * p["d2d_vth"] * rng.standard_normal(N))
    vth_eff = vth - p["dibl"] * (1 / L - 1)            # shorter L -> lower effective Vth

    # speed: every critical path gets its own local Vth wobble; the slowest wins
    def speed(v, l):
        return (p["vdd"] - v) ** p["alpha"] / l
    s0 = speed(p["vth0"], 1.0)
    path_v = vth_eff[:, None] + s * p["path_vth"] * rng.standard_normal((N, p["n_paths"]))
    fmax = c["f_nominal"] * speed(path_v, L[:, None]).min(axis=1) / s0

    # leakage: exponential in Vth, inversely proportional to L
    p_leak = c["p_leak_nominal"] * np.exp(-(vth_eff - p["vth0"]) / p["n_vt"]) / L

    # random killer defects: land either in a core or in shared logic
    die_area_cm2 = c["die_w"] * c["die_h"] / 100
    n_def = rng.poisson(d0 * die_area_cm2, N)
    dead_cores = np.zeros(N, int)
    uncore_dead = np.zeros(N, bool)
    for k in np.nonzero(n_def)[0]:
        u = rng.random(n_def[k])
        in_core = u < c["core_area_frac"]
        uncore_dead[k] = (~in_core).any()
        dead_cores[k] = len(np.unique(rng.integers(0, c["n_cores"], in_core.sum())))

    return dict(wafer=wafer, x=x, y=y, r_norm=np.sqrt(rn2), L=L, vth=vth_eff,
                fmax=fmax, p_leak=p_leak, dead_cores=dead_cores, uncore_dead=uncore_dead,
                dies_per_wafer=nd, n_wafers=n_wafers)


def power_at(f_ghz, p_leak, cores, chip=CHIP):
    """Total power running at frequency f with the given number of active cores."""
    frac = cores / chip["n_cores"]
    return frac * (chip["p_dyn_nominal"] * f_ghz / chip["f_nominal"] + p_leak)


# ---------------------------------------------------------------------------
# Binning
# ---------------------------------------------------------------------------

def assign_bins(sim, skus=SKUS, harvest=True, allowed=None, chip=CHIP):
    """
    Give every die the most valuable SKU it qualifies for.

    A die qualifies for a SKU if:
      - it has at least that many working cores and no defect in shared logic
      - its slowest path runs at >= the SKU's frequency
      - its power at that frequency (with only the SKU's cores on) is <= the SKU's limit
    harvest=False: dies with any dead core are thrown away.
    allowed: optional list of SKU indices the company sells (to model a single-product strategy).

    Returns (bin index per die, -1 = scrap), plus why top-speed dies missed the top bin.
    """
    N = len(sim["fmax"])
    bins = np.full(N, -1)
    working = chip["n_cores"] - sim["dead_cores"]
    usable = ~sim["uncore_dead"]
    if not harvest:
        usable &= sim["dead_cores"] == 0
    idx = range(len(skus)) if allowed is None else allowed
    for i in sorted(idx, key=lambda i: -skus[i][4]):           # most valuable first
        name, cores, fmin, pmax, price = skus[i]
        ok = (bins == -1) & usable & (working >= cores) & (sim["fmax"] >= fmin)
        ok &= power_at(fmin, sim["p_leak"], cores) <= pmax
        bins[ok] = i
    return bins


def revenue_per_wafer(sim, bins, skus=SKUS):
    prices = np.array([s[4] for s in skus])
    return prices[bins[bins >= 0]].sum() / sim["n_wafers"]


def strategies(sim, skus=SKUS):
    """Revenue per wafer under different product strategies."""
    out = {}
    for i in range(3):   # single 8-core product, nothing else sold
        out[f"Only sell {skus[i][0]}"] = revenue_per_wafer(sim, assign_bins(sim, skus, harvest=False, allowed=[i]))
    out["Speed binning (3 tiers)"] = revenue_per_wafer(sim, assign_bins(sim, skus, harvest=False, allowed=[0, 1, 2]))
    out["Binning + core harvesting"] = revenue_per_wafer(sim, assign_bins(sim, skus, harvest=True))
    return out
