"""Unit tests for CSV/HTML export and the local watchlist."""

import csv
import io

from dearnana.models import Facility, RankedFacility
from dearnana import export


def _ranked(ccn: str, name: str, score: float, **overrides) -> RankedFacility:
    facility = Facility(
        ccn=ccn,
        name=name,
        address="1 Main St",
        city="Seattle",
        state="WA",
        zip_code="98101",
        phone="2065551212",
        overall_rating=4,
        **overrides,
    )
    return RankedFacility(
        facility=facility, distance_miles=2.5, composite_score=score, score_breakdown={}
    )


def test_to_csv_round_trips_columns():
    ranked = [_ranked("1", "Home A", 88.0), _ranked("2", "Home B", 74.0)]
    rows = list(csv.reader(io.StringIO(export.to_csv(ranked))))
    assert rows[0][0] == "Rank"
    assert "Facility" in rows[0]
    assert len(rows) == 3  # header + 2 facilities
    assert rows[1][1] == "Home A"


def test_to_html_is_well_formed_table():
    html = export.to_html([_ranked("1", "Home A", 88.0)])
    assert html.startswith("<!DOCTYPE html>")
    assert "<table>" in html and "Home A" in html


def test_watchlist_append_dedupes_by_ccn(tmp_path, monkeypatch):
    monkeypatch.setattr(export, "WATCHLIST_PATH", tmp_path / "watchlist.json")

    added = export.save_to_watchlist([_ranked("AAA", "Home A", 88.0)])
    assert added == 1

    # Re-saving the same CCN plus a new one: only the new one counts as added.
    added = export.save_to_watchlist(
        [_ranked("AAA", "Home A", 90.0), _ranked("BBB", "Home B", 70.0)]
    )
    assert added == 1

    entries = export.load_watchlist()
    assert len(entries) == 2
    a = next(e for e in entries if e["ccn"] == "AAA")
    assert a["score"] == 90.0  # updated in place


def test_load_watchlist_missing_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(export, "WATCHLIST_PATH", tmp_path / "nope.json")
    assert export.load_watchlist() == []


def test_format_watchlist_empty_message():
    assert "empty" in export.format_watchlist([])
