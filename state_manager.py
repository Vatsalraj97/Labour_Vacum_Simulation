# =============================================================================
# state_manager.py  --  Compute TubeState, PoolState, SystemState each quarter
# =============================================================================
# Called once per quarter BEFORE the event pass.
# Reads Tube / MarketPool objects and returns immutable snapshots (zones.py).
# Does NOT modify any live simulation objects.
# =============================================================================

from __future__ import annotations
import numpy as np
from scipy.stats import beta as scipy_beta
from typing import Dict, Tuple

import config
from entities import Tube, MarketPool
from zones import TubeState, PoolState, SystemState


def compute_all_states(
    tubes_by_tier : Dict[float, Tube],
    pool          : MarketPool,
    quarter       : int,
) -> Tuple[Dict[float, TubeState], PoolState, SystemState]:
    """
    Build full state snapshot for the current quarter.

    Returns
    -------
    tube_states  : dict mapping tier -> TubeState
    pool_state   : PoolState
    system_state : SystemState (shock_active / cumulative_exits injected later
                   by Simulation._run_step before passing to event_engine)
    """
    tube_states: Dict[float, TubeState] = {
        tier: _compute_tube_state(tier, tube)
        for tier, tube in tubes_by_tier.items()
    }
    pool_state   = _compute_pool_state(pool)
    system_state = _compute_system_state(
        tubes_by_tier, pool, tube_states, pool_state, quarter
    )
    return tube_states, pool_state, system_state


# =============================================================================
# Per-tube snapshot
# =============================================================================

def _compute_tube_state(tier: float, tube: Tube) -> TubeState:
    balls = tube.balls
    n     = len(balls)

    # ── Beta fit ──────────────────────────────────────────────────────────────
    if n >= 5:
        skills_arr  = np.array([b.skill for b in balls], dtype=float)
        skills_fit  = np.clip(skills_arr, 0.001, 0.999)
        try:
            # floc=0, fscale=1 constrains Beta to the unit interval
            a, b_p, _, _ = scipy_beta.fit(skills_fit, floc=0, fscale=1)
        except Exception:
            a, b_p = 2.0, 2.0   # uninformative Beta(2,2) fallback
    elif n > 0:
        skills_arr = np.array([b.skill for b in balls], dtype=float)
        a, b_p     = 2.0, 2.0
    else:
        skills_arr = np.array([], dtype=float)
        a, b_p     = 2.0, 2.0

    # ── Skill percentiles ─────────────────────────────────────────────────────
    if n > 0:
        mean_skill   = float(np.mean(skills_arr))
        median_skill = float(np.median(skills_arr))
        p10_skill    = float(np.percentile(skills_arr, 10))
        p90_skill    = float(np.percentile(skills_arr, 90))
        density_bands = [
            float(np.sum((skills_arr >= i * 0.1) & (skills_arr < (i + 1) * 0.1)))
            for i in range(10)
        ]
        sers          = np.array([b.SER for b in balls], dtype=float)
        mean_SER      = float(np.mean(sers))
        median_SER    = float(np.median(sers))
        # PLACEHOLDER: stagnant threshold 0.001 SER/quarter.
        # Replace with empirical SER distribution lower bound.
        stagnant_fraction = float(np.mean(sers < 0.001))
    else:
        mean_skill = median_skill = p10_skill = p90_skill = 0.0
        density_bands = [0.0] * 10
        mean_SER = median_SER = stagnant_fraction = 0.0

    # ── Crowding and derived dynamics ─────────────────────────────────────────
    crowding_index  = tube.density  # headcount / (diameter^2 * 1000)
    beta_crowd      = config.BARRIER_PARAMS['beta_crowd']
    crowding_factor = 1.0 / (1.0 + beta_crowd * crowding_index)

    # PLACEHOLDER: lucky_break_lambda = 0.05 * (1 - crowding/2), floor 0.005.
    # Calibrate against NAM productivity survey variance data.
    lucky_break_lambda = 0.05 * max(0.1, 1.0 - crowding_index / 2.0)

    # PLACEHOLDER: death_rate_modifier scales with how far mean skill is from
    # tier ceiling. Workers operating below their tier ceiling make more errors.
    # Source: BLS Survey of Occupational Injuries and Illnesses (SOII) by skill.
    death_rate_modifier = (
        1.0 + (1.0 - mean_skill / tier) * 0.5
        if tier > 0 else 1.0
    )

    # ── Growth field closure ──────────────────────────────────────────────────
    alpha     = config.ALPHA
    attractor = tier + 0.1  # PLACEHOLDER: skill "sweet spot" just above tier

    def growth_field(
        skill,
        _a=alpha, _att=attractor, _tier=tier, _cf=crowding_factor,
    ) -> float:
        """
        dskill/dt for one ball in one quarter.

        skill <= attractor : grow towards attractor (proximity-weighted).
        skill >  attractor : very slow regression back towards attractor.

        PLACEHOLDER: attractor = tier + 0.1 is a linear heuristic.
        Replace with empirically fitted per-tier growth curves from
        DOL RAPIDS apprenticeship completion rate data.
        """
        if _att <= 0:
            return 0.0
        if skill <= _att:
            proximity = max(skill / _att, 0.01)
            return config.BASE_GROWTH_RATE * (proximity ** _a) * _tier * _cf
        else:
            overshoot = min((skill - _att) * 3.0, 1.0)
            return -config.BASE_GROWTH_RATE * config.REGRESSION_RATE * overshoot

    return TubeState(
        tier=tier,
        demand_height=tube.demand_height,
        effective_volume=tube.effective_volume,
        vacuum=tube.vacuum,
        fill_pct=tube.fill_pct,
        headcount=n,
        beta_alpha=a,
        beta_beta=b_p,
        mean_skill=mean_skill,
        median_skill=median_skill,
        p10_skill=p10_skill,
        p90_skill=p90_skill,
        density_bands=density_bands,
        mean_SER=mean_SER,
        median_SER=median_SER,
        stagnant_fraction=stagnant_fraction,
        crowding_index=crowding_index,
        lucky_break_lambda=lucky_break_lambda,
        death_rate_modifier=death_rate_modifier,
        growth_field=growth_field,
    )


# =============================================================================
# Pool snapshot
# =============================================================================

def _compute_pool_state(pool: MarketPool) -> PoolState:
    waiting = pool.waiting   # List[(ball, quarters_waiting)]
    n       = len(waiting)

    if n > 0:
        skills  = np.array([b.skill for b, _ in waiting], dtype=float)
        wait_qs = np.array([q       for _, q in waiting], dtype=float)
        sers    = np.array([b.SER   for b, _ in waiting], dtype=float)

        mean_skill            = float(np.mean(skills))
        mean_SER              = float(np.mean(sers))
        mean_waiting_quarters = float(np.mean(wait_qs))
        p90_waiting_quarters  = float(np.percentile(wait_qs, 90))

        if n >= 5:
            skills_fit = np.clip(skills, 0.001, 0.999)
            try:
                a, b_p, _, _ = scipy_beta.fit(skills_fit, floc=0, fscale=1)
            except Exception:
                a, b_p = 2.0, 2.0
        else:
            a, b_p = 2.0, 2.0

        density_by_target_tier: Dict[float, int] = {}
        for ball, _ in waiting:
            t = ball.target_tier
            if t is not None:
                density_by_target_tier[t] = density_by_target_tier.get(t, 0) + 1
    else:
        mean_skill = mean_SER = mean_waiting_quarters = p90_waiting_quarters = 0.0
        a, b_p = 2.0, 2.0
        density_by_target_tier = {}

    return PoolState(
        total_size=n,
        mean_skill=mean_skill,
        mean_SER=mean_SER,
        mean_waiting_quarters=mean_waiting_quarters,
        p90_waiting_quarters=p90_waiting_quarters,
        density_by_target_tier=density_by_target_tier,
        beta_alpha=a,
        beta_beta=b_p,
    )


# =============================================================================
# System aggregate
# =============================================================================

def _compute_system_state(
    tubes_by_tier : Dict[float, Tube],
    pool          : MarketPool,
    tube_states   : Dict[float, TubeState],
    pool_state    : PoolState,
    quarter       : int,
) -> SystemState:
    year            = config.START_YEAR + quarter / config.QUARTERS_PER_YEAR
    total_workforce = sum(ts.headcount for ts in tube_states.values())
    total_pool      = pool_state.total_size + len(pool.injured_waiting)
    system_vacuum   = sum(ts.vacuum for ts in tube_states.values())

    if tube_states:
        binding_ts  = max(tube_states.values(), key=lambda ts: ts.vacuum)
        binding_tier = binding_ts.tier
    else:
        binding_tier = 0.0

    return SystemState(
        quarter=quarter,
        year=round(year, 4),
        total_workforce=total_workforce,
        total_pool=total_pool,
        total_exits_this_quarter=0,
        system_vacuum=system_vacuum,
        binding_tier=binding_tier,
    )
