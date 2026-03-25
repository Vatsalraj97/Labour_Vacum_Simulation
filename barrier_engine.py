# =============================================================================
# barrier_engine.py  --  Quarterly placement probability for pool balls
# =============================================================================
#
# P_barrier = P_accept * P_train_yield * P_pool * P_crowd * P_experience
#             * (1 + epsilon)
#
# All multiplicative factors in [0,1]. epsilon is a small additive luck term.
# Returns a probability in [0, 1].
#
# PLACEHOLDER: Every formula and constant in this file is a calibration target.
# Priority data sources:
#   P_accept      -- BLS JOLTS skill-gap × time-to-fill cross-tabs
#   P_train_yield -- Manufacturing Institute / NAM training cost surveys
#   P_pool        -- BLS JOLTS applicant-to-opening ratios by occupation
#   P_crowd       -- BLS OES headcount vs vacancy by occupation code
#   P_experience  -- Longitudinal employer-employee matched data (LEHD)
# =============================================================================

from __future__ import annotations
import math
from typing import Optional

import config
from entities import Ball, Tube
from zones import TubeState, PoolState


def compute_barrier(
    ball        : Ball,
    tube        : Tube,
    tube_state  : Optional[TubeState],
    pool_state  : PoolState,
    params      : dict,
) -> float:
    """
    Compute the quarterly probability that 'ball' is placed into 'tube'.

    Parameters
    ----------
    ball        : the worker seeking placement
    tube        : the target tube (next tier up)
    tube_state  : TubeState snapshot of the target tube; None = use defaults
    pool_state  : PoolState snapshot (for competition density)
    params      : config.BARRIER_PARAMS dict

    Returns
    -------
    float in [0.0, 1.0]
    """
    p            = params
    target_tier  = tube.tier
    raw_gap      = target_tier - ball.skill     # positive = under-skilled
    skill_gap    = max(raw_gap, 0.0)            # one-sided gap for cost calcs

    # ── Hard caps ─────────────────────────────────────────────────────────────
    # Absolute floor: skill too low for any placement
    if ball.skill < p['hard_cap_skill']:
        return p['hard_cap_p']

    # Cannot leap more than max_upward_gap into a high tier in one move
    if target_tier > p['hard_cap_tube'] and skill_gap > p['max_upward_gap']:
        return p['hard_cap_p']

    # ── P_accept: asymmetric Gaussian on raw skill gap ────────────────────────
    # Underqualified (raw_gap > 0): narrow right-tail sigma
    # Overqualified  (raw_gap < 0): wide  left-tail sigma (employers wary)
    # PLACEHOLDER: sigma values from config; calibrate with JOLTS hire-rate data.
    if raw_gap >= 0:
        sigma = p['sigma_right_base']
    else:
        sigma = p['sigma_right_base'] * p['sigma_left_mult']

    P_accept = math.exp(-(raw_gap ** 2) / (2.0 * sigma ** 2 + 1e-12))

    # Extra flunk penalty for large positive gaps beyond one sigma
    if raw_gap > p['sigma_right_base']:
        overshoot = raw_gap - p['sigma_right_base']
        P_accept *= math.exp(-p['lambda_flunk'] * overshoot)

    # ── P_train_yield: can employer afford to bridge the gap? ─────────────────
    # Training cost grows exponentially with skill gap (cost_exp_k in params).
    # If cost exceeds employer_max_cost the employer will not hire.
    # PLACEHOLDER: cost_exp_k = 6.0 derived from manufacturing training surveys.
    #   Replace with sector-level training cost data from BLS Employer Costs
    #   for Employee Compensation (ECEC) supplementary tables.
    age_years     = ball.age / 4.0   # computed once; used in yield and retirement check
    training_cost = (
        p['training_base_cost']
        * math.exp(p['cost_exp_k'] * max(skill_gap - 0.05, 0.0))
    )

    if training_cost > p['employer_max_cost']:
        P_train_yield = 0.0
    else:
        # Older workers absorb training more slowly (age_yield_scale penalty)
        # PLACEHOLDER: age_yield_scale = 0.04 per year above 25.
        #   Source: Acemoglu & Pischke (1999) on employer-sponsored training.
        age_discount  = max(0.0, 1.0 - p['age_yield_scale'] * max(0.0, age_years - 25.0))
        P_train_yield = p['yield_base'] * age_discount

    # Near-retirement penalty: employer ROI horizon too short
    years_remaining = max(0.0, float(p['retire_age']) - age_years)
    if years_remaining < p['min_years_to_work']:
        P_train_yield *= 0.02  # effectively blocks placement near retirement

    # ── P_pool: competition from other candidates targeting the same tier ──────
    # PLACEHOLDER: k_pool_sensitivity = 10.
    #   Calibrate using BLS JOLTS applicant-per-opening ratios by occupation.
    n_competing   = pool_state.density_by_target_tier.get(target_tier, 0)
    pool_total    = max(pool_state.total_size, 1)
    compete_frac  = n_competing / pool_total
    raw_pool      = 1.0 / (1.0 + p['k_pool_sensitivity'] * compete_frac)
    P_pool        = max(raw_pool, p['pool_floor'])

    # Decay: employers prefer recently-unemployed candidates
    # Each quarter beyond 4 reduces P_pool by pool_decay_rate.
    P_pool *= p['pool_decay_rate'] ** max(0, ball.pool_tenure - 4)

    # ── P_crowd: target tube congestion → fewer open slots ────────────────────
    crowding = tube_state.crowding_index if tube_state is not None else 0.0
    P_crowd  = 1.0 / (1.0 + p['beta_crowd'] * crowding)

    # ── P_experience: SER-based signal of learning velocity ───────────────────
    # PLACEHOLDER: linear scale with SER.
    #   Replace with logistic regression fit to LEHD matched employer data.
    P_experience = min(1.0, 0.4 + ball.SER * 8.0)

    # ── Luck term ─────────────────────────────────────────────────────────────
    epsilon = p['luck_p']

    # ── Final probability ─────────────────────────────────────────────────────
    P_barrier = (
        P_accept
        * P_train_yield
        * P_pool
        * P_crowd
        * P_experience
        * (1.0 + epsilon)
    )

    return max(0.0, min(1.0, P_barrier))
