# =============================================================================
# graduation_engine.py  —  Skill graduation and tube transitions
# =============================================================================
# When a ball's skill exceeds its tube's tier ceiling, it graduates.
# It enters the MarketPool and seeks placement in the next tier up.
# =============================================================================

from __future__ import annotations
import random
from typing import Dict, List, Tuple
import config
from entities import Ball, Tube, MarketPool


GradLog = List[Tuple[Ball, float, float]]  # (ball, from_tier, to_tier)


def process_graduations(tubes_by_tier: Dict[float, Tube],
                        pool: MarketPool,
                        placement_prob: float = config.PLACEMENT_PROBABILITY,
                        rng: random.Random = None) -> GradLog:
    """
    Two-phase process each quarter:

    Phase 1 — Eject:
        Scan every tube. Any ball with skill > tube.tier gets ejected
        into the MarketPool.

    Phase 2 — Place:
        For each ball in the pool, attempt placement in the next tier up.
        Placement succeeds with probability = placement_prob.
        Failed placements stay in pool for next quarter.

    Parameters
    ----------
    tubes_by_tier   : dict mapping tier -> Tube
    pool            : the shared MarketPool
    placement_prob  : quarterly probability of successful job placement
                      PLACEHOLDER: calibrate against BLS JOLTS time-to-fill
    rng             : seeded Random

    Returns
    -------
    GradLog: list of (ball, from_tier, to_tier) for successful placements
    """
    if rng is None:
        rng = random.Random()

    # Advance waiting time for all pool balls
    pool.tick()

    # Phase 1: eject graduated balls from tubes
    _eject_graduated(tubes_by_tier, pool)

    # Phase 2: place pool balls into next tier
    log = _place_from_pool(tubes_by_tier, pool, placement_prob, rng)

    return log


def _eject_graduated(tubes_by_tier: Dict[float, Tube],
                     pool: MarketPool) -> None:
    """
    Remove any ball whose skill exceeds its tube's tier ceiling.
    Ball goes into MarketPool with tube_tier = None.

    Note: we collect removals first to avoid mutating the list mid-iteration.
    """
    for tube in tubes_by_tier.values():
        to_graduate = [b for b in tube.balls if b.skill > tube.tier]
        for ball in to_graduate:
            tube.remove_ball(ball)
            pool.add(ball)


def _place_from_pool(tubes_by_tier: Dict[float, Tube],
                     pool: MarketPool,
                     placement_prob: float,
                     rng: random.Random) -> GradLog:
    """
    Attempt to place each waiting ball into the next tier up.

    Placement logic:
    1. Find target tier = smallest tier > ball.skill
    2. Roll placement_prob — success or stay in pool
    3. On success: add ball to target tube

    PLACEHOLDER: Currently no capacity cap on tubes.
    Future version should enforce a maximum headcount per tube
    derived from real job posting volumes (BLS JOLTS openings by occupation).

    PLACEHOLDER: No underemployment path yet.
    If no tier exists above the ball's skill (i.e., skill >= 1.0),
    the ball should enter an 'expert overflow' pool.
    Currently these balls are silently dropped — log them in future.
    """
    log: GradLog = []
    sorted_tiers = sorted(tubes_by_tier.keys())

    to_remove_from_pool = []

    for ball, wait_time in list(pool.waiting):
        # Find next tier above current skill
        target_tier = next(
            (t for t in sorted_tiers if t > ball.skill), None
        )

        if target_tier is None:
            # Ball has exceeded all tiers — PLACEHOLDER: expert overflow
            to_remove_from_pool.append(ball)
            continue

        # Attempt placement
        if rng.random() < placement_prob:
            from_tier = ball.tube_tier   # None while in pool
            tubes_by_tier[target_tier].add_ball(ball)
            to_remove_from_pool.append(ball)
            log.append((ball, from_tier, target_tier))

    for ball in to_remove_from_pool:
        pool.remove(ball)

    return log
