# =============================================================================
# inflow_engine.py  —  New worker entrants from the population pipeline
# =============================================================================
# Inflow is derived entirely from demographics — NOT from demand.
# The census cohort matures into the workforce; a fixed % enters manufacturing.
# New entrants always start in low-skill tubes (0.1 – 0.4).
# =============================================================================

from __future__ import annotations
import random
import numpy as np
from typing import Dict, List
import config
from entities import Ball, Tube


def add_quarterly_entrants(tubes_by_tier: Dict[float, Tube],
                           mfg_entry_pct: float = config.MFG_ENTRY_PCT,
                           rng: random.Random = None,
                           workforce_scale: int = 1) -> List[Ball]:
    """
    Create new Ball objects for this quarter's manufacturing entrants
    and place them into appropriate low-skill tubes.

    Parameters
    ----------
    tubes_by_tier : dict mapping tier -> Tube
    mfg_entry_pct : % of working-age cohort entering manufacturing
                    (Monte Carlo variable)
    rng           : seeded Random for reproducibility

    Returns
    -------
    List of newly created Ball objects (already placed in tubes)

    PLACEHOLDER: quarterly_entrants calculation uses a flat annual cohort.
    Real implementation should use Census Bureau population projections
    by birth year (ACS Table B01001) — cohort size varies by year.
    """
    if rng is None:
        rng = random.Random()

    # Quarterly entrant count
    # PLACEHOLDER: ANNUAL_WORKING_AGE_COHORT in config.py
    quarterly_entrants = int(
        config.ANNUAL_WORKING_AGE_COHORT * mfg_entry_pct / config.QUARTERS_PER_YEAR
        / workforce_scale
    )

    new_balls = []
    for _ in range(quarterly_entrants):
        ball = _create_entrant(rng)
        target_tube = _assign_tube(ball.skill, tubes_by_tier)
        if target_tube is not None:
            target_tube.add_ball(ball)
            new_balls.append(ball)

    return new_balls


def _create_entrant(rng: random.Random) -> Ball:
    """
    Spawn a new Ball with a skill level drawn from the entrant distribution.

    PLACEHOLDER: skill distribution parameters in config.py
    (ENTRANT_SKILL_MEAN, ENTRANT_SKILL_STD, ENTRANT_SKILL_MIN/MAX).

    Age quartile is always 1 (young entrant).
    Immigrant flag is a PLACEHOLDER — currently set randomly at 8.5% rate
    matching the approximate manufacturing immigrant share (BLS CPS).
    Ideally this would be drawn from a census-derived demographic model.
    """
    skill = np.random.normal(config.ENTRANT_SKILL_MEAN,
                             config.ENTRANT_SKILL_STD)
    skill = float(np.clip(skill, config.ENTRANT_SKILL_MIN,
                                 config.ENTRANT_SKILL_MAX))

    # PLACEHOLDER: immigrant flag
    # Source: BLS CPS Table 14, nativity x manufacturing
    is_immigrant = rng.random() < 0.102   # ~10.2% manufacturing immigrant share

    return Ball(
        skill        = skill,
        tube_tier    = None,    # will be set by target_tube.add_ball()
        tenure       = 0,
        tube_tenure  = 0,
        age_quartile = 1,
        immigrant    = is_immigrant,
    )


def _assign_tube(skill: float,
                 tubes_by_tier: Dict[float, Tube]) -> Tube | None:
    """
    Find the most appropriate tube for a new entrant.

    Rule: place in the highest tier where tier >= skill AND tier <= 0.4
    (new entrants never start above tier 0.4 — no raw entrant enters
    a specialist or expert tube directly).

    If no valid tube exists, the entrant is lost (not modelled — placeholder).
    PLACEHOLDER: 'lost entrant' path should feed a separate pool
    representing workers who entered the labour market but couldn't
    find a manufacturing job — relevant for policy analysis.
    """
    valid_tiers = [
        tier for tier in sorted(tubes_by_tier.keys())
        if tier >= skill and tier <= 0.4
    ]
    if not valid_tiers:
        return None
    target_tier = valid_tiers[0]   # lowest valid tier (most appropriate fit)
    return tubes_by_tier[target_tier]
