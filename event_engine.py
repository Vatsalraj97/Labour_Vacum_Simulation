# =============================================================================
# event_engine.py  --  Priority-ordered event processing for all agents
# =============================================================================
#
# Priority chain for tube balls (events 1-12):
#   1  fatal_injury          exits permanently
#   2  shock_removal         exits permanently
#   3  retirement            exits permanently
#   4  serious_injury        exits to injured sub-pool; skill reduced
#   5  minor_injury          stays in tube; skill reduced (NOT an exit)
#   6  graduation            exits to MarketPool; target_tier = next tier up
#   7  management_graduation exits permanently to management pool
#   8  lucky_break           stays; growth_multiplier x5 this quarter (NOT exit)
#   9  skill_growth          stays; applies growth_field * multiplier
#  10  frustration_quit      exits permanently (high-skill stagnators)
#  11  voluntary_quit        exits to MarketPool; no target_tier change
#  12  career_change         exits permanently to non-manufacturing
#
# Pool balls (events 13-15):
#  13  placement             barrier_engine determines placement probability
#  14  skill_regression      slow decay while unemployed
#  15  discouragement        long-term unemployed exit permanently
#
# Population pipeline (event 16):
#  16  entry                 new entrants placed into low-skill tubes
#
# Rule: each ball fires AT MOST ONE exit-event per quarter.
#       Non-exit events (5 minor_injury, 8 lucky_break, 9 skill_growth)
#       apply within the chain independently of exit status.
# =============================================================================

from __future__ import annotations
import math
import random
import numpy as np
from typing import Any, Dict, List, Optional, Tuple

import config
import barrier_engine
from entities import Ball, Tube, MarketPool
from zones import TubeState, PoolState, SystemState

# Legacy module imports kept for compatibility (logic inlined below)
from growth_engine  import _growth_delta        # noqa: F401
from exit_engine    import exit_summary         # noqa: F401
from inflow_engine  import _assign_tube         # noqa: F401

# EventLog entry: dict snapshot of ball state at the moment the event fires.
# Keys: quarter, year, ball_id, event_type, tier, skill, age_qtrs,
#        tenure, tube_tenure, immigrant
EventLog = List[Dict[str, Any]]


def _event_record(
    ball  : Ball,
    tier  : Optional[float],
    reason: str,
    step  : int,
    year  : float,
) -> Dict[str, Any]:
    """Capture ball state at the instant an event fires."""
    return {
        'quarter'    : step,
        'year'       : round(year, 2),
        'ball_id'    : ball.ball_id,
        'event_type' : reason,
        'tier'       : tier,
        'skill'      : round(ball.skill, 4),
        'age_qtrs'   : ball.age,
        'tenure'     : ball.tenure,
        'tube_tenure': ball.tube_tenure,
        'immigrant'  : ball.immigrant,
    }


# =============================================================================
# Public entry point
# =============================================================================

def process_all_events(
    tubes_by_tier : Dict[float, Tube],
    pool          : MarketPool,
    tube_states   : Dict[float, TubeState],
    pool_state    : PoolState,
    system_state  : SystemState,
    params,                                # SimParams duck-typed (no circular import)
    rng           : random.Random,
    step          : int   = 0,
    year          : float = 0.0,
) -> EventLog:
    """
    Run the full priority-ordered event chain for all agents in one quarter.
    Modifies tube.balls, pool.waiting, and pool.injured_waiting in-place.
    Returns EventLog for snapshot accounting.
    """
    log: EventLog = []
    sorted_tiers  = sorted(tubes_by_tier.keys())

    # ── Events 1-12: tube balls ───────────────────────────────────────────────
    for tier in sorted_tiers:
        tube = tubes_by_tier[tier]
        ts   = tube_states[tier]

        perm_removed : List[Ball]              = []
        to_pool      : List[Ball]              = []
        to_injured   : List[Tuple[Ball, int]]  = []

        for ball in list(tube.balls):   # snapshot list before mutations
            outcome = _process_tube_ball(
                ball, tier, ts, sorted_tiers, system_state, params, rng, log, step, year
            )
            if outcome == 'removed':
                perm_removed.append(ball)
            elif outcome == 'to_pool':
                to_pool.append(ball)
            elif outcome == 'to_injured':
                to_injured.append((ball, config.INJURY_RECOVERY_Q.get(tier, 2)))
            # 'stayed' -> nothing to do

        # Apply moves after iteration to avoid list mutation during loop
        for ball in perm_removed:
            if ball in tube.balls:
                tube.remove_ball(ball)

        for ball in to_pool:
            if ball in tube.balls:
                tube.remove_ball(ball)
                ball.pool_tenure = 0
                pool.add(ball)

        for ball, rec_q in to_injured:
            if ball in tube.balls:
                tube.remove_ball(ball)
                ball.pool_tenure = 0
                pool.injured_waiting.append((ball, rec_q))

    # ── Events 13-15: pool balls ──────────────────────────────────────────────
    pool.tick()   # advance all waiting counters

    placements     : List[Tuple[Ball, float]] = []
    discouragements: List[Ball]               = []

    for ball, wait_time in list(pool.waiting):
        ball.pool_tenure = wait_time   # sync field with tuple counter
        ball.age        += 1

        # 13. Placement attempt via barrier_engine ────────────────────────────
        tgt = ball.target_tier if ball.target_tier is not None else \
              next((t for t in sorted_tiers if t > ball.skill), None)

        placed = False
        if tgt is not None and tgt in tubes_by_tier:
            tgt_tube  = tubes_by_tier[tgt]
            tgt_state = tube_states.get(tgt)
            p_place   = barrier_engine.compute_barrier(
                ball, tgt_tube, tgt_state, pool_state, config.BARRIER_PARAMS
            )
            if rng.random() < p_place:
                placements.append((ball, tgt))
                log.append(_event_record(ball, tgt, 'placement', step, year))
                placed = True

        if not placed:
            # 14. Skill regression — very slow decay while between jobs
            # PLACEHOLDER: pool_decay_rate = 0.97 per quarter (~12%/yr).
            # Source: Kambourov & Manovskii (2009) on occupational mobility
            # skill depreciation rates.
            ball.skill = max(0.001, ball.skill * config.BARRIER_PARAMS['pool_decay_rate'])

            # 15. Discouragement exit — grows with pool tenure beyond 12 qtrs
            # PLACEHOLDER: 0.005 base rate per quarter after 12 quarters.
            disc_p = 0.005 * max(0.0, (ball.pool_tenure - 12) / 12.0)
            if disc_p > 0.0 and rng.random() < disc_p:
                discouragements.append(ball)
                log.append(_event_record(ball, None, 'discouragement', step, year))

    # Apply pool moves
    for ball, tgt in placements:
        pool.remove(ball)
        ball.target_tier = None
        ball.pool_tenure = 0
        tubes_by_tier[tgt].add_ball(ball)

    for ball in discouragements:
        pool.remove(ball)

    # ── Injured sub-pool ──────────────────────────────────────────────────────
    graduating_injured : List[Ball]              = []
    updated_injured    : List[Tuple[Ball, int]]  = []

    for ball, rec_q in pool.injured_waiting:
        ball.age   += 1
        ball.skill  = max(0.001, ball.skill * 0.9985)  # slow decay during recovery
        if rec_q <= 1:
            graduating_injured.append(ball)
        else:
            updated_injured.append((ball, rec_q - 1))

    pool.injured_waiting = updated_injured
    for ball in graduating_injured:
        pool.add(ball)   # return to active waiting list

    # ── Event 16: new entrants ────────────────────────────────────────────────
    _entry_events(tubes_by_tier, sorted_tiers, params, rng, log, step, year)

    return log


# =============================================================================
# Tube-ball priority chain (events 1-12)
# =============================================================================

def _process_tube_ball(
    ball         : Ball,
    tier         : float,
    ts           : TubeState,
    sorted_tiers : List[float],
    system_state : SystemState,
    params,
    rng          : random.Random,
    log          : EventLog,
    step         : int   = 0,
    year         : float = 0.0,
) -> str:
    """
    Process events 1-12 for one ball. Returns movement outcome:
        'removed'   -- permanently exits simulation
        'to_pool'   -- moves to MarketPool.waiting
        'to_injured'-- moves to MarketPool.injured_waiting
        'stayed'    -- remains in tube
    """
    growth_multiplier = 1.0

    # 1. Fatal injury ──────────────────────────────────────────────────────────
    # PLACEHOLDER: FATAL_INJURY_RATE values from BLS CFOI (Census of Fatal
    # Occupational Injuries). death_rate_modifier higher when workers are
    # below their tier ceiling (operating out of depth).
    fatal_p = config.FATAL_INJURY_RATE.get(tier, 0.0) * ts.death_rate_modifier
    if rng.random() < fatal_p:
        log.append(_event_record(ball, tier, 'fatal_injury', step, year))
        return 'removed'

    # 2. Shock removal ─────────────────────────────────────────────────────────
    # Fires only if Simulation flagged a shock this quarter in system_state.
    if system_state.shock_active:
        weight     = config.SHOCK_TIER_WEIGHTS.get(tier, 1.0)
        shock_rate = min(params.shock_removal_rate * weight, 0.5)
        if rng.random() < shock_rate:
            log.append(_event_record(ball, tier, 'shock_removal', step, year))
            return 'removed'

    # 3. Retirement ────────────────────────────────────────────────────────────
    # PLACEHOLDER: RETIREMENT_TENURE_THRESHOLD = 28 quarters (7 years) matches
    # approximate manufacturing mid-career transition point.
    # Escalating probability once threshold crossed.
    if ball.is_near_retirement:
        excess   = ball.tenure - config.RETIREMENT_TENURE_THRESHOLD
        retire_p = config.RETIREMENT_BASE_RATE * (
            1.0 + excess / max(config.RETIREMENT_TENURE_THRESHOLD, 1)
        )
        retire_p = min(retire_p, 0.35)
        if rng.random() < retire_p:
            log.append(_event_record(ball, tier, 'retirement', step, year))
            return 'removed'

    # 4. Serious injury (exits to injured sub-pool) ────────────────────────────
    # Ball returns to active pool after INJURY_RECOVERY_Q[tier] quarters.
    # Skill reduced immediately by full INJURY_SKILL_PENALTY.
    # PLACEHOLDER: SERIOUS_INJURY_RATE from BLS SOII days-away-from-work cases.
    serious_p = config.SERIOUS_INJURY_RATE.get(tier, 0.0)
    if rng.random() < serious_p:
        penalty    = config.INJURY_SKILL_PENALTY.get(tier, 0.0)
        ball.skill = max(0.001, ball.skill - penalty)
        log.append(_event_record(ball, tier, 'serious_injury', step, year))
        return 'to_injured'

    # 5. Minor injury (non-exit — ball stays in tube) ─────────────────────────
    # Skill reduced by 40% of penalty. Growth still applies this quarter.
    minor_p = config.MINOR_INJURY_RATE.get(tier, 0.0)
    if rng.random() < minor_p:
        penalty    = config.INJURY_SKILL_PENALTY.get(tier, 0.0)
        ball.skill = max(0.001, ball.skill - penalty * 0.4)
        log.append(_event_record(ball, tier, 'minor_injury', step, year))
        # NOT an exit — chain continues

    # 6. Graduation ────────────────────────────────────────────────────────────
    # Requires skill >= GRAD_SKILL_THRESH[tier] AND tube_tenure >= GRAD_MIN_TENURE[tier].
    # PLACEHOLDER: GRAD_SKILL_THRESH set at ~90% of tier to reward near-mastery
    # rather than strict ceiling breach. Calibrate against apprenticeship
    # competency-assessment pass rates (DOL RAPIDS).
    grad_thresh     = config.GRAD_SKILL_THRESH.get(tier, tier * 0.9)
    grad_min_tenure = config.GRAD_MIN_TENURE.get(tier, 8)
    if ball.skill >= grad_thresh and ball.tube_tenure >= grad_min_tenure:
        next_tier        = next((t for t in sorted_tiers if t > tier), None)
        ball.target_tier = next_tier
        log.append(_event_record(ball, tier, 'graduation', step, year))
        return 'to_pool'

    # 7. Management graduation ─────────────────────────────────────────────────
    # High-skill + long-tenure workers promoted out of the tube system entirely.
    # Tiers 0.1-0.3 have no management path (MGMT_SKILL_THRESH = 0.0 → ineligible).
    # PLACEHOLDER: MGMT_GRAD_RATE = 0.30 quarterly if eligible.
    # Source: BLS occupational mobility between operative and supervisory codes.
    mgmt_thresh     = config.MGMT_SKILL_THRESH.get(tier, 99.0)
    mgmt_min_tenure = config.MGMT_MIN_TENURE.get(tier, 9999)
    if mgmt_thresh > 0.0 and ball.skill >= mgmt_thresh and ball.tube_tenure >= mgmt_min_tenure:
        if rng.random() < config.MGMT_GRAD_RATE:
            log.append(_event_record(ball, tier, 'management_graduation', step, year))
            return 'removed'

    # 8. Lucky break (non-exit) ────────────────────────────────────────────────
    # Poisson draw: P(at least one event) = 1 - exp(-lambda).
    # If fires: growth_multiplier = 5 for event 9.
    # PLACEHOLDER: lucky_break_lambda ~ 0.005-0.05.
    # Represents mentorship, internal training opportunity, project assignment.
    lam = ts.lucky_break_lambda
    if rng.random() < (1.0 - math.exp(-lam)):
        growth_multiplier = 5.0
        log.append(_event_record(ball, tier, 'lucky_break', step, year))

    # 9. Skill growth ──────────────────────────────────────────────────────────
    dskill     = ts.growth_field(ball.skill) * growth_multiplier
    ball.skill = max(0.001, min(0.999, ball.skill + dskill))
    ball.tenure      += 1
    ball.tube_tenure += 1
    ball.age         += 1
    ball.update_SER()

    # 10. Frustration quit ─────────────────────────────────────────────────────
    # Eligibility: ball near tier ceiling AND long tenure → skill stagnation.
    # Stagnancy score: 0 = growing fast, 1 = completely stagnant.
    # PLACEHOLDER: STAGNANCY_SKILL_THRESH = 0.90 * tier, STAGNANCY_MIN_TENURE = 16 qtrs.
    stagnancy_thresh = config.STAGNANCY_SKILL_THRESH * tier
    if ball.skill >= stagnancy_thresh and ball.tube_tenure >= config.STAGNANCY_MIN_TENURE:
        max_expected_ser = config.BASE_GROWTH_RATE * 0.5
        stagnancy_score  = max(0.0, 1.0 - ball.SER / max(max_expected_ser, 1e-9))
        frust_p = min(
            config.FRUSTRATION_MAX_P,
            config.FRUSTRATION_BASE_RATE + config.FRUSTRATION_SCALE * stagnancy_score,
        )
        if rng.random() < frust_p:
            log.append(_event_record(ball, tier, 'frustration_quit', step, year))
            return 'removed'

    # 11. Voluntary quit ───────────────────────────────────────────────────────
    # Ball moves to pool. target_tier stays None — placed based on skill.
    # PLACEHOLDER: QUIT_RATE_BY_TIER from BLS JOLTS quit rates by industry.
    quit_rate = config.QUIT_RATE_BY_TIER.get(tier, 0.02)
    if rng.random() < quit_rate:
        ball.target_tier = None
        log.append(_event_record(ball, tier, 'voluntary_quit', step, year))
        return 'to_pool'

    # 12. Career change (exits permanently to non-manufacturing sector) ─────────
    # PLACEHOLDER: CAREER_CHANGE_RATE separate from quit rates because this
    # permanently removes the worker from manufacturing; voluntary quit may
    # return to pool / re-enter.
    career_rate = config.CAREER_CHANGE_RATE.get(tier, 0.005)
    if rng.random() < career_rate:
        log.append(_event_record(ball, tier, 'career_change', step, year))
        return 'removed'

    return 'stayed'


# =============================================================================
# New entrant generation (event 16)
# =============================================================================

def _entry_events(
    tubes_by_tier : Dict[float, Tube],
    sorted_tiers  : List[float],
    params,
    rng           : random.Random,
    log           : EventLog,
    step          : int   = 0,
    year          : float = 0.0,
) -> None:
    """
    Create new Ball objects for this quarter's manufacturing entrants.
    Places them in the lowest valid tube (tier in [skill, 0.4]).

    PLACEHOLDER: Uses flat annual cohort / 4. Replace with Census birth-cohort
    projections (ACS Table B01001) for year-varying quarterly inflow.
    """
    workforce_scale = getattr(params, 'workforce_scale', 1)
    quarterly_n = int(
        config.ANNUAL_WORKING_AGE_COHORT
        * params.mfg_entry_pct
        / config.QUARTERS_PER_YEAR
        / max(workforce_scale, 1)
    )

    for _ in range(quarterly_n):
        skill = float(np.clip(
            np.random.normal(config.ENTRANT_SKILL_MEAN, config.ENTRANT_SKILL_STD),
            config.ENTRANT_SKILL_MIN,
            config.ENTRANT_SKILL_MAX,
        ))
        # PLACEHOLDER: immigrant share ~10.2% of manufacturing entrants (BLS CPS)
        is_immigrant = rng.random() < 0.102

        ball = Ball(
            skill        = skill,
            tube_tier    = None,
            tenure       = 0,
            tube_tenure  = 0,
            age_quartile = 1,
            age          = rng.randint(18 * 4, 25 * 4),
            immigrant    = is_immigrant,
            target_tier  = None,
        )

        # Place in lowest valid entry tube (0.1 <= tier <= 0.4, tier >= skill)
        valid = [t for t in sorted_tiers if t >= skill and t <= 0.4]
        if valid:
            tgt = valid[0]
            tubes_by_tier[tgt].add_ball(ball)
            log.append(_event_record(ball, tgt, 'entry', step, year))
