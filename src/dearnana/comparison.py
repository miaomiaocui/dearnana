"""Side-by-side comparison table for ranked facilities (markdown, no AI).

Renders cleanly both in a terminal and inside the saved markdown report.
"""

from dearnana.models import RankedFacility

_HEADERS = [
    "#", "Facility", "Dist", "Score", "CMS", "Staffing", "Turnover",
    "Penalties", "Abuse", "Chain",
]


def _row(i: int, r: RankedFacility) -> list[str]:
    f = r.facility
    cms = f"{f.overall_rating}/5" if f.overall_rating > 0 else "n/r"
    staffing = f"{f.staffing_rating}/5" if f.staffing_rating > 0 else "n/r"
    turnover = f"{f.total_nursing_turnover:.0f}%" if f.total_nursing_turnover is not None else "—"
    penalties = str(f.number_of_penalties) if f.number_of_penalties else "0"
    abuse = "⚠" if f.abuse_icon else "—"
    chain = f.chain_name or "Independent"
    return [
        str(i),
        f.name,
        f"{r.distance_miles} mi",
        f"{r.composite_score}",
        cms,
        staffing,
        turnover,
        penalties,
        abuse,
        chain,
    ]


def build_comparison_table(ranked: list[RankedFacility]) -> str:
    """Markdown comparison table, one row per ranked facility."""
    if not ranked:
        return ""
    rows = [_row(i, r) for i, r in enumerate(ranked, start=1)]
    header = "| " + " | ".join(_HEADERS) + " |"
    divider = "| " + " | ".join("---" for _ in _HEADERS) + " |"
    body = ["| " + " | ".join(cell for cell in row) + " |" for row in rows]
    return "\n".join([header, divider, *body])
