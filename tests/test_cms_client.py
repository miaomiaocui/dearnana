"""Unit tests for CMS client parsing, retries, and caching."""

import httpx
import pytest

from dearnana.cms_client import (
    _cache_path,
    _clean_text,
    _get_json,
    _parse_facility,
    _parse_state_rows,
    _safe_float_or_none,
)
from dearnana.errors import DataFetchError


def _provider_row(**overrides) -> dict:
    row = {
        "cms_certification_number_ccn": "505001",
        "provider_name": "Test Home",
        "provider_address": "1 Main St",
        "citytown": "Seattle",
        "state": "WA",
        "zip_code": "98101",
        "latitude": "47.6",
        "longitude": "-122.3",
        "overall_rating": "4",
        "health_inspection_rating": "3",
        "staffing_rating": "4",
        "total_nursing_staff_turnover": "45.5",
        "registered_nurse_turnover": "",
        "chain_name": "Test Chain",
        "chain_id": "C1",
        "number_of_facilities_in_chain": "12",
        "chain_average_overall_5star_rating": "2.3",
        "provider_changed_ownership_in_last_12_months": "Y",
        "abuse_icon": "N",
    }
    row.update(overrides)
    return row


class TestSafeFloatOrNone:
    def test_blank_is_none(self):
        assert _safe_float_or_none("") is None
        assert _safe_float_or_none(None) is None

    def test_invalid_is_none(self):
        assert _safe_float_or_none("abc") is None

    def test_valid(self):
        assert _safe_float_or_none("45.5") == 45.5


class TestParseFacility:
    def test_unrated_facility_kept(self):
        f = _parse_facility(_provider_row(overall_rating=""))
        assert f is not None
        assert f.overall_rating == 0

    def test_missing_coordinates_dropped(self):
        assert _parse_facility(_provider_row(latitude="")) is None

    def test_chain_fields(self):
        f = _parse_facility(_provider_row())
        assert f.chain_name == "Test Chain"
        assert f.chain_facility_count == 12
        assert f.chain_avg_overall == 2.3
        assert f.changed_ownership_12mo is True

    def test_turnover_none_when_blank(self):
        f = _parse_facility(_provider_row())
        assert f.total_nursing_turnover == 45.5
        assert f.rn_turnover is None

    def test_state_rows_counts(self):
        rows = [
            _provider_row(),
            _provider_row(overall_rating=""),
            _provider_row(latitude=""),
        ]
        result = _parse_state_rows(rows)
        assert len(result.facilities) == 2
        assert result.unrated_count == 1
        assert result.excluded_no_location == 1


class TestGetJsonRetry:
    def _client_with_responses(self, responses):
        calls = iter(responses)

        def handler(request):
            return next(calls)

        return httpx.Client(transport=httpx.MockTransport(handler))

    def test_retries_then_succeeds(self, mocker):
        mocker.patch("dearnana.cms_client.time.sleep")
        client = self._client_with_responses(
            [
                httpx.Response(500),
                httpx.Response(500),
                httpx.Response(200, json={"results": []}),
            ]
        )
        data = _get_json(client, "https://example.com/x", {})
        assert data == {"results": []}

    def test_persistent_failure_raises(self, mocker):
        mocker.patch("dearnana.cms_client.time.sleep")
        client = self._client_with_responses([httpx.Response(500)] * 3)
        with pytest.raises(DataFetchError):
            _get_json(client, "https://example.com/x", {})

    def test_client_error_no_retry(self, mocker):
        sleep = mocker.patch("dearnana.cms_client.time.sleep")
        client = self._client_with_responses([httpx.Response(404)])
        with pytest.raises(DataFetchError):
            _get_json(client, "https://example.com/x", {})
        sleep.assert_not_called()


class TestCache:
    def test_round_trip(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dearnana.cms_client.CACHE_DIR", str(tmp_path))
        from dearnana.cms_client import _read_cache, _write_cache

        assert _read_cache("missing") is None
        _write_cache("key", [{"a": 1}])
        assert _read_cache("key") == [{"a": 1}]

    def test_cache_path_traversal_blocked(self, tmp_path, monkeypatch):
        """A hostile CCN must not produce a path outside the cache dir."""
        monkeypatch.setattr("dearnana.cms_client.CACHE_DIR", str(tmp_path))
        hostile = "deficiencies_../../../../etc/passwd"
        path = _cache_path(hostile)
        assert path.resolve().parent == tmp_path.resolve()
        assert ".." not in path.name
        assert "/" not in path.name


class TestCleanText:
    def test_strips_control_chars(self):
        assert _clean_text("Evil\x1b[31mName\x00Home") == "Evil[31mNameHome"

    def test_none_and_empty(self):
        assert _clean_text(None) == ""
        assert _clean_text("") == ""

    def test_normal_text_unchanged(self):
        assert _clean_text("Covenant Shores Health Center") == "Covenant Shores Health Center"

    def test_parse_facility_cleans_name(self):
        f = _parse_facility(_provider_row(provider_name="Bad\x1b]0;pwned\x07 Home"))
        assert "\x1b" not in f.name
        assert "\x07" not in f.name
