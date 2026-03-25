# =============================================================================
# simulation.py  --  Main orchestrator: initialise + run one full simulation
# =============================================================================

from __future__ import annotations
import random
import numpy as np
import pandas as pd
from typing import Dict, List, Optional
from dataclasses import dataclass, field

import config
import state_manager
import event_engine
from entities import Ball, Tube, MarketPool


# =============================================================================
# Parameter bundle (one instance per MC run)
# =============================================================================
@dataclass
class SimParams:
    """
    All tuneable parameters for one simulation run.
    Defaults come from config.py — Monte Carlo overrides them per run.
    workforce_scale divides population counts for fast testing (--scale flag).
    """
    alpha              : float = config.ALPHA
    beta               : float = config.BETA
    base_growth_rate   : float = config.BASE_GROWTH_RATE
    mfg_entry_pct      : float = config.MFG_ENTRY_PCT
    shock_probability  : float = config.SHOCK_PROBABILITY
    shock_removal_rate : float = config.SHOCK_REMOVAL_RATE
    industry_growth    : float = config.INDUSTRY_GROWTH_RATE
    reshoring_total_m  : float = config.RESHORING_TOTAL_M
    placement_prob     : float = config.PLACEMENT_PROBABILITY
    seed               : int   = 42
    workforce_scale    : int   = 1   # divide all populations by this factor


# =============================================================================
# Snapshot — system state at one timestep (output record)
# =============================================================================
@dataclass
class Snapshot:
    step        : int
    year        : float
    total_balls : int
    pool_size   : int
    per_tube    : List[dict]
    exits       : dict


# =============================================================================
# Simulation
# =============================================================================
class Simulation:
    """
    Runs a complete 2025-2033 labour market simulation (32 quarters).

    Usage:
        sim = Simulation(SimParams(seed=42, workforce_scale=1000))
        snapshots = sim.run()
        df = sim.to_dataframe(snapshots)
    """

    def __init__(self, params: SimParams = None, workforce_scale: int = None):
        self.params = params or SimParams()
        # workforce_scale: prefer explicit kwarg, then params field, then 1
        if workforce_scale is not None:
            self.params.workforce_scale = max(1, workforce_scale)
        self.workforce_scale = max(1, self.params.workforce_scale)

        self.rng = random.Random(self.params.seed)
        np.random.seed(self.params.seed)

        self.tubes_by_tier: Dict[float, Tube] = {}
        self.pool = MarketPool()
        self._cumulative_exits: Dict[str, int] = {}

        self._initialise_tubes()
        self._populate_initial_workforce()

    # ── Setup ─────────────────────────────────────────────────────────────────

    def _initialise_tubes(self):
        """
        Create one Tube per tier. demand_height is set to 0 here and
        calibrated to effective_volume after _populate_initial_workforce runs,
        so that vacuum = 25% of supply from step 0 (the 2025 vacancy gap).
        """
        for tier in config.TUBE_TIERS:
            diameter = tier * config.TUBE_DIAMETER_SCALE
            self.tubes_by_tier[tier] = Tube(
                tier=tier, diameter=diameter, demand_height=0.0
            )

    def _populate_initial_workforce(self):
        """
        Distribute INITIAL_WORKFORCE balls across tubes using
        INITIAL_TIER_DISTRIBUTION (already multiplied by 0.75 in config).

        Age-group calibration reflects US manufacturing workforce census data
        (approximate 2025 age pyramid from BLS CPS by industry):
          55-64  ~23%  tenure = randint(28, 40)  (near-retirement cohort)
          45-54  ~25%  tenure = randint(16, 28)  (mid-career peak)
          35-44  ~22%  tenure = randint(12, 16)  (established workers)
          20-34  ~30%  tenure = randint( 0, 12)  (early-career entrants)

        PLACEHOLDER: age-group weights from BLS CPS Table 14 (manufacturing
        by age). Update with ACS 5-year estimates when available.
        """
        AGE_GROUPS   = ['20_34', '35_44', '45_54', '55_64']
        AGE_WEIGHTS  = [0.30,    0.22,    0.25,    0.23]

        for tier, tube in self.tubes_by_tier.items():
            share     = config.INITIAL_TIER_DISTRIBUTION.get(tier, 0.0)
            n_workers = int(config.INITIAL_WORKFORCE * share / self.workforce_scale)

            for _ in range(n_workers):
                low   = max(tier - 0.09, 0.001)
                skill = self.rng.uniform(low, tier)

                # Draw age group from US manufacturing age distribution
                age_group = self.rng.choices(AGE_GROUPS, weights=AGE_WEIGHTS, k=1)[0]

                if age_group == '55_64':
                    tenure      = self.rng.randint(28, 40)
                    age_qtrs    = self.rng.randint(55 * 4, 65 * 4)
                    age_quartile = 4
                elif age_group == '45_54':
                    tenure      = self.rng.randint(16, 28)
                    age_qtrs    = self.rng.randint(45 * 4, 55 * 4)
                    age_quartile = 3
                elif age_group == '35_44':
                    tenure      = self.rng.randint(12, 16)
                    age_qtrs    = self.rng.randint(35 * 4, 45 * 4)
                    age_quartile = 2
                else:  # 20_34
                    tenure      = self.rng.randint(0, 12)
                    age_qtrs    = self.rng.randint(20 * 4, 35 * 4)
                    age_quartile = 1

                ball = Ball(
                    skill         = skill,
                    tube_tier     = tier,
                    tenure        = tenure,
                    tube_tenure   = 0,       # reset to 0 — prevents cascade graduation at t=0
                    age_quartile  = age_quartile,
                    age           = age_qtrs,
                    immigrant     = self.rng.random() < 0.102,
                    target_tier   = None,
                )
                ball.update_SER()
                tube.balls.append(ball)

        # Calibrate demand heights so vacuum = 25% of supply at t=0
        # (matches the 0.75 multiplier in INITIAL_TIER_DISTRIBUTION)
        for tube in self.tubes_by_tier.values():
            if tube.effective_volume > 0:
                tube.demand_height = tube.effective_volume / 0.75

    # ── Demand update ─────────────────────────────────────────────────────────

    def _update_demand(self, step: int):
        """
        Raise tube demand heights each quarter:
        1. Industry output growth (all tiers proportionally)
        2. Reshoring demand (weighted towards mid tiers)

        PLACEHOLDER: reshoring spread evenly over TOTAL_STEPS quarters.
        Replace with Reshoring Initiative project pipeline calendar.
        """
        quarterly_growth         = self.params.industry_growth / config.QUARTERS_PER_YEAR
        # Reshoring adds individual worker-equivalent units each quarter.
        # reshoring_total_m is in millions; divide by TOTAL_STEPS to spread evenly.
        quarterly_reshoring_units = (
            self.params.reshoring_total_m * 1_000_000
            / config.TOTAL_STEPS
            / self.workforce_scale
        )

        for tier, tube in self.tubes_by_tier.items():
            tube.demand_height *= (1 + quarterly_growth)
            weight              = config.RESHORING_TIER_WEIGHTS.get(tier, 0.0)
            tube.demand_height += quarterly_reshoring_units * weight

    # ── Main loop ─────────────────────────────────────────────────────────────

    def run(self) -> List[Snapshot]:
        """
        Execute all 32 quarters. Returns list of Snapshot objects.

        Order of operations each quarter:
          1. Update demand heights
          2. Compute state snapshots (tube_states, pool_state, system_state)
          3. Inject shock flag and cumulative exit history into system_state
          4. Run event_engine.process_all_events()
          5. Update cumulative exits; record snapshot
        """
        snapshots = []

        for step in range(config.TOTAL_STEPS):
            year = config.START_YEAR + step / config.QUARTERS_PER_YEAR

            # 1. Demand
            self._update_demand(step)

            # 2. Compute states BEFORE events fire
            tube_states, pool_state, system_state = state_manager.compute_all_states(
                self.tubes_by_tier, self.pool, step
            )

            # 3. Inject context into system_state
            system_state.cumulative_exits_by_reason = dict(self._cumulative_exits)
            if self.rng.random() < self.params.shock_probability:
                system_state.shock_active = {'policy': True}

            # 4. Process all events
            evt_log = event_engine.process_all_events(
                self.tubes_by_tier,
                self.pool,
                tube_states,
                pool_state,
                system_state,
                self.params,
                self.rng,
            )

            # 5. Accumulate exits and snapshot
            for _, _, reason in evt_log:
                self._cumulative_exits[reason] = (
                    self._cumulative_exits.get(reason, 0) + 1
                )
            system_state.total_exits_this_quarter = len(evt_log)

            snap = self._snapshot(step, year, evt_log, tube_states, system_state)
            snapshots.append(snap)

        return snapshots

    # ── Snapshot builder ──────────────────────────────────────────────────────

    def _snapshot(self, step, year, evt_log, tube_states, system_state) -> Snapshot:
        per_tube = []
        for tier in sorted(tube_states.keys()):
            ts = tube_states[tier]
            per_tube.append({
                'tier'         : tier,
                'headcount'    : ts.headcount,
                'eff_volume'   : round(ts.effective_volume, 2),
                'demand_height': round(ts.demand_height, 2),
                'vacuum'       : round(ts.vacuum, 2),
                'fill_pct'     : round(ts.fill_pct, 4),
                'density'      : round(ts.crowding_index, 4),
                'mean_SER'     : round(ts.mean_SER, 5),
                'stagnant_frac': round(ts.stagnant_fraction, 4),
            })

        exits = {}
        for _, _, reason in evt_log:
            exits[reason] = exits.get(reason, 0) + 1

        return Snapshot(
            step=step,
            year=round(year, 2),
            total_balls=system_state.total_workforce,
            pool_size=system_state.total_pool,
            per_tube=per_tube,
            exits=exits,
        )

    # ── Output helpers ────────────────────────────────────────────────────────

    @staticmethod
    def to_dataframe(snapshots: List[Snapshot]) -> pd.DataFrame:
        """Flatten snapshots into a tidy DataFrame. All exit reasons included."""
        all_reasons = sorted({r for snap in snapshots for r in snap.exits})
        rows = []
        for snap in snapshots:
            for t in snap.per_tube:
                row = {
                    'step'       : snap.step,
                    'year'       : snap.year,
                    'total_balls': snap.total_balls,
                    'pool_size'  : snap.pool_size,
                    **t,
                }
                for reason in all_reasons:
                    row[f'exits_{reason}'] = snap.exits.get(reason, 0)
                rows.append(row)
        return pd.DataFrame(rows)
