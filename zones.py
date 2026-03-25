# =============================================================================
# zones.py  --  Snapshot state dataclasses: TubeState, PoolState, SystemState
# =============================================================================
# These are immutable-ish snapshots computed BEFORE the event pass each quarter
# by state_manager.compute_all_states(). Engines read them; they do not mutate
# the live Tube / MarketPool objects.
# =============================================================================

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional


@dataclass
class TubeState:
    """
    Complete per-tube snapshot for one quarter.

    Computed by state_manager._compute_tube_state() before events fire.
    Passed read-only to event_engine and barrier_engine.
    """

    tier            : float
    demand_height   : float
    effective_volume: float
    vacuum          : float
    fill_pct        : float
    headcount       : int

    # ── Beta distribution fitted to ball skill values ─────────────────────────
    # scipy.stats.beta.fit() with floc=0, fscale=1 gives (alpha, beta).
    # PLACEHOLDER: Beta(2,2) is the uninformative default when headcount < 5.
    # Once real per-tier skill survey data is available, replace defaults
    # with empirically fitted priors per tier.
    beta_alpha      : float
    beta_beta       : float

    # ── Skill percentile stats ────────────────────────────────────────────────
    mean_skill      : float
    median_skill    : float
    p10_skill       : float
    p90_skill       : float

    # ── Density bands ─────────────────────────────────────────────────────────
    # Worker count per 0.1 skill band: index 0 = [0.0, 0.1), index 9 = [0.9, 1.0)
    # Used to visualise where within a tier workers are concentrated.
    density_bands   : List[float]

    # ── Skill Earnings Rate (SER) stats ───────────────────────────────────────
    # SER = skill / tube_tenure  (units: skill points per quarter).
    # High SER = fast learner; low SER = stagnating.
    # PLACEHOLDER: SER is a proxy for productivity growth; replace with
    # firm-level productivity-per-worker data when available.
    mean_SER        : float
    median_SER      : float
    stagnant_fraction: float    # fraction of balls with SER < 0.001

    # ── Crowding and dynamics ─────────────────────────────────────────────────
    crowding_index      : float  # = Tube.density (headcount / diameter^2 / 1000)
    lucky_break_lambda  : float  # Poisson rate for 5x growth events this quarter
    death_rate_modifier : float  # multiplier on fatal/serious injury probabilities

    # ── Growth field closure ──────────────────────────────────────────────────
    # Callable: skill (float) -> dskill/dt (float) for one quarter.
    # Captures attractor, crowding factor, and regression slope.
    # Built fresh each quarter in state_manager so it reflects current density.
    # PLACEHOLDER: attractor = tier + 0.1 is a linear heuristic.
    # Calibrate against DOL RAPIDS apprenticeship completion data.
    growth_field    : Callable


@dataclass
class PoolState:
    """
    Snapshot of the MarketPool — workers between tubes awaiting placement.
    Includes both active waiting and injured sub-pool counts.
    """

    total_size              : int     # active waiting only (not injured)
    mean_skill              : float
    mean_SER                : float

    mean_waiting_quarters   : float
    p90_waiting_quarters    : float   # 90th-percentile wait time (quarters)

    # Workers per target tier in the active pool.
    # PLACEHOLDER: used by barrier_engine P_pool factor to model competition.
    # Source: BLS JOLTS applicant-to-opening ratios by occupation would calibrate
    # k_pool_sensitivity in BARRIER_PARAMS.
    density_by_target_tier  : Dict[float, int]

    # Beta distribution fitted to pool skill distribution.
    # Default Beta(2,2) when fewer than 5 active waiting balls.
    beta_alpha              : float
    beta_beta               : float


@dataclass
class SystemState:
    """
    Quarter-level aggregate of the entire labour market system.
    Written by state_manager; extended by Simulation before event pass.
    """

    quarter                     : int
    year                        : float
    total_workforce             : int     # balls in tubes
    total_pool                  : int     # balls in pool (active + injured)
    total_exits_this_quarter    : int     # filled in post-event by Simulation
    system_vacuum               : float   # sum of vacuum across all tubes
    binding_tier                : float   # tier with highest vacuum

    # Injected by Simulation._run_step() after state is returned from manager.
    # Persists across quarters via Simulation._cumulative_exits.
    cumulative_exits_by_reason  : Dict[str, int] = field(default_factory=dict)

    # Populated by Simulation._run_step() based on shock probability roll.
    # event_engine checks this dict; key 'policy' = ICE/enforcement shock.
    # PLACEHOLDER: only 'policy' shock type implemented.
    # Future: add 'recession', 'pandemic', 'supply_chain' shock types with
    # separate tier-weight profiles per shock category.
    shock_active                : Dict[str, bool] = field(default_factory=dict)
