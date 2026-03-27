# =============================================================================
# config.py  —  All placeholders in one place
# =============================================================================
# Every value marked PLACEHOLDER can be replaced with real data.
# Source suggestions are noted in comments.
# =============================================================================

# ── Simulation time ───────────────────────────────────────────────────────────
START_YEAR   = 2025
END_YEAR     = 2033
QUARTERS_PER_YEAR = 4
TOTAL_STEPS  = (END_YEAR - START_YEAR) * QUARTERS_PER_YEAR  # 32 quarters

# ── Tube definitions ──────────────────────────────────────────────────────────
# 10 skill tiers from 0.1 (entry) to 1.0 (expert)
# Diameter is proportional to tier — wider tubes hold more workers
TUBE_TIERS = [round(t * 0.1, 1) for t in range(1, 11)]
# [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]

# PLACEHOLDER: diameter multiplier per tier
# Currently linear — could be shaped by real job distribution data (BLS OES)
TUBE_DIAMETER_SCALE = 2.0  # tube diameter = tier * TUBE_DIAMETER_SCALE

# ── Initial worker population ─────────────────────────────────────────────────
# PLACEHOLDER: Total US manufacturing workers Dec 2025
# Source: BLS CES series CEU3000000001
INITIAL_WORKFORCE = 12_690_000

# PLACEHOLDER: Distribution of workers across tiers at t=0
# Currently a rough bell curve centred on tier 0.4 (general manufacturing)
# Replace with BLS OES occupational distribution data
INITIAL_TIER_DISTRIBUTION = {
    # Each value multiplied by 0.75 to represent a 25% vacancy gap at model start
    0.1: 0.0600,   # ~0.76M  entry / assembly
    0.2: 0.0975,   # ~1.24M  semi-skilled operators
    0.3: 0.1200,   # ~1.52M  skilled operators
    0.4: 0.1350,   # ~1.71M  core manufacturing
    0.5: 0.1200,   # ~1.52M  senior operators / technicians
    0.6: 0.0900,   # ~1.14M  lead technicians
    0.7: 0.0675,   # ~0.86M  specialists
    0.8: 0.0375,   # ~0.48M  senior specialists
    0.9: 0.0150,   # ~0.19M  master craftspeople
    1.0: 0.0075,   # ~0.10M  experts / system designers
}

# ── Inflow (new entrants from population pipeline) ────────────────────────────
# PLACEHOLDER: Annual US birth cohort reaching working age (~18-22)
# Source: US Census Bureau, American Community Survey Table B01001
ANNUAL_WORKING_AGE_COHORT = 4_584_041

# PLACEHOLDER: % of working-age entrants going into manufacturing
# Source: BLS Current Population Survey, Table 14 (industry of employment)
# Has been declining from ~12% (2000) to ~8% (2024)
MFG_ENTRY_PCT = 0.085

# Annual manufacturing entrants (derived — do not edit directly)
ANNUAL_MFG_ENTRANTS = int(ANNUAL_WORKING_AGE_COHORT * MFG_ENTRY_PCT)
# ~340,000 / year → ~85,000 / quarter

# PLACEHOLDER: Skill distribution of NEW entrants (always enter low tiers)
# New entrants can only enter tubes 0.1–0.4
# Source: BLS JOLTS, apprenticeship programme completion data (DOL)
ENTRANT_SKILL_MEAN  = 0.12   # most start near bottom
ENTRANT_SKILL_STD   = 0.06   # some variation (community college grads vs raw)
ENTRANT_SKILL_MIN   = 0.01
ENTRANT_SKILL_MAX   = 0.35   # hard cap — no new entrant starts above 0.35

# ── Growth engine parameters ──────────────────────────────────────────────────
# Skill growth formula:
#   dskill/dt = BASE_GROWTH_RATE
#               * (skill / tube_tier) ^ ALPHA      # proximity to ceiling
#               * (1 / (1 + BETA * density))       # crowding penalty
#               * tube_tier                         # higher tiers grow faster

# PLACEHOLDER: Base quarterly growth rate
# Source: no direct empirical source — calibrate against apprenticeship
#         programme completion data (DOL RAPIDS database)
BASE_GROWTH_RATE = 0.015   # ~6% skill gain per year at base

# PLACEHOLDER: Alpha — controls convexity of proximity effect
# Higher alpha = faster growth only very close to ceiling; lower = more linear
# Reasonable range: 0.5–2.5
ALPHA = 1.4

# PLACEHOLDER: Beta — crowding sensitivity
# Higher beta = growth slows sharply in dense tubes
# Reasonable range: 0.1–1.0
BETA = 0.3

# ── Graduation ────────────────────────────────────────────────────────────────
# A ball graduates when skill > tube_tier
# It then enters MarketPool and seeks the next tube up

# PLACEHOLDER: Quarterly probability that a graduated ball actually FINDS
# a slot in the next tube (job market matching efficiency)
# 1.0 = instant placement; 0.5 = 50% chance each quarter
PLACEMENT_PROBABILITY = 0.7

# ── Exit engine parameters ────────────────────────────────────────────────────

# Voluntary quit (career change / burnout)
# PLACEHOLDER: Quarterly probability of voluntary exit, by tier
# Source: BLS JOLTS quit rates by industry (Table 16)
# Lower tiers have higher quit rates
QUIT_RATE_BY_TIER = {
    0.1: 0.0250,  # ~10%/yr  — manufacturing-exit quit (BLS JOLTS Table 16)
    0.2: 0.0211,
    0.3: 0.0167,
    0.4: 0.0139,
    0.5: 0.0111,
    0.6: 0.0083,
    0.7: 0.0067,
    0.8: 0.0050,
    0.9: 0.0039,
    1.0: 0.0028,  # ~1.1%/yr — experts rarely leave
}

# Retirement (age-driven)
# PLACEHOLDER: Quarterly retirement probability by worker age quartile
# Source: BLS CPS, SIPP (Survey of Income & Program Participation)
# In simulation, age is proxied by total tenure in the system
RETIREMENT_TENURE_THRESHOLD = 120   # quarters (30 years) before retirement risk rises
RETIREMENT_BASE_RATE        = 0.035  # quarterly rate once above threshold
# Scales up with tenure beyond threshold — see exit_engine.py

# Policy shock (ICE raids, layoffs, recession)
# PLACEHOLDER: Probability of a shock event occurring in any given quarter
# Source: calibrate against historical enforcement data (DHS enforcement stats)
SHOCK_PROBABILITY    = 0.05   # 5% chance per quarter — placeholder
SHOCK_REMOVAL_RATE   = 0.02   # % of workers removed if shock occurs
# PLACEHOLDER: Shock hits lower tiers harder (higher immigrant share)
SHOCK_TIER_WEIGHTS = {
    0.1: 3.0,   # food processing, textiles — highest exposure
    0.2: 2.5,
    0.3: 1.5,
    0.4: 1.0,   # baseline
    0.5: 0.8,
    0.6: 0.5,
    0.7: 0.3,
    0.8: 0.2,
    0.9: 0.1,
    1.0: 0.05,
}

# ── Demand signals ────────────────────────────────────────────────────────────
# Demand raises the HEIGHT of each tube — does not create workers

# PLACEHOLDER: Annual industry output growth rate
# Source: UNIDO World Manufacturing Production Q1 2025
INDUSTRY_GROWTH_RATE = 0.019   # 1.9% per year (UNIDO 2024 USA baseline)

# PLACEHOLDER: Total reshoring labour demand 2025–2033 (millions)
# Source: Reshoring Initiative 2024 + CHIPS Act + IRA + IIJA
RESHORING_TOTAL_M = 0.300   # 300k workers total over 9 years (Reshoring Initiative 2024)

# PLACEHOLDER: Tier distribution of reshoring demand
# Reshoring tends to create mid-tier jobs (CNC, electronics assembly)
RESHORING_TIER_WEIGHTS = {
    0.1: 0.05,
    0.2: 0.10,
    0.3: 0.20,
    0.4: 0.25,
    0.5: 0.20,
    0.6: 0.12,
    0.7: 0.05,
    0.8: 0.02,
    0.9: 0.01,
    1.0: 0.00,
}

# ── Monte Carlo parameters ────────────────────────────────────────────────────
MC_RUNS   = 500
MC_SEED   = 42

# Parameter variation ranges for MC sampling (Normal distributions)
# PLACEHOLDER: Std devs represent uncertainty — tighten as more data arrives
MC_PARAMS = {
    "alpha":              {"mean": ALPHA,              "std": 0.30},
    "beta":               {"mean": BETA,               "std": 0.08},
    "base_growth_rate":   {"mean": BASE_GROWTH_RATE,   "std": 0.004},
    "mfg_entry_pct":      {"mean": MFG_ENTRY_PCT,      "std": 0.010},
    "shock_probability":  {"mean": SHOCK_PROBABILITY,  "std": 0.020},
    "industry_growth":    {"mean": INDUSTRY_GROWTH_RATE,"std": 0.005},
    "reshoring_total_m":  {"mean": RESHORING_TOTAL_M,  "std": 0.075},
}

# =============================================================================
# Part 2 additions — new mechanics parameters
# =============================================================================

# ── Skill regression rate (above attractor) ───────────────────────────────────
# PLACEHOLDER: regression is very slow — 8% of growth rate.
# Represents skill decay when a worker operates just above their tier ceiling.
REGRESSION_RATE = 0.08

# ── Barrier engine parameters ──────────────────────────────────────────────────
# PLACEHOLDER: all values are initial estimates.
# See barrier_engine.py for calibration source notes per factor.
BARRIER_PARAMS = dict(
    sigma_right_base    = 0.12,   # right-tail sigma for P_accept Gaussian
    sigma_left_mult     = 2.8,    # left-tail sigma = sigma_right * this
    hard_cap_skill      = 0.1,    # absolute floor: below this skill, no placement
    hard_cap_tube       = 0.7,    # tube tier above which max_upward_gap enforced
    hard_cap_p          = 0.0001, # placement probability when hard cap triggered
    max_upward_gap      = 0.6,    # max skill gap allowed for high-tier placement
    lambda_flunk        = 4.0,    # flunk penalty exponential decay rate
    retire_age          = 65,     # years: employer won't invest beyond this age
    training_base_cost  = 2000,   # $ base training cost
    cost_exp_k          = 6.0,    # exponential growth rate of training cost with gap
    employer_max_cost   = 12000,  # $ max employer will spend on training per hire
    min_years_to_work   = 3,      # years remaining before near-retirement block
    age_yield_scale     = 0.04,   # training yield discount per year above 25
    yield_base          = 0.85,   # baseline training yield probability
    pool_decay_rate     = 0.97,   # quarterly skill decay rate while in pool
    pool_floor          = 0.20,   # minimum P_pool (BLS JOLTS: 8-12 applicants/opening)
    k_pool_sensitivity  = 5,      # competition sensitivity in P_pool factor
    luck_p              = 0.002,  # small additive luck term in P_barrier
    beta_crowd          = 0.1,    # crowding sensitivity in P_crowd factor (lowered from 5.0)
)

# ── Frustration / stagnation parameters ───────────────────────────────────────
# PLACEHOLDER: thresholds represent workers near skill ceiling for too long.
# Calibrate against BLS job-to-job transition data by tenure band.
STAGNANCY_SKILL_THRESH  = 0.90   # fraction of tier at which stagnancy risk starts
STAGNANCY_MIN_TENURE    = 16     # minimum quarters before frustration risk opens
FRUSTRATION_BASE_RATE   = 0.02   # quarterly base probability of frustration quit
FRUSTRATION_SCALE       = 0.08   # additional probability per unit stagnancy score
FRUSTRATION_MAX_P       = 0.25   # quarterly cap on frustration quit probability

# ── Graduation thresholds and tenure minimums ─────────────────────────────────
# PLACEHOLDER: GRAD_SKILL_THRESH set at ~90% of tier to reward near-mastery.
# GRAD_MIN_TENURE reflects typical apprenticeship programme lengths (DOL RAPIDS).
GRAD_SKILL_THRESH  = {0.1: 0.08, 0.2: 0.17, 0.3: 0.27, 0.4: 0.36, 0.5: 0.45,
                      0.6: 0.54, 0.7: 0.63, 0.8: 0.72, 0.9: 0.82, 1.0: 0.92}
GRAD_MIN_TENURE    = {0.1:  4,   0.2:  6,   0.3:  8,   0.4: 10,   0.5: 12,
                      0.6: 14,   0.7: 16,   0.8: 20,   0.9: 24,   1.0: 32}

# ── Management graduation thresholds ─────────────────────────────────────────
# Tiers 0.1-0.3 have no management path (MGMT_SKILL_THRESH = 0.0 blocks eligibility).
# PLACEHOLDER: MGMT_GRAD_RATE = 0.30 quarterly if eligible.
MGMT_SKILL_THRESH  = {0.1: 0.0,  0.2: 0.0,  0.3: 0.0,  0.4: 0.38, 0.5: 0.47,
                      0.6: 0.56, 0.7: 0.65, 0.8: 0.74, 0.9: 0.84, 1.0: 0.95}
MGMT_MIN_TENURE    = {0.1:  0,   0.2:  0,   0.3:  0,   0.4: 16,   0.5: 16,
                      0.6: 20,   0.7: 24,   0.8: 28,   0.9: 32,   1.0: 40}
MGMT_GRAD_RATE     = 0.015

# ── Career change rates (exits permanently to non-manufacturing) ───────────────
# PLACEHOLDER: separate from voluntary quit because career changers never return.
# Source: CPS tenure supplement career-change transitions by occupation.
CAREER_CHANGE_RATE = {0.1: 0.028, 0.2: 0.022, 0.3: 0.017, 0.4: 0.012, 0.5: 0.009,
                      0.6: 0.007, 0.7: 0.005, 0.8: 0.003, 0.9: 0.002, 1.0: 0.0015}

# ── Injury rates and penalties ────────────────────────────────────────────────
# PLACEHOLDER: all rates from BLS SOII (Survey of Occupational Injuries &
# Illnesses) by NAICS subsector. Mapped to skill tiers as a proxy for
# occupational exposure level. Calibrate using NAICS-to-tier crosswalk.
MINOR_INJURY_RATE   = {0.1: 0.0088, 0.2: 0.0105, 0.3: 0.0145, 0.4: 0.0168,
                       0.5: 0.0125, 0.6: 0.0195, 0.7: 0.0215, 0.8: 0.0155,
                       0.9: 0.0225, 1.0: 0.0285}
SERIOUS_INJURY_RATE = {0.1: 0.0012, 0.2: 0.0018, 0.3: 0.0025, 0.4: 0.0032,
                       0.5: 0.0022, 0.6: 0.0042, 0.7: 0.0055, 0.8: 0.0038,
                       0.9: 0.0068, 1.0: 0.0095}
FATAL_INJURY_RATE   = {0.1: 0.000005, 0.2: 0.000008, 0.3: 0.000015, 0.4: 0.000025,
                       0.5: 0.000012, 0.6: 0.000035, 0.7: 0.000055, 0.8: 0.000042,
                       0.9: 0.000085, 1.0: 0.000145}
INJURY_SKILL_PENALTY = {0.1: 0.02, 0.2: 0.03, 0.3: 0.04, 0.4: 0.05, 0.5: 0.04,
                        0.6: 0.06, 0.7: 0.07, 0.8: 0.08, 0.9: 0.10, 1.0: 0.12}
INJURY_RECOVERY_Q    = {0.1: 1, 0.2: 1, 0.3: 2, 0.4: 2, 0.5: 2,
                        0.6: 3, 0.7: 3, 0.8: 4, 0.9: 5, 1.0: 6}


def validate_config():
    """
    Sanity-check critical parameter relationships.
    Call from simulation.__init__() to catch miscalibration early.
    """
    assert sum(INITIAL_TIER_DISTRIBUTION.values()) <= 1.01, \
        "INITIAL_TIER_DISTRIBUTION sums > 1"
    assert all(v >= 0 for v in QUIT_RATE_BY_TIER.values()), \
        "Negative quit rate"
    assert all(v >= 0 for v in CAREER_CHANGE_RATE.values()), \
        "Negative career change rate"
    assert MGMT_GRAD_RATE <= 0.10, \
        f"MGMT_GRAD_RATE={MGMT_GRAD_RATE} suspiciously high (>10%/qtr)"
    assert RETIREMENT_TENURE_THRESHOLD >= 40, \
        f"RETIREMENT_TENURE_THRESHOLD={RETIREMENT_TENURE_THRESHOLD} too low — workers retire too young"
    assert BARRIER_PARAMS['pool_floor'] <= 0.40, \
        "pool_floor too generous — placement is not realistic"
    assert 0 < MFG_ENTRY_PCT < 0.20, \
        "MFG_ENTRY_PCT out of realistic range"
    for tier in TUBE_TIERS:
        assert GRAD_SKILL_THRESH.get(tier, 0) < tier, \
            f"GRAD_SKILL_THRESH[{tier}] must be less than tier ceiling"
