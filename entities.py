# =============================================================================
# entities.py  —  Core data classes: Ball, Tube, MarketPool
# =============================================================================
# Pure data containers — no simulation logic lives here.
# Engines import these and operate on them.
# =============================================================================

from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from typing import List, Optional
import config


# =============================================================================
# BALL  —  represents one worker
# =============================================================================
@dataclass
class Ball:
    """
    A single worker in the simulation.

    skill       : float [0.01 – 1.0]
                  Current skill level. Grows over time via growth_engine.
                  When skill > tube.tier, the ball graduates.

    tube_tier   : float
                  The tier of the tube this ball currently lives in.
                  Set to None when the ball is in MarketPool (between jobs).

    tenure      : int (quarters)
                  Total quarters this ball has been in the simulation.
                  Used by exit_engine to compute retirement probability.

    tube_tenure : int (quarters)
                  Quarters spent in the current tube.
                  Resets to 0 on graduation / tube change.

    age_quartile: int [1–4]
                  PLACEHOLDER: rough age bracket of the worker.
                  1 = new entrant (18-25), 4 = near retirement (55+).
                  Drives retirement probability in exit_engine.
                  Source: BLS CPS age-by-industry breakdown.

    immigrant   : bool
                  PLACEHOLDER: whether this worker is foreign-born.
                  Affects shock sensitivity in exit_engine.
                  Source: BLS CPS nativity × industry tables.

    ball_id     : str
                  Unique identifier — auto-generated.
    """
    skill        : float
    tube_tier    : Optional[float]
    tenure       : int   = 0
    tube_tenure  : int   = 0
    age_quartile : int   = 1        # PLACEHOLDER — see above
    immigrant    : bool  = False    # PLACEHOLDER — see above
    ball_id      : str   = field(default_factory=lambda: str(uuid.uuid4())[:8])

    # ── New fields (Part 2 architecture) ─────────────────────────────────────
    age          : int   = 0
    # Total quarters alive in simulation (proxy for real age when initialised
    # via _populate_initial_workforce age-group calibration).

    pool_tenure  : int   = 0
    # Quarters spent in MarketPool since last placement. Resets on placement.
    # Used by barrier_engine P_pool decay and discouragement exit probability.

    target_tier  : Optional[float] = None
    # The specific tier this ball is trying to enter from the pool.
    # Set on graduation (next tier up). None = voluntary quit (skill-matched).

    on_probation           : bool  = False
    probation_gap          : float = 0.0
    probation_qtrs_remaining: int  = 0
    # PLACEHOLDER: probation fields reserved for a future mechanic where
    # newly placed balls face a probation period during which they can be
    # returned to pool if performance is below probation_gap threshold.
    # Not yet wired into event_engine.

    SER          : float = 0.0
    # Skill Earnings Rate = skill / max(tube_tenure, 1).
    # Updated by update_SER() after each growth event.
    # High SER = fast learner; low SER = stagnating worker.
    # PLACEHOLDER: SER is a proxy for per-worker productivity growth.
    # Replace with firm-level matched employer-employee data (LEHD).

    # ── methods ───────────────────────────────────────────────────────────────
    def update_SER(self) -> None:
        """
        Recalculate Skill Earnings Rate after a growth or placement event.
        SER = skill / max(tube_tenure, 1)
        Called by event_engine after skill_growth step (event 9) and on
        placement into a new tube (tube_tenure resets to 0 -> SER = skill).
        """
        self.SER = self.skill / max(self.tube_tenure, 1)

    # ── derived properties ────────────────────────────────────────────────────
    @property
    def is_near_retirement(self) -> bool:
        """True once tenure exceeds the retirement threshold in config."""
        return self.tenure >= config.RETIREMENT_TENURE_THRESHOLD

    @property
    def effective_output(self) -> float:
        """
        How much 'work' this ball contributes relative to a full-tier worker.
        A ball of skill 0.1 in tube 0.5 contributes 0.1/0.5 = 0.20 of a unit.
        A ball of skill 0.48 in tube 0.5 contributes 0.48/0.5 = 0.96 of a unit.
        This is the ELU concept translated into physics.
        """
        if self.tube_tier is None or self.tube_tier == 0:
            return 0.0
        return min(self.skill / self.tube_tier, 1.0)

    def __repr__(self):
        return (f"Ball(id={self.ball_id}, skill={self.skill:.3f}, "
                f"tube={self.tube_tier}, tenure={self.tenure}q)")


# =============================================================================
# TUBE  —  represents a skill-tier job category
# =============================================================================
@dataclass
class Tube:
    """
    A vertical tube representing one skill tier of the job market.

    tier            : float [0.1 – 1.0]
                      The skill ceiling of this tube.
                      Balls with skill > tier graduate out.

    diameter        : float
                      Physical width of the tube — proportional to tier.
                      Wider = higher-tier jobs (more complex, more workers).
                      diameter = tier * config.TUBE_DIAMETER_SCALE

    demand_height   : float
                      How many effective worker-units this tube needs RIGHT NOW.
                      Raised by reshoring and industry growth each quarter.
                      Measured in thousands of workers.

    balls           : List[Ball]
                      All workers currently in this tube.

    Derived metrics (computed, not stored):
    - effective_volume : sum of ball.effective_output across all balls
    - vacuum           : demand_height - effective_volume  (floored at 0)
    - density          : len(balls) / (diameter^2)  (crowding metric for growth)
    """
    tier          : float
    diameter      : float
    demand_height : float
    balls         : List[Ball] = field(default_factory=list)

    # ── capacity / volume ─────────────────────────────────────────────────────
    @property
    def headcount(self) -> int:
        """Raw number of workers in this tube."""
        return len(self.balls)

    @property
    def effective_volume(self) -> float:
        """
        Sum of effective output units across all balls.
        This is what actually fills the tube — not raw headcount.
        A tube full of 0.1-skill balls in a 0.5-tier tube is mostly empty
        in output terms, even if headcount looks fine.
        """
        return sum(b.effective_output for b in self.balls)

    @property
    def vacuum(self) -> float:
        """
        Output gap = demand - effective supply.
        Positive = shortfall. Zero = demand met. Never goes negative.
        """
        return max(self.demand_height - self.effective_volume, 0.0)

    @property
    def density(self) -> float:
        """
        Crowding metric used by growth_engine.
        Higher density → slower individual skill growth.
        PLACEHOLDER: normalisation constant 1000 is arbitrary —
        calibrate against real productivity-per-worker data.
        """
        if self.diameter == 0:
            return 0.0
        return self.headcount / (self.diameter ** 2 * 1000)

    @property
    def fill_pct(self) -> float:
        """Effective volume as % of demand. 1.0 = fully met."""
        if self.demand_height == 0:
            return 1.0
        return min(self.effective_volume / self.demand_height, 1.0)

    # ── ball management ───────────────────────────────────────────────────────
    def add_ball(self, ball: Ball):
        ball.tube_tier   = self.tier
        ball.tube_tenure = 0
        self.balls.append(ball)

    def remove_ball(self, ball: Ball):
        ball.tube_tier = None
        self.balls.remove(ball)

    def __repr__(self):
        return (f"Tube(tier={self.tier}, balls={self.headcount}, "
                f"eff_vol={self.effective_volume:.1f}, "
                f"demand={self.demand_height:.1f}, vac={self.vacuum:.1f})")


# =============================================================================
# MARKET POOL  —  graduated balls waiting for placement
# =============================================================================
@dataclass
class MarketPool:
    """
    Holds balls that have graduated from their tube and are seeking
    a slot in the tier above.

    waiting : List[tuple[Ball, int]]
              Each entry is (ball, quarters_waiting).
              Quarters waiting increments each step until placement.

    PLACEHOLDER: placement_lag mechanics not yet implemented.
    Currently all balls in pool are offered placement each quarter.
    Future: add job-search duration drawn from BLS JOLTS time-to-fill data.
    """
    waiting         : List[tuple] = field(default_factory=list)
    injured_waiting : List[tuple] = field(default_factory=list)
    # injured_waiting entries: (ball, recovery_quarters_remaining)
    # Ball returns to active waiting list when counter reaches 0.
    # PLACEHOLDER: INJURY_RECOVERY_Q values from BLS SOII median days away
    # from work by industry and injury type.

    def add(self, ball: Ball):
        ball.tube_tier = None
        self.waiting.append((ball, 0))

    def tick(self):
        """Increment waiting time for all balls in pool."""
        self.waiting = [(b, q + 1) for b, q in self.waiting]

    def remove(self, ball: Ball):
        self.waiting = [(b, q) for b, q in self.waiting if b.ball_id != ball.ball_id]

    @property
    def balls(self) -> List[Ball]:
        return [b for b, _ in self.waiting]

    @property
    def size(self) -> int:
        return len(self.waiting)

    def __repr__(self):
        return f"MarketPool(waiting={self.size})"
