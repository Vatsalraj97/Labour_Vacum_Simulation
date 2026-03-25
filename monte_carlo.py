# =============================================================================
# monte_carlo.py  —  Run N simulations with varied parameters
# =============================================================================

from __future__ import annotations
import numpy as np
import pandas as pd
from tqdm import tqdm
import config
from simulation import Simulation, SimParams


def run_monte_carlo(n_runs: int = config.MC_RUNS,
                    seed:   int = config.MC_SEED) -> pd.DataFrame:
    """
    Run N complete simulations, each with a different parameter draw.
    Returns a DataFrame with all runs stacked — one row per (run, step, tier).

    Parameters
    ----------
    n_runs : number of Monte Carlo runs
    seed   : master seed for reproducibility (each run gets seed+i)
    """
    rng = np.random.default_rng(seed)
    all_dfs = []

    for i in tqdm(range(n_runs), desc="Monte Carlo runs"):
        params = _sample_params(rng, run_id=i, base_seed=seed)
        sim    = Simulation(params)
        snaps  = sim.run()
        df     = Simulation.to_dataframe(snaps)
        df["run_id"] = i
        all_dfs.append(df)

    combined = pd.concat(all_dfs, ignore_index=True)
    return combined


def _sample_params(rng: np.random.Generator,
                   run_id: int,
                   base_seed: int) -> SimParams:
    """
    Draw one parameter set from the distributions defined in config.MC_PARAMS.

    Each parameter is sampled from Normal(mean, std) and clipped to
    a reasonable range to avoid degenerate simulations.

    PLACEHOLDER: clip bounds are currently hard-coded below.
    Tighten or widen them as empirical data arrives.
    """
    p = config.MC_PARAMS

    alpha            = float(np.clip(rng.normal(p["alpha"]["mean"],
                                                p["alpha"]["std"]), 0.3, 3.0))
    beta             = float(np.clip(rng.normal(p["beta"]["mean"],
                                                p["beta"]["std"]), 0.0, 1.5))
    base_growth_rate = float(np.clip(rng.normal(p["base_growth_rate"]["mean"],
                                                p["base_growth_rate"]["std"]),
                                     0.003, 0.04))
    mfg_entry_pct    = float(np.clip(rng.normal(p["mfg_entry_pct"]["mean"],
                                                p["mfg_entry_pct"]["std"]),
                                     0.04, 0.15))
    shock_prob       = float(np.clip(rng.normal(p["shock_probability"]["mean"],
                                                p["shock_probability"]["std"]),
                                     0.0, 0.20))
    industry_growth  = float(np.clip(rng.normal(p["industry_growth"]["mean"],
                                                p["industry_growth"]["std"]),
                                     0.0, 0.04))
    reshoring        = float(np.clip(rng.normal(p["reshoring_total_m"]["mean"],
                                                p["reshoring_total_m"]["std"]),
                                     0.05, 0.80))

    return SimParams(
        alpha             = alpha,
        beta              = beta,
        base_growth_rate  = base_growth_rate,
        mfg_entry_pct     = mfg_entry_pct,
        shock_probability = shock_prob,
        industry_growth   = industry_growth,
        reshoring_total_m = reshoring,
        seed              = base_seed + run_id,
    )


# =============================================================================
# Analysis helpers
# =============================================================================

def percentile_summary(df: pd.DataFrame,
                        metric: str = "vacuum") -> pd.DataFrame:
    """
    For each (year, tier), compute P5/P50/P95 of the chosen metric
    across all MC runs.

    Returns a DataFrame with columns: year, tier, P5, P50, P95, mean
    """
    grp = df.groupby(["year", "tier"])[metric]
    summary = grp.agg(
        P5   = lambda x: np.percentile(x, 5),
        P25  = lambda x: np.percentile(x, 25),
        P50  = lambda x: np.percentile(x, 50),
        P75  = lambda x: np.percentile(x, 75),
        P95  = lambda x: np.percentile(x, 95),
        mean = "mean",
    ).reset_index()
    return summary


def binding_tier(df: pd.DataFrame) -> pd.DataFrame:
    """
    Identify which tier has the highest vacuum at each timestep (per run).
    Returns: run_id, year, binding_tier, max_vacuum
    """
    idx = df.groupby(["run_id", "year"])["vacuum"].idxmax()
    result = df.loc[idx, ["run_id", "year", "tier", "vacuum"]].copy()
    result = result.rename(columns={"tier": "binding_tier",
                                    "vacuum": "max_vacuum"})
    return result.reset_index(drop=True)
