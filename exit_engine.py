# =============================================================================
# exit_engine.py  —  All outflow mechanics (voluntary, retirement, shock)
# =============================================================================

from __future__ import annotations
import random
from typing import List, Tuple
import config
from entities import Ball, Tube


ExitLog = List[Tuple[Ball, str]]   # (ball, reason)


def process_exits(tubes: List[Tube],
                  shock_probability: float = config.SHOCK_PROBABILITY,
                  shock_removal_rate: float = config.SHOCK_REMOVAL_RATE,
                  rng: random.Random = None) -> ExitLog:
    """
    Process all three exit types for one quarter.
    Returns a log of (ball, reason) for every worker removed.

    Order: voluntary -> retirement -> shock (shock is rare but batch)

    Parameters
    ----------
    tubes             : all active Tube objects
    shock_probability : probability a shock event occurs this quarter
    shock_removal_rate: fraction removed from exposed tiers if shock fires
    rng               : optional seeded Random instance for reproducibility
    """
    if rng is None:
        rng = random.Random()

    log: ExitLog = []

    # ── 1. Voluntary quits ────────────────────────────────────────────────────
    log += _voluntary_exits(tubes, rng)

    # ── 2. Retirements ────────────────────────────────────────────────────────
    log += _retirement_exits(tubes, rng)

    # ── 3. Policy shock (ICE raids / layoffs) ─────────────────────────────────
    if rng.random() < shock_probability:
        log += _shock_exits(tubes, shock_removal_rate, rng)

    return log


# =============================================================================
# Voluntary exits
# =============================================================================
def _voluntary_exits(tubes: List[Tube], rng: random.Random) -> ExitLog:
    """
    Each ball has a quarterly quit probability determined by its tube tier.
    Lower tiers have higher quit rates (more churn, less investment).

    PLACEHOLDER: QUIT_RATE_BY_TIER in config.py.
    Source to calibrate: BLS JOLTS quit rates by industry x occupation.
    """
    log = []
    for tube in tubes:
        rate = config.QUIT_RATE_BY_TIER.get(tube.tier, 0.02)
        to_remove = [b for b in tube.balls if rng.random() < rate]
        for ball in to_remove:
            tube.remove_ball(ball)
            log.append((ball, "voluntary_quit"))
    return log


# =============================================================================
# Retirement exits
# =============================================================================
def _retirement_exits(tubes: List[Tube], rng: random.Random) -> ExitLog:
    """
    Once a ball's tenure exceeds RETIREMENT_TENURE_THRESHOLD, it faces
    an escalating retirement probability each quarter.

    retire_prob = BASE_RATE * (1 + excess_tenure / threshold)

    This means someone with 20 years tenure retires at roughly 2x the
    base rate of someone who just crossed the threshold.

    PLACEHOLDER: threshold and base rate in config.py.
    Source: BLS CPS retirement age data; SIPP longitudinal surveys.
    """
    log = []
    for tube in tubes:
        to_remove = []
        for ball in tube.balls:
            if ball.is_near_retirement:
                excess = ball.tenure - config.RETIREMENT_TENURE_THRESHOLD
                prob   = config.RETIREMENT_BASE_RATE * (
                    1.0 + excess / config.RETIREMENT_TENURE_THRESHOLD
                )
                prob   = min(prob, 0.35)   # cap at 35%/quarter
                if rng.random() < prob:
                    to_remove.append(ball)
        for ball in to_remove:
            tube.remove_ball(ball)
            log.append((ball, "retirement"))
    return log


# =============================================================================
# Shock exits (ICE raids, economic downturns, sudden layoffs)
# =============================================================================
def _shock_exits(tubes: List[Tube],
                 removal_rate: float,
                 rng: random.Random) -> ExitLog:
    """
    A shock event removes a fraction of workers, weighted by tier exposure.
    Lower tiers (higher immigrant share, more vulnerable) are hit harder.

    PLACEHOLDER: SHOCK_TIER_WEIGHTS in config.py.
    Source: NBER immigration enforcement studies; BLS industry layoff data.

    Note: this is the most uncertain parameter in the model.
    The shock_probability itself is a Monte Carlo variable.
    """
    log = []
    for tube in tubes:
        weight = config.SHOCK_TIER_WEIGHTS.get(tube.tier, 1.0)
        effective_rate = min(removal_rate * weight, 0.5)   # cap at 50%
        to_remove = [b for b in tube.balls if rng.random() < effective_rate]
        for ball in to_remove:
            tube.remove_ball(ball)
            log.append((ball, "shock"))
    return log


# =============================================================================
# Summary helper
# =============================================================================
def exit_summary(log: ExitLog) -> dict:
    """Count exits by reason."""
    summary = {"voluntary_quit": 0, "retirement": 0, "shock": 0}
    for _, reason in log:
        summary[reason] = summary.get(reason, 0) + 1
    return summary
