"""Unit tests for the comparison table."""

from dearnana.comparison import build_comparison_table
from dearnana.models import Facility, RankedFacility


def _ranked(name: str, score: float, **overrides) -> RankedFacility:
    facility = Facility(
        ccn=name,
        name=name,
        address="1 Main St",
        city="Seattle",
        state="WA",
        zip_code="98101",
        overall_rating=4,
        **overrides,
    )
    return RankedFacility(
        facility=facility, distance_miles=2.5, composite_score=score, score_breakdown={}
    )


def test_table_has_header_and_one_row_per_facility():
    ranked = [_ranked("Home A", 88.0), _ranked("Home B", 74.0)]
    table = build_comparison_table(ranked)
    lines = table.splitlines()
    # header + divider + 2 data rows
    assert len(lines) == 4
    assert lines[0].startswith("| #")
    assert "Home A" in table and "Home B" in table


def test_abuse_flag_rendered():
    table = build_comparison_table([_ranked("Bad Home", 30.0, abuse_icon=True)])
    assert "⚠" in table


def test_independent_when_no_chain():
    table = build_comparison_table([_ranked("Solo Home", 50.0)])
    assert "Independent" in table


def test_empty_returns_empty_string():
    assert build_comparison_table([]) == ""
