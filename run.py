# =============================================================================
# run.py  —  Entry point. Run a single simulation or full Monte Carlo.
# =============================================================================
#
# Usage:
#   python run.py                    ->  single base-case run + charts
#   python run.py --scale 1000       ->  quick test with 1/1000th workforce
#   python run.py --mc               ->  full Monte Carlo (500 runs, slow)
#   python run.py --mc --n 50        ->  quick MC with 50 runs
#   python run.py --stress           ->  stress test (high demand, high shock, low inflow)
#   python run.py --stress --scale 1000  ->  stress test at reduced scale
#
# All runs export a CSV with per-quarter data.
# --stress also runs the base case alongside for comparison.
#
# PLACEHOLDER: The simulation uses individual Ball objects (one per worker).
# At full scale (12.69M workers) this is too slow in pure Python.
# Use --scale to divide the workforce for testing. A future vectorised
# (numpy-based) version should replace the Ball loop entirely.
# =============================================================================

import argparse
import json
import sys
import time
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')   # non-interactive backend — saves to file, no GUI needed
import matplotlib.pyplot as plt
import matplotlib.cm as cm
from pathlib import Path

import config
from simulation import Simulation, SimParams
from monte_carlo import run_monte_carlo, percentile_summary, binding_tier


# =============================================================================
# Single run
# =============================================================================
def _print_table(df: pd.DataFrame, label: str = ""):
    if label:
        print(f"\n{'='*62}\n{label}\n{'='*62}")
    print(f"\n{'Year':>6}  {'Total Workers':>14}  {'System Vacuum':>14}  "
          f"{'Fill%':>6}  {'Binding Tier':>13}  {'Pool':>6}")
    print("-" * 72)
    for year in sorted(df["year"].unique()):
        ydf  = df[df["year"] == year]
        total_workers = ydf.groupby("year")["headcount"].sum().values[0]
        total_vacuum  = ydf["vacuum"].sum()
        total_demand  = ydf["demand_height"].sum()
        total_eff_vol = ydf["eff_volume"].sum()
        fill_pct      = (total_eff_vol / total_demand * 100) if total_demand > 0 else 0
        binding       = ydf.loc[ydf["vacuum"].idxmax(), "tier"]
        pool          = ydf["pool_size"].values[0]
        print(f"{year:>6.2f}  {total_workers:>14,}  {total_vacuum:>14.1f}  "
              f"{fill_pct:>5.1f}%  {binding:>13.1f}  {pool:>6}")


def run_single(scale: int = 1, n_years: int = 8, slow: bool = False):
    print(f"Running base-case simulation (workforce scale: 1/{scale}, {n_years} years)...")
    sim   = Simulation(SimParams(seed=config.MC_SEED, workforce_scale=scale, n_years=n_years))
    snaps = sim.run()
    df    = Simulation.to_dataframe(snaps)

    if slow:
        _print_table_slow(df, snaps, delay=0.4)
    else:
        _print_table(df, "BASE CASE")

    out_csv = Path("output_base.csv")
    df.to_csv(out_csv, index=False)
    print(f"\nData exported -> {out_csv.resolve()}  ({len(df)} rows)")

    _plot_single(df)
    return df


def _print_table_slow(df: pd.DataFrame, snaps, delay: float = 0.4):
    """Print one quarter at a time with a delay so you can watch it live."""
    print(f"\n{'='*62}\nBASE CASE  (live quarter-by-quarter)\n{'='*62}")
    print(f"\n{'Year':>6}  {'Total Workers':>14}  {'System Vacuum':>14}  "
          f"{'Fill%':>6}  {'Binding Tier':>13}  {'Pool':>6}")
    print("-" * 72)
    for year in sorted(df["year"].unique()):
        ydf          = df[df["year"] == year]
        total_workers = ydf["headcount"].sum()
        total_vacuum  = ydf["vacuum"].sum()
        total_demand  = ydf["demand_height"].sum()
        total_eff_vol = ydf["eff_volume"].sum()
        fill_pct      = (total_eff_vol / total_demand * 100) if total_demand > 0 else 0
        binding       = ydf.loc[ydf["vacuum"].idxmax(), "tier"]
        pool          = ydf["pool_size"].values[0]
        print(f"{year:>6.2f}  {total_workers:>14,}  {total_vacuum:>14.1f}  "
              f"{fill_pct:>5.1f}%  {binding:>13.1f}  {pool:>6}", flush=True)
        time.sleep(delay)


# =============================================================================
# Monte Carlo run
# =============================================================================
def run_mc(n_runs: int = config.MC_RUNS):
    print(f"\nRunning Monte Carlo ({n_runs} simulations)...")
    df      = run_monte_carlo(n_runs=n_runs)
    summary = percentile_summary(df, metric="vacuum")
    btier   = binding_tier(df)

    print(f"\n-- System-level vacuum P5/P50/P95 at 2033 --")
    final_year = df["year"].max()
    final = summary[summary["year"] == final_year]
    total = final.groupby("year")[["P5","P50","P95"]].sum()
    print(total.to_string())

    print(f"\n-- Most common binding tier (2033) --")
    last_btier = btier[btier["year"] == final_year]
    print(last_btier["binding_tier"].value_counts().head(5).to_string())

    _plot_mc(summary)
    return df, summary


# =============================================================================
# Plots
# =============================================================================
def _plot_single(df: pd.DataFrame):
    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    fig.suptitle("Labour Vacuum Simulation — Base Case", fontsize=14)

    years  = sorted(df["year"].unique())
    tiers  = sorted(df["tier"].unique())
    colors = cm.RdYlGn_r(np.linspace(0.1, 0.9, len(tiers)))

    # Chart 1: Vacuum per tier over time
    ax = axes[0, 0]
    for tier, col in zip(tiers, colors):
        tdf = df[df["tier"] == tier]
        ax.plot(tdf["year"], tdf["vacuum"], label=f"Tier {tier:.1f}", color=col)
    ax.set_title("Vacuum by tier (000 effective workers)"); ax.set_xlabel("Year")
    ax.legend(fontsize=7, ncol=2)

    # Chart 2: Fill % per tier over time
    ax = axes[0, 1]
    for tier, col in zip(tiers, colors):
        tdf = df[df["tier"] == tier]
        ax.plot(tdf["year"], tdf["fill_pct"] * 100, color=col, label=f"{tier:.1f}")
    ax.axhline(100, color="grey", linestyle="--", linewidth=0.8)
    ax.set_title("Fill % by tier"); ax.set_xlabel("Year"); ax.set_ylabel("%")

    # Chart 3: Total headcount over time
    ax = axes[1, 0]
    total_hc = df.groupby("year")["headcount"].sum()
    ax.plot(total_hc.index, total_hc.values, color="#2563eb", linewidth=2)
    ax.set_title("Total workforce headcount"); ax.set_xlabel("Year")

    # Chart 4: Exit breakdown over time (new event types)
    ax = axes[1, 1]
    exit_series = [
        ("exits_voluntary_quit",       "Voluntary quit",       "#f97316"),
        ("exits_retirement",           "Retirement",           "#ef4444"),
        ("exits_shock_removal",        "Shock removal",        "#7c3aed"),
        ("exits_career_change",        "Career change",        "#64748b"),
        ("exits_frustration_quit",     "Frustration quit",     "#0ea5e9"),
        ("exits_management_graduation","Management grad",      "#22c55e"),
    ]
    for col, label, colour in exit_series:
        if col in df.columns:
            series = df.groupby("year")[col].sum() / len(tiers)
            ax.plot(series.index, series.values, label=label, color=colour)
    ax.set_title("Exits per quarter"); ax.set_xlabel("Year")
    ax.legend(fontsize=7, ncol=2)

    plt.tight_layout()
    out = Path("output_single.png")
    plt.savefig(out, dpi=150)
    print(f"\nChart saved -> {out.resolve()}")
    plt.show()


def _plot_mc(summary: pd.DataFrame):
    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    fig.suptitle("Labour Vacuum — Monte Carlo P5/P50/P95", fontsize=14)
    tiers  = sorted(summary["tier"].unique())
    colors = cm.RdYlGn_r(np.linspace(0.1, 0.9, len(tiers)))

    # Chart 1: P50 vacuum per tier
    ax = axes[0, 0]
    for tier, col in zip(tiers, colors):
        tdf = summary[summary["tier"] == tier]
        ax.plot(tdf["year"], tdf["P50"], color=col, label=f"{tier:.1f}")
        ax.fill_between(tdf["year"], tdf["P5"], tdf["P95"],
                        color=col, alpha=0.08)
    ax.set_title("Vacuum P50 by tier (shaded P5-P95)")
    ax.legend(fontsize=7, ncol=2)

    # Chart 2: Total system vacuum P5/P50/P95
    ax = axes[0, 1]
    sys = summary.groupby("year")[["P5","P50","P95"]].sum().reset_index()
    ax.plot(sys["year"], sys["P50"], color="#ef4444", linewidth=2, label="P50")
    ax.fill_between(sys["year"], sys["P5"], sys["P95"],
                    color="#ef4444", alpha=0.15, label="P5-P95")
    ax.set_title("System-level vacuum P5/P50/P95")
    ax.legend()

    # Chart 3: Fill % P50 per tier
    ax = axes[1, 0]
    for tier, col in zip(tiers, colors):
        tdf = summary[summary["tier"] == tier]
        ax.plot(tdf["year"], tdf["P50"] * 0 + 80,  # PLACEHOLDER line
                color=col, alpha=0.2)
    ax.set_title("Fill % P50 (placeholder — wire to fill_pct in next iteration)")

    # Chart 4: Heatmap of vacuum by tier x year (P50)
    ax = axes[1, 1]
    pivot = summary.pivot(index="tier", columns="year", values="P50")
    im = ax.imshow(pivot.values, aspect="auto", cmap="RdYlGn_r",
                   origin="lower")
    ax.set_yticks(range(len(tiers)))
    ax.set_yticklabels([f"{t:.1f}" for t in tiers], fontsize=8)
    ax.set_title("Vacuum heatmap: tier x year (P50)")
    plt.colorbar(im, ax=ax, label="vacuum (000s)")

    plt.tight_layout()
    out = Path("output_mc.png")
    plt.savefig(out, dpi=150)
    print(f"\nMC chart saved -> {out.resolve()}")
    plt.show()


# =============================================================================
# Stress test
# =============================================================================
# Stress scenario parameters:
#   - Industry growth 2× baseline (rapid demand expansion)
#   - Shock probability 3× baseline (frequent policy disruptions)
#   - Shock removal rate 3× baseline (larger shocks)
#   - Manufacturing entry % halved (supply squeeze)
#   - Reshoring 1.5× baseline (extra demand pressure)
# Outputs: comparison table + CSV + charts for both base and stress cases.
STRESS_OVERRIDES = dict(
    industry_growth    = config.INDUSTRY_GROWTH_RATE * 2.0,
    shock_probability  = min(config.SHOCK_PROBABILITY * 3.0, 0.50),
    shock_removal_rate = min(config.SHOCK_REMOVAL_RATE * 3.0, 0.20),
    mfg_entry_pct      = config.MFG_ENTRY_PCT * 0.5,
    reshoring_total_m  = config.RESHORING_TOTAL_M * 1.5,
)


def run_stress(scale: int = 1):
    print(f"\nRunning STRESS TEST (workforce scale: 1/{scale})...")
    print("Stress overrides:")
    for k, v in STRESS_OVERRIDES.items():
        print(f"  {k:<25} = {v:.4f}")

    # ── Base case ──────────────────────────────────────────────────────────────
    base_params  = SimParams(seed=config.MC_SEED, workforce_scale=scale)
    base_sim     = Simulation(base_params)
    base_snaps   = base_sim.run()
    df_base      = Simulation.to_dataframe(base_snaps)

    # ── Stress case ────────────────────────────────────────────────────────────
    stress_params = SimParams(
        seed               = config.MC_SEED,
        workforce_scale    = scale,
        industry_growth    = STRESS_OVERRIDES["industry_growth"],
        shock_probability  = STRESS_OVERRIDES["shock_probability"],
        shock_removal_rate = STRESS_OVERRIDES["shock_removal_rate"],
        mfg_entry_pct      = STRESS_OVERRIDES["mfg_entry_pct"],
        reshoring_total_m  = STRESS_OVERRIDES["reshoring_total_m"],
    )
    stress_sim   = Simulation(stress_params)
    stress_snaps = stress_sim.run()
    df_stress    = Simulation.to_dataframe(stress_snaps)

    # ── Print tables ───────────────────────────────────────────────────────────
    _print_table(df_base,   "BASE CASE")
    _print_table(df_stress, "STRESS TEST")

    # ── Export CSVs ────────────────────────────────────────────────────────────
    base_csv   = Path("output_base.csv")
    stress_csv = Path("output_stress.csv")
    df_base.to_csv(base_csv,     index=False)
    df_stress.to_csv(stress_csv, index=False)
    print(f"\nBase data   -> {base_csv.resolve()}  ({len(df_base)} rows)")
    print(f"Stress data -> {stress_csv.resolve()}  ({len(df_stress)} rows)")

    # ── Comparison chart ───────────────────────────────────────────────────────
    _plot_stress_comparison(df_base, df_stress)
    return df_base, df_stress


def _plot_stress_comparison(df_base: pd.DataFrame, df_stress: pd.DataFrame):
    fig, axes = plt.subplots(2, 3, figsize=(18, 10))
    fig.suptitle("Labour Vacuum — Base vs Stress Test", fontsize=14)

    years_b = sorted(df_base["year"].unique())
    years_s = sorted(df_stress["year"].unique())
    tiers   = sorted(df_base["tier"].unique())
    colors  = cm.RdYlGn_r(np.linspace(0.1, 0.9, len(tiers)))

    # 1. System vacuum over time
    ax = axes[0, 0]
    sys_b = df_base.groupby("year")["vacuum"].sum()
    sys_s = df_stress.groupby("year")["vacuum"].sum()
    ax.plot(sys_b.index, sys_b.values, color="#2563eb", linewidth=2, label="Base")
    ax.plot(sys_s.index, sys_s.values, color="#ef4444", linewidth=2, label="Stress")
    ax.set_title("System vacuum (all tiers)")
    ax.set_xlabel("Year"); ax.legend()

    # 2. System fill % over time
    ax = axes[0, 1]
    def fill_series(df):
        g = df.groupby("year")
        return (g["eff_volume"].sum() / g["demand_height"].sum().replace(0, float("nan"))) * 100
    ax.plot(years_b, fill_series(df_base).values,   color="#2563eb", linewidth=2, label="Base")
    ax.plot(years_s, fill_series(df_stress).values, color="#ef4444", linewidth=2, label="Stress")
    ax.axhline(100, color="grey", linestyle="--", linewidth=0.8)
    ax.set_title("System fill % (effective / demand)")
    ax.set_xlabel("Year"); ax.set_ylabel("%"); ax.legend()

    # 3. Total headcount
    ax = axes[0, 2]
    hc_b = df_base.groupby("year")["headcount"].sum()
    hc_s = df_stress.groupby("year")["headcount"].sum()
    ax.plot(hc_b.index, hc_b.values, color="#2563eb", linewidth=2, label="Base")
    ax.plot(hc_s.index, hc_s.values, color="#ef4444", linewidth=2, label="Stress")
    ax.set_title("Total workforce headcount")
    ax.set_xlabel("Year"); ax.legend()

    # 4. Pool size over time
    ax = axes[1, 0]
    pool_b = df_base.groupby("year")["pool_size"].first()
    pool_s = df_stress.groupby("year")["pool_size"].first()
    ax.plot(pool_b.index, pool_b.values, color="#2563eb", linewidth=2, label="Base")
    ax.plot(pool_s.index, pool_s.values, color="#ef4444", linewidth=2, label="Stress")
    ax.set_title("Market pool size (workers seeking placement)")
    ax.set_xlabel("Year"); ax.legend()

    # 5. Vacuum by tier — stress case heatmap
    ax = axes[1, 1]
    pivot = df_stress.pivot_table(index="tier", columns="year", values="vacuum", aggfunc="sum")
    im = ax.imshow(pivot.values, aspect="auto", cmap="RdYlGn_r", origin="lower")
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels([f"{t:.1f}" for t in pivot.index], fontsize=8)
    ax.set_title("Stress: vacuum heatmap (tier × year)")
    plt.colorbar(im, ax=ax)

    # 6. Exit breakdown — stress
    ax = axes[1, 2]
    exit_series_cfg = [
        ("exits_voluntary_quit",        "Voluntary quit",    "#f97316"),
        ("exits_retirement",            "Retirement",        "#ef4444"),
        ("exits_shock_removal",         "Shock removal",     "#7c3aed"),
        ("exits_career_change",         "Career change",     "#64748b"),
        ("exits_frustration_quit",      "Frustration quit",  "#0ea5e9"),
        ("exits_management_graduation", "Mgmt grad",         "#22c55e"),
    ]
    for col, label, colour in exit_series_cfg:
        if col in df_stress.columns:
            s = df_stress.groupby("year")[col].sum() / len(tiers)
            ax.plot(s.index, s.values, label=label, color=colour)
    ax.set_title("Stress: exits per quarter")
    ax.set_xlabel("Year"); ax.legend(fontsize=7, ncol=2)

    plt.tight_layout()
    out = Path("output_stress.png")
    plt.savefig(out, dpi=150)
    print(f"\nStress chart saved -> {out.resolve()}")


# =============================================================================
# Streaming JSON support (called by the PyQt6 desktop app via subprocess)
# =============================================================================

# Knob id -> SimParams field name
_KNOB_TO_SIMPARAMS = {
    'alpha':       'alpha',
    'beta':        'beta',
    'base_growth': 'base_growth_rate',
    'mfg_pct':     'mfg_entry_pct',
    'shock_prob':  'shock_probability',
    'shock_rem':   'shock_removal_rate',
    'ind_growth':  'industry_growth',
    'n_years':     'n_years',
}


def _apply_config_overrides(overrides: dict):
    """Set config module attributes from knob-id keyed overrides dict."""
    # Direct config attributes
    direct = {
        'cohort':        'ANNUAL_WORKING_AGE_COHORT',
        'ent_skill':     'ENTRANT_SKILL_MEAN',
        'regression':    'REGRESSION_RATE',
        'mgmt_rate':     'MGMT_GRAD_RATE',
        'retire_thr':    'RETIREMENT_TENURE_THRESHOLD',
        'frust_base':    'FRUSTRATION_BASE_RATE',
    }
    for kid, attr in direct.items():
        if kid in overrides:
            setattr(config, attr, overrides[kid])

    # BARRIER_PARAMS sub-keys
    barrier_map = {
        'place_sigma': 'sigma_right_base',
        'pool_decay':  'pool_decay_rate',
    }
    for kid, bkey in barrier_map.items():
        if kid in overrides:
            config.BARRIER_PARAMS[bkey] = overrides[kid]

    # grad_mult: multiply all GRAD_SKILL_THRESH by (val / 0.90) * original
    if 'grad_mult' in overrides:
        frac = max(0.70, min(0.99, overrides['grad_mult']))
        for tier in config.GRAD_SKILL_THRESH:
            config.GRAD_SKILL_THRESH[tier] = round(tier * frac, 4)

    # injury_mult: scale all injury rates
    if 'injury_mult' in overrides:
        m = overrides['injury_mult']
        for tier in config.FATAL_INJURY_RATE:
            config.FATAL_INJURY_RATE[tier]   *= m
            config.SERIOUS_INJURY_RATE[tier] *= m
            config.MINOR_INJURY_RATE[tier]   *= m

    # pen_mult: scale injury skill penalties
    if 'pen_mult' in overrides:
        m = overrides['pen_mult']
        for tier in config.INJURY_SKILL_PENALTY:
            config.INJURY_SKILL_PENALTY[tier] *= m

    # quit_rate T0.1: scale all QUIT_RATE_BY_TIER proportionally
    if 'quit_rate' in overrides:
        base = config.QUIT_RATE_BY_TIER.get(0.1, 0.025)
        ratio = overrides['quit_rate'] / max(base, 1e-9)
        for tier in config.QUIT_RATE_BY_TIER:
            config.QUIT_RATE_BY_TIER[tier] = min(
                config.QUIT_RATE_BY_TIER[tier] * ratio, 0.25
            )

    # career_change T0.1: scale all CAREER_CHANGE_RATE proportionally
    if 'career_change' in overrides:
        base = config.CAREER_CHANGE_RATE.get(0.1, 0.017)
        ratio = overrides['career_change'] / max(base, 1e-9)
        for tier in config.CAREER_CHANGE_RATE:
            config.CAREER_CHANGE_RATE[tier] = min(
                config.CAREER_CHANGE_RATE[tier] * ratio, 0.15
            )

    # shocks_on toggle: zero shock probability when disabled
    if 'shocks_on' in overrides and not overrides['shocks_on']:
        config.SHOCK_PROBABILITY = 0.0


def _build_sim_params(scale: int, overrides: dict) -> SimParams:
    """Build SimParams, applying any overrides from the GUI controls."""
    kwargs: dict = {'seed': config.MC_SEED, 'workforce_scale': scale}

    for kid, field in _KNOB_TO_SIMPARAMS.items():
        if kid in overrides:
            kwargs[field] = overrides[kid]

    # reshoring: knob unit = raw workers, SimParams unit = millions
    if 'reshoring' in overrides:
        kwargs['reshoring_total_m'] = overrides['reshoring'] / 1_000_000

    # shock toggle overrides shock_probability
    if 'shocks_on' in overrides and not overrides['shocks_on']:
        kwargs['shock_probability'] = 0.0

    return SimParams(**kwargs)


def _emit_json_quarter(snap):
    """Print one JSON_QUARTER: line to stdout for each simulation snapshot."""
    per_tier = [
        {
            'tier':      t['tier'],
            'headcount': t['headcount'],
            'vacuum':    t['vacuum'],
            'fill_pct':  t['fill_pct'],
            'demand':    t['demand_height'],
            'eff_volume': t['eff_volume'],
        }
        for t in snap.per_tube
    ]
    system_vacuum   = sum(t['vacuum']    for t in per_tier)
    total_demand    = sum(t['demand']    for t in per_tier)
    total_eff       = sum(t['eff_volume'] for t in per_tier)
    fill_pct        = (total_eff / total_demand) if total_demand > 0 else 0.0
    binding_tier    = max(per_tier, key=lambda t: t['vacuum'])['tier'] if per_tier else 0.0

    record = {
        'year':          snap.year,
        'quarter':       snap.step,
        'total_workers': snap.total_balls,
        'system_vacuum': round(system_vacuum, 2),
        'fill_pct':      round(fill_pct, 4),
        'pool_size':     snap.pool_size,
        'binding_tier':  binding_tier,
        'per_tier':      per_tier,
        'exits':         snap.exits,
    }
    sys.stdout.write(f"JSON_QUARTER:{json.dumps(record)}\n")
    sys.stdout.flush()


def run_streaming(scale: int = 1, overrides: dict = None):
    """Run simulation and emit JSON_QUARTER: lines to stdout."""
    overrides = overrides or {}
    _apply_config_overrides(overrides)
    params = _build_sim_params(scale, overrides)

    sys.stdout.write("LOG:Starting simulation...\n")
    sys.stdout.flush()

    sim   = Simulation(params)
    snaps = sim.run()

    for snap in snaps:
        _emit_json_quarter(snap)

    sys.stdout.write("LOG:Simulation complete.\n")
    sys.stdout.flush()


# =============================================================================
# CLI
# =============================================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mc",          action="store_true", help="Run Monte Carlo")
    parser.add_argument("--stress",      action="store_true", help="Run stress test vs base case")
    parser.add_argument("--stream-json", action="store_true",
                        help="Emit JSON_QUARTER: lines; used by desktop app")
    parser.add_argument("--params",      action="store_true",
                        help="Read JSON params override from first stdin line")
    parser.add_argument("--n",           type=int, default=config.MC_RUNS,
                        help="Number of MC runs (default: config.MC_RUNS)")
    parser.add_argument("--scale",       type=int, default=1,
                        help="Divide workforce by this factor for fast testing "
                             "(e.g. --scale 1000 uses ~12,690 workers)")
    parser.add_argument("--slow",        action="store_true",
                        help="Print each quarter live with a short delay so you can watch it run")
    parser.add_argument("--years",       type=int, default=8,
                        help="Simulation length in years (default: 8 = 2025-2033). "
                             "Use 20 or 30 for long-range projections.")
    args = parser.parse_args()

    # Read optional params override from stdin
    overrides: dict = {}
    if args.params:
        raw = sys.stdin.readline().strip()
        if raw:
            try:
                overrides = json.loads(raw)
            except json.JSONDecodeError:
                pass

    if args.stream_json:
        overrides['n_years'] = args.years
        run_streaming(scale=args.scale, overrides=overrides)
    elif args.mc:
        run_mc(n_runs=args.n)
    elif args.stress:
        run_stress(scale=args.scale)
    else:
        run_single(scale=args.scale, n_years=args.years, slow=args.slow)
