"""Client for CMS Provider Data Catalog API."""

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from dearnana.config import (
    CACHE_DIR,
    CACHE_TTL_HOURS,
    CMS_API_BASE,
    HEALTH_DEFICIENCIES_DATASET,
    MDS_QM_DATASET,
    OWNERSHIP_DATASET,
    PENALTIES_DATASET,
    PROVIDER_INFO_DATASET,
)
from dearnana.errors import DataFetchError
from dearnana.models import Facility, StateFacilities

# MDS quality measure codes used for condition-aware ranking
MDS_MEASURE_CODES = {
    "401", "404", "406", "407", "408", "409", "410",
    "434", "451", "452", "479", "480", "481",
}

_RETRY_ATTEMPTS = 3
_RETRY_BACKOFF_SECONDS = 1.0


def _cache_path(key: str) -> Path:
    # Cache keys embed externally-sourced values (CCNs, state codes) that may
    # be caller-supplied (e.g. a web backend passing user input to
    # fetch_*_by_ccn). Restrict to a safe charset so a hostile value can
    # never traverse outside the cache directory.
    safe_key = re.sub(r"[^A-Za-z0-9_-]", "_", key)
    cache_dir = Path(CACHE_DIR).expanduser()
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{safe_key}.json"


def _read_cache(key: str) -> list[dict] | None:
    path = _cache_path(key)
    if not path.exists():
        return None
    age_hours = (time.time() - path.stat().st_mtime) / 3600
    if age_hours > CACHE_TTL_HOURS:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError, OSError):
        # A corrupted or partially-written cache file (interrupted write,
        # full disk, etc.) must not brick the tool. Treat it as a cache miss
        # and remove the bad file so the next run refetches cleanly.
        try:
            path.unlink()
        except OSError:
            pass
        return None


def _write_cache(key: str, data: list[dict]) -> None:
    # Write atomically: a crash mid-write leaves the previous cache (or no
    # cache) intact rather than a truncated file that _read_cache must heal.
    path = _cache_path(key)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp, path)


def _clean_text(val: str | None) -> str:
    """Strip control characters from externally-sourced text.

    CMS strings end up in terminal output, markdown reports, and LLM
    prompts; control characters could smuggle ANSI escape sequences.
    """
    if not val:
        return ""
    return re.sub(r"[\x00-\x1f\x7f]", "", val)


def _safe_float(val: str | None, default: float = 0.0) -> float:
    if not val or val == "":
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _safe_float_or_none(val: str | None) -> float | None:
    if not val or val == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _safe_int(val: str | None, default: int = 0) -> int:
    if not val or val == "":
        return default
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default


def _safe_int_or_none(val: str | None) -> int | None:
    if not val or val == "":
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def _make_client() -> httpx.Client:
    return httpx.Client(timeout=30, transport=httpx.HTTPTransport(retries=2))


def _get_json(client: httpx.Client, url: str, params: dict) -> dict:
    """GET with retry/backoff on transient failures.

    Retries on connection errors and 429/5xx responses. Raises DataFetchError
    with a user-facing message after the final attempt fails.
    """
    last_error: Exception | None = None
    for attempt in range(_RETRY_ATTEMPTS):
        try:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            last_error = e
            status = e.response.status_code
            if status != 429 and status < 500:
                # Client error — retrying won't help
                break
        except (httpx.TransportError, json.JSONDecodeError) as e:
            last_error = e
        if attempt < _RETRY_ATTEMPTS - 1:
            time.sleep(_RETRY_BACKOFF_SECONDS * (2 ** attempt))
    if isinstance(last_error, httpx.HTTPStatusError):
        status = last_error.response.status_code
        if status != 429 and status < 500:
            # Not a connectivity problem — the endpoint answered with a client
            # error (e.g. a renamed/removed CMS dataset id), which retrying or a
            # better connection won't fix.
            raise DataFetchError(
                f"The CMS data API returned HTTP {status} for {url}. "
                "The dataset may have been moved or renamed — check for a newer "
                "version of DearNana."
            )
    raise DataFetchError(
        f"Could not reach the CMS data API ({last_error}). "
        "Check your internet connection and try again in a few minutes."
    )


def _fetch_all_pages(
    client: httpx.Client,
    dataset: str,
    conditions: dict,
    limit: int = 500,
    max_pages: int = 200,
) -> list[dict]:
    """Paginate through a CMS datastore query with the given conditions.

    max_pages bounds the loop so a misbehaving endpoint can't make us
    fetch forever (200 pages x 500 rows covers every per-state dataset
    with a wide margin).
    """
    url = f"{CMS_API_BASE}/{dataset}/0"
    all_rows: list[dict] = []
    offset = 0
    for _ in range(max_pages):
        params = {"limit": limit, "offset": offset, **conditions}
        data = _get_json(client, url, params)
        results = data.get("results", [])
        all_rows.extend(results)
        if len(results) < limit:
            break
        offset += limit
    return all_rows


def _state_conditions(state: str) -> dict:
    return {
        "conditions[0][property]": "state",
        "conditions[0][value]": state,
        "conditions[0][operator]": "=",
    }


def _ccn_conditions(ccn: str) -> dict:
    return {
        "conditions[0][property]": "cms_certification_number_ccn",
        "conditions[0][value]": ccn,
        "conditions[0][operator]": "=",
    }


def _parse_facility(row: dict) -> Facility | None:
    """Parse a CMS API row into a Facility model.

    Returns None only when the facility has no usable coordinates (it cannot
    be distance-ranked). Unrated facilities are kept and scored neutrally.
    """
    lat = _safe_float(row.get("latitude"))
    lng = _safe_float(row.get("longitude"))
    if lat == 0.0 or lng == 0.0:
        return None

    return Facility(
        ccn=_clean_text(row.get("cms_certification_number_ccn")),
        name=_clean_text(row.get("provider_name")),
        address=_clean_text(row.get("provider_address")),
        city=_clean_text(row.get("citytown")),
        state=_clean_text(row.get("state")),
        zip_code=_clean_text(row.get("zip_code")),
        latitude=lat,
        longitude=lng,
        phone=_clean_text(row.get("telephone_number")),
        ownership_type=_clean_text(row.get("ownership_type")),
        number_of_beds=_safe_int(row.get("number_of_certified_beds")),
        average_residents_per_day=_safe_float(row.get("average_number_of_residents_per_day")),
        overall_rating=_safe_int(row.get("overall_rating")),
        health_inspection_rating=_safe_int(row.get("health_inspection_rating")),
        qm_rating=_safe_int(row.get("qm_rating")),
        staffing_rating=_safe_int(row.get("staffing_rating")),
        total_nurse_staffing_hours=_safe_float(
            row.get("reported_total_nurse_staffing_hours_per_resident_per_day")
        ),
        rn_staffing_hours=_safe_float(
            row.get("reported_rn_staffing_hours_per_resident_per_day")
        ),
        total_nursing_turnover=_safe_float_or_none(row.get("total_nursing_staff_turnover")),
        rn_turnover=_safe_float_or_none(row.get("registered_nurse_turnover")),
        number_of_fines=_safe_int(row.get("number_of_fines")),
        total_fines_dollars=_safe_float(row.get("total_amount_of_fines_in_dollars")),
        number_of_penalties=_safe_int(row.get("total_number_of_penalties")),
        abuse_icon=row.get("abuse_icon", "N") == "Y",
        sprinkler_systems=_clean_text(row.get("automatic_sprinkler_systems_in_all_required_areas")),
        in_hospital=row.get("provider_resides_in_hospital", "N") == "Y",
        continuing_care=row.get("continuing_care_retirement_community", "N") == "Y",
        special_focus_status=_clean_text(row.get("special_focus_status")),
        chain_name=_clean_text(row.get("chain_name")),
        chain_id=_clean_text(row.get("chain_id")),
        chain_facility_count=_safe_int_or_none(row.get("number_of_facilities_in_chain")),
        chain_avg_overall=_safe_float_or_none(row.get("chain_average_overall_5star_rating")),
        chain_avg_health_inspection=_safe_float_or_none(
            row.get("chain_average_health_inspection_rating")
        ),
        chain_avg_staffing=_safe_float_or_none(row.get("chain_average_staffing_rating")),
        chain_avg_qm=_safe_float_or_none(row.get("chain_average_qm_rating")),
        changed_ownership_12mo=row.get("provider_changed_ownership_in_last_12_months", "N") == "Y",
    )


def _parse_state_rows(rows: list[dict]) -> StateFacilities:
    facilities = []
    excluded = 0
    unrated = 0
    for row in rows:
        f = _parse_facility(row)
        if f is None:
            excluded += 1
            continue
        if f.overall_rating == 0:
            unrated += 1
        facilities.append(f)
    return StateFacilities(
        facilities=facilities,
        excluded_no_location=excluded,
        unrated_count=unrated,
    )


def fetch_state_facilities(state: str) -> StateFacilities:
    """Fetch all nursing home facilities for a state, with exclusion counts.

    Uses local file cache with configurable TTL.
    """
    cache_key = f"providers_{state}"
    cached = _read_cache(cache_key)
    if cached is not None:
        return _parse_state_rows(cached)

    with _make_client() as client:
        all_rows = _fetch_all_pages(client, PROVIDER_INFO_DATASET, _state_conditions(state))

    _write_cache(cache_key, all_rows)
    return _parse_state_rows(all_rows)


def fetch_facilities_by_state(state: str) -> list[Facility]:
    """Backward-compatible wrapper returning just the facility list."""
    return fetch_state_facilities(state).facilities


def fetch_mds_measures_by_state(state: str) -> dict[str, dict[str, float]]:
    """Fetch MDS quality measure scores for all facilities in a state.

    Returns {ccn: {measure_code: four_quarter_average_score}} for the measure
    codes used in condition-aware ranking. Lower scores are better for all
    of these measures.
    """
    cache_key = f"mds_{state}"
    rows = _read_cache(cache_key)
    if rows is None:
        with _make_client() as client:
            rows = _fetch_all_pages(client, MDS_QM_DATASET, _state_conditions(state))
        _write_cache(cache_key, rows)

    measures: dict[str, dict[str, float]] = {}
    for row in rows:
        code = row.get("measure_code", "")
        if code not in MDS_MEASURE_CODES:
            continue
        score = _safe_float_or_none(row.get("four_quarter_average_score"))
        if score is None:
            continue
        ccn = row.get("cms_certification_number_ccn", "")
        measures.setdefault(ccn, {})[code] = score
    return measures


def _fetch_by_ccn_cached(client: httpx.Client, dataset: str, cache_prefix: str, ccn: str) -> list[dict]:
    """Fetch raw rows for one CCN from a dataset, with per-CCN file caching."""
    cache_key = f"{cache_prefix}_{ccn}"
    cached = _read_cache(cache_key)
    if cached is not None:
        return cached
    url = f"{CMS_API_BASE}/{dataset}/0"
    params = {"limit": 100, "offset": 0, **_ccn_conditions(ccn)}
    data = _get_json(client, url, params)
    rows = data.get("results", [])
    _write_cache(cache_key, rows)
    return rows


def _map_deficiencies(rows: list[dict]) -> list[dict]:
    return [
        {
            "date": _clean_text(r.get("survey_date")),
            "category": _clean_text(r.get("deficiency_category")),
            "description": _clean_text(r.get("deficiency_description")),
            "severity": _clean_text(r.get("scope_severity_code")),
            "corrected": _clean_text(r.get("deficiency_corrected")),
            "correction_date": _clean_text(r.get("correction_date")),
        }
        for r in rows
    ]


def _map_penalties(rows: list[dict]) -> list[dict]:
    return [
        {
            "date": _clean_text(r.get("penalty_date")),
            "type": _clean_text(r.get("penalty_type")),
            "fine_amount": _safe_float(r.get("fine_amount")),
            "denial_days": _safe_int(r.get("payment_denial_length_in_days")),
        }
        for r in rows
    ]


def _map_ownership(rows: list[dict]) -> list[dict]:
    return [
        {
            "owner_name": _clean_text(r.get("owner_name")),
            "owner_type": _clean_text(r.get("owner_type")),
            "role": _clean_text(r.get("role_played_by_owner_or_manager_in_facility")),
            "ownership_percentage": _clean_text(r.get("ownership_percentage")),
            "association_date": _clean_text(r.get("association_date")),
        }
        for r in rows
    ]


def fetch_deficiencies_by_ccn(ccn: str) -> list[dict]:
    """Fetch health deficiency citations for a specific facility."""
    with _make_client() as client:
        return _map_deficiencies(
            _fetch_by_ccn_cached(client, HEALTH_DEFICIENCIES_DATASET, "deficiencies", ccn)
        )


def fetch_penalties_by_ccn(ccn: str) -> list[dict]:
    """Fetch penalty records for a specific facility."""
    with _make_client() as client:
        return _map_penalties(
            _fetch_by_ccn_cached(client, PENALTIES_DATASET, "penalties", ccn)
        )


def fetch_ownership_by_ccn(ccn: str) -> list[dict]:
    """Fetch owner/manager records for a specific facility."""
    with _make_client() as client:
        return _map_ownership(
            _fetch_by_ccn_cached(client, OWNERSHIP_DATASET, "ownership", ccn)
        )


_ENRICH_SOURCES = [
    ("deficiencies", HEALTH_DEFICIENCIES_DATASET, _map_deficiencies),
    ("penalties", PENALTIES_DATASET, _map_penalties),
    ("ownership", OWNERSHIP_DATASET, _map_ownership),
]


def enrich_facilities(ccns: list[str]) -> dict[str, dict]:
    """Fetch deficiencies, penalties, and ownership for a list of CCNs.

    Fetches run in parallel; an individual failure leaves that entry as None
    rather than aborting the batch.

    Returns {ccn: {"deficiencies": [...], "penalties": [...], "ownership": [...]}}
    """
    unique_ccns = list(dict.fromkeys(ccns))
    result: dict[str, dict] = {ccn: {} for ccn in unique_ccns}

    def task(ccn: str, key: str, dataset: str, mapper) -> None:
        try:
            rows = _fetch_by_ccn_cached(client, dataset, key, ccn)
            result[ccn][key] = mapper(rows)
        except DataFetchError:
            result[ccn][key] = None

    with _make_client() as client:
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [
                pool.submit(task, ccn, key, dataset, mapper)
                for ccn in unique_ccns
                for key, dataset, mapper in _ENRICH_SOURCES
            ]
            for fut in futures:
                fut.result()

    return result
