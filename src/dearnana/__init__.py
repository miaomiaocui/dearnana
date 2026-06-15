"""DearNana - Find and rank nursing homes using CMS public data."""

from importlib.metadata import PackageNotFoundError, version as _pkg_version

try:
    __version__ = _pkg_version("dearnana")
except PackageNotFoundError:  # running from a source tree without an install
    __version__ = "0.0.0"

from dearnana.comparison import build_comparison_table
from dearnana.condition import NeedsProfile, build_measure_weights, parse_condition
from dearnana.errors import DataFetchError
from dearnana.export import load_watchlist, save_to_watchlist, to_csv, to_html
from dearnana.filters import filter_facilities
from dearnana.llm_advisor import build_advisor_prompt, generate_recommendation
from dearnana.models import Facility, RankedFacility, StateFacilities, UserInput
from dearnana.questionnaire import prompt_needs
from dearnana.ranker import (
    compute_composite_score,
    compute_measure_benchmarks,
    rank_facilities,
    score_condition_match,
)
from dearnana.report import build_data_report
from dearnana.geocode import geocode_address

__all__ = [
    "Facility",
    "RankedFacility",
    "StateFacilities",
    "UserInput",
    "NeedsProfile",
    "DataFetchError",
    "rank_facilities",
    "compute_composite_score",
    "compute_measure_benchmarks",
    "score_condition_match",
    "parse_condition",
    "build_measure_weights",
    "geocode_address",
    "build_data_report",
    "build_comparison_table",
    "build_advisor_prompt",
    "generate_recommendation",
    "filter_facilities",
    "prompt_needs",
    "to_csv",
    "to_html",
    "load_watchlist",
    "save_to_watchlist",
]
