"""Scoring weights, thresholds, and reference data."""

import os

# CMS Provider Data API
CMS_API_BASE = "https://data.cms.gov/provider-data/api/1/datastore/query"
PROVIDER_INFO_DATASET = "4pq5-n9py"
HEALTH_DEFICIENCIES_DATASET = "r5ix-sfxw"
PENALTIES_DATASET = "g6vv-u9sr"
OWNERSHIP_DATASET = "y2hd-n93e"
MDS_QM_DATASET = "djen-97ju"

# Search defaults
DEFAULT_RADIUS_MILES = 50
DEFAULT_TOP_N = 5

# Composite scoring weights (must sum to 1.0)
WEIGHTS = {
    "overall_rating": 0.25,
    "health_inspection": 0.20,
    "staffing_quality": 0.20,
    "staff_stability": 0.10,
    "penalty_history": 0.10,
    "distance": 0.10,
    "safety": 0.05,
}

# Weight given to the condition-match component when a needs profile is
# active. The base WEIGHTS are scaled by (1 - CONDITION_MATCH_WEIGHT) so the
# total still sums to 1.0.
CONDITION_MATCH_WEIGHT = 0.15

# National benchmarks for scoring.
#
# 4.1 hrs/resident/day is the minimum total direct-care nursing time
# recommended by the 2001 CMS-commissioned staffing study (the oft-cited
# "4.1 standard"; see https://theconsumervoice.org/staffing/). It is a
# recommended minimum, NOT the national average (which is ~3.6 hrs).
NATIONAL_TOTAL_NURSE_HOURS_PER_RESIDENT_DAY = 4.1
# Turnover reference points: CMS Payroll-Based Journal analyses report
# national mean turnover of ~53% (total nursing) and ~52% (RN); see
# https://www.cms.gov/newsroom/press-releases/advance-information-quality-care-cms-makes-nursing-home-staffing-data-available
# These project-set reference points anchor the 50-point midpoint of the
# staff-stability score.
NATIONAL_MEDIAN_TOTAL_TURNOVER = 52.0  # percent
NATIONAL_MEDIAN_RN_TURNOVER = 50.0  # percent

# Abuse flag penalty (subtracted from composite score)
ABUSE_PENALTY = 50
# Heavier penalty when the needs profile includes a vulnerable population
# (dementia, mental health)
ABUSE_PENALTY_VULNERABLE = 60

# Minimum number of state datapoints required for a percentile benchmark;
# below this the measure scores neutral (50).
MIN_BENCHMARK_SAMPLES = 20

# LLM config (overridable via environment)
LLM_MODEL = os.environ.get("DEARNANA_LLM_MODEL", "claude-sonnet-4-6")
CONDITION_PARSER_MODEL = os.environ.get("DEARNANA_PARSER_MODEL", "claude-haiku-4-5")
LLM_MAX_TOKENS = 2500
LLM_TEMPERATURE = 0.3

# State median monthly nursing home costs (semi-private room).
# Used as a rough budget proxy since CMS doesn't publish pricing.
#
# Source: CareScout (Genworth Financial) "Cost of Care Survey 2024",
# Monthly Median Costs table, "Nursing Home Care - Semi-Private Room" column.
# Survey conducted July-December 2024; monthly = annual rate / 12.
# PDF: https://assets.carescout.com/55da049c1f/282102.pdf (doc 282102 030425)
# Retrieved: 2026-06-06. Latest data: https://www.carescout.com/cost-of-care
STATE_MEDIAN_MONTHLY_COST: dict[str, int] = {
    "AL": 8152, "AK": 30371, "AZ": 7604, "AR": 7148, "CA": 11695,
    "CO": 10038, "CT": 15056, "DE": 14174, "FL": 10342, "GA": 8821,
    "HI": 15087, "ID": 10068, "IL": 7908, "IN": 8486, "IA": 8927,
    "KS": 7756, "KY": 8730, "LA": 7482, "ME": 12927, "MD": 12501,
    "MA": 14448, "MI": 10646, "MN": 12167, "MS": 9642, "MO": 6357,
    "MT": 9064, "NE": 8380, "NV": 11209, "NH": 12471, "NJ": 12380,
    "NM": 9764, "NY": 14722, "NC": 8821, "ND": 8882, "OH": 9034,
    "OK": 6448, "OR": 15817, "PA": 11832, "RI": 11406, "SC": 8958,
    "SD": 8821, "TN": 9125, "TX": 5475, "UT": 8365, "VT": 13688,
    "VA": 8669, "WA": 12714, "WV": 12471, "WI": 10068, "WY": 9916,
    "DC": 8167,
}
# USA national median, same source and column
NATIONAL_MEDIAN_MONTHLY_COST = 9277

# Cache
CACHE_DIR = "~/.dearnana/cache"
CACHE_TTL_HOURS = 24
