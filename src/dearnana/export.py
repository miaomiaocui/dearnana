"""Token-free exports and a local watchlist.

CSV/HTML exports let families share results; the watchlist persists saved picks
across runs under ~/.dearnana (the same root the CMS cache uses).
"""

import csv
import html
import io
import json
from datetime import datetime
from pathlib import Path

from dearnana.models import RankedFacility

WATCHLIST_PATH = Path("~/.dearnana/watchlist.json").expanduser()

_EXPORT_COLUMNS = [
    ("rank", "Rank"),
    ("name", "Facility"),
    ("address", "Address"),
    ("city", "City"),
    ("state", "State"),
    ("zip_code", "ZIP"),
    ("phone", "Phone"),
    ("distance_miles", "Distance (mi)"),
    ("composite_score", "DearNana Score"),
    ("overall_rating", "CMS Overall"),
    ("staffing_rating", "Staffing"),
    ("total_nursing_turnover", "Turnover %"),
    ("number_of_penalties", "Penalties"),
    ("abuse_icon", "Abuse Flag"),
    ("chain_name", "Chain"),
]


def _record(i: int, r: RankedFacility) -> dict:
    f = r.facility
    return {
        "rank": i,
        "name": f.name,
        "address": f.address,
        "city": f.city,
        "state": f.state,
        "zip_code": f.zip_code,
        "phone": f.phone,
        "distance_miles": r.distance_miles,
        "composite_score": r.composite_score,
        "overall_rating": f.overall_rating,
        "staffing_rating": f.staffing_rating,
        "total_nursing_turnover": f.total_nursing_turnover if f.total_nursing_turnover is not None else "",
        "number_of_penalties": f.number_of_penalties,
        "abuse_icon": "yes" if f.abuse_icon else "no",
        "chain_name": f.chain_name or "Independent",
    }


def to_csv(ranked: list[RankedFacility]) -> str:
    """Render ranked facilities as CSV text."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([label for _, label in _EXPORT_COLUMNS])
    for i, r in enumerate(ranked, start=1):
        rec = _record(i, r)
        writer.writerow([rec[key] for key, _ in _EXPORT_COLUMNS])
    return buf.getvalue()


def to_html(ranked: list[RankedFacility]) -> str:
    """Render ranked facilities as a standalone HTML table."""
    head = (
        "<thead><tr>"
        + "".join(f"<th>{html.escape(label)}</th>" for _, label in _EXPORT_COLUMNS)
        + "</tr></thead>"
    )
    rows = []
    for i, r in enumerate(ranked, start=1):
        rec = _record(i, r)
        cells = "".join(
            f"<td>{html.escape(str(rec[key]))}</td>" for key, _ in _EXPORT_COLUMNS
        )
        rows.append(f"<tr>{cells}</tr>")
    return (
        "<!DOCTYPE html>\n<html><head><meta charset='utf-8'>"
        "<title>DearNana results</title>"
        "<style>body{font-family:sans-serif}table{border-collapse:collapse}"
        "th,td{border:1px solid #ccc;padding:6px 10px;text-align:left}"
        "th{background:#f3f3f3}</style></head><body>"
        "<h1>DearNana — nursing home comparison</h1>"
        f"<table>{head}<tbody>{''.join(rows)}</tbody></table>"
        "</body></html>"
    )


def load_watchlist() -> list[dict]:
    """Read the saved watchlist; returns [] if none or unreadable."""
    if not WATCHLIST_PATH.exists():
        return []
    try:
        data = json.loads(WATCHLIST_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return data if isinstance(data, list) else []


def save_to_watchlist(ranked: list[RankedFacility]) -> int:
    """Append the ranked facilities to the watchlist, de-duped by CCN.

    Re-saving a facility updates its score/date in place. Returns the number of
    new (previously unseen) facilities added.
    """
    existing = load_watchlist()
    by_ccn = {e.get("ccn"): e for e in existing}
    today = datetime.now().strftime("%Y-%m-%d")
    added = 0
    for r in ranked:
        f = r.facility
        if f.ccn not in by_ccn:
            added += 1
        by_ccn[f.ccn] = {
            "ccn": f.ccn,
            "name": f.name,
            "city": f.city,
            "state": f.state,
            "score": r.composite_score,
            "phone": f.phone,
            "saved": today,
        }
    WATCHLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    WATCHLIST_PATH.write_text(
        json.dumps(list(by_ccn.values()), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return added


def format_watchlist(entries: list[dict]) -> str:
    """Plain markdown table of saved watchlist entries."""
    if not entries:
        return "Your watchlist is empty. Run a search with --save-watchlist to add picks."
    headers = ["Facility", "City", "State", "Score", "Phone", "Saved"]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for e in sorted(entries, key=lambda e: e.get("score", 0), reverse=True):
        lines.append(
            "| "
            + " | ".join(
                str(e.get(k, ""))
                for k in ("name", "city", "state", "score", "phone", "saved")
            )
            + " |"
        )
    return "\n".join(lines)
