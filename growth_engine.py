# =============================================================================
# growth_engine.py  --  Nonlinear skill growth for balls inside tubes
# =============================================================================
# Formula:
#   dskill = BASE_GROWTH_RATE
#            * (skill / tube_tier) ^ alpha       <- proximity to ceiling
#            * 1 / (1 + beta * density)          <- crowding penalty
#            * tube_tier                         <- higher tiers grow faster
#
# Parameters alpha and beta are Monte Carlo variables (see config.py).
# =============================================================================

from __future__ import annotations
from typing import List
import config
from entities import Ball, Tube


def grow_all(tubes: List[Tube],
             alpha: float = config.ALPHA,
             beta:  float = config.BETA) -> None:
    """
    Apply one quarter of skill growth to every ball in every tube.
    Modifies ball.skill in-place.

    Parameters
    ----------
    tubes : all active Tube objects
    alpha : growth convexity (higher = faster only near ceiling)
    beta  : crowding sensitivity (higher = density hurts more)
    """
    for tube in tubes:
        if not tube.balls:
            continue
        density = tube.density
        for ball in tube.balls:
            delta = _growth_delta(ball.skill, tube.tier, density, alpha, beta)
            ball.skill = min(ball.skill + delta, 0.999)   # cap just below 1.0
            ball.tenure      += 1
            ball.tube_tenure += 1


def _growth_delta(skill:     float,
                  tier:      float,
                  density:   float,
                  alpha:     float,
                  beta:      float) -> float:
    """
    Compute skill gain for one ball in one quarter.

    Behaviour:
    - A ball of skill 0.45 in tube 0.5 (proximity = 0.90) grows FAST
    - A ball of skill 0.05 in tube 0.5 (proximity = 0.10) grows SLOW
    - A crowded tube (density > 1) slows everyone down
    - Higher-tier tubes produce faster absolute growth (x tier multiplier)

    PLACEHOLDER: The formula shape is intuitive but not empirically calibrated.
    To calibrate: fit against apprenticeship completion rate data from
    DOL RAPIDS database or NAM workforce survey longitudinal data.
    """
    if tier == 0:
        return 0.0

    proximity     = skill / tier                          # 0.0 -> 1.0
    proximity     = max(proximity, 0.01)                  # avoid zero^alpha
    crowding_pen  = 1.0 / (1.0 + beta * density)
    tier_boost    = tier                                  # higher tiers faster

    delta = (config.BASE_GROWTH_RATE
             * (proximity ** alpha)
             * crowding_pen
             * tier_boost)

    return delta


# =============================================================================
# Utility: show growth rate table (useful for calibration)
# =============================================================================
def print_growth_table():
    """
    Print a table of quarterly growth rates for representative skill / tier
    combinations. Run this to sanity-check the alpha / beta settings.
    """
    print(f"\nGrowth rate table  (alpha={config.ALPHA}, beta={config.BETA})")
    print(f"{'Tube':>6}  {'Skill':>6}  {'Proximity':>10}  "
          f"{'dSkill/Q':>10}  {'Yrs to graduate':>16}")
    print("-" * 58)
    examples = [
        (0.3, 0.05), (0.3, 0.20), (0.3, 0.28),
        (0.5, 0.10), (0.5, 0.35), (0.5, 0.48),
        (0.8, 0.40), (0.8, 0.65), (0.8, 0.78),
        (1.0, 0.60), (1.0, 0.85), (1.0, 0.98),
    ]
    for tier, skill in examples:
        delta = _growth_delta(skill, tier, density=0.5,
                              alpha=config.ALPHA, beta=config.BETA)
        gap   = tier - skill
        qtrs  = gap / delta if delta > 0 else float("inf")
        yrs   = qtrs / 4
        print(f"{tier:>6.1f}  {skill:>6.2f}  "
              f"{skill/tier:>10.2f}  {delta:>10.5f}  {yrs:>16.1f}")


if __name__ == "__main__":
    print_growth_table()
