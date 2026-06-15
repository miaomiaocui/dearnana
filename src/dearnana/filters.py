"""Pre-ranking facility filters.

Operate on raw Facility fields so they compose with everything downstream
(ranking, condition scoring). Shared by the CLI and the web backend.
"""

from dearnana.models import Facility


def filter_facilities(
    facilities: list[Facility],
    *,
    min_stars: int = 0,
    exclude_abuse: bool = False,
    exclude_special_focus: bool = False,
    sprinkler_only: bool = False,
    independent_only: bool = False,
) -> tuple[list[Facility], list[str]]:
    """Drop facilities failing any active filter.

    Returns (kept, notes) where notes describe how many were removed by each
    active filter (for user-facing messaging).
    """
    checks = [
        (min_stars > 0, lambda f: f.overall_rating >= min_stars,
         f"below {min_stars} CMS stars"),
        (exclude_abuse, lambda f: not f.abuse_icon, "abuse-flagged"),
        (exclude_special_focus, lambda f: not f.special_focus_status,
         "on CMS Special Focus list"),
        (sprinkler_only, lambda f: f.sprinkler_systems == "Yes",
         "without full sprinkler coverage"),
        (independent_only, lambda f: not f.chain_name, "chain-affiliated"),
    ]
    notes: list[str] = []
    for active, predicate, label in checks:
        if not active:
            continue
        before = len(facilities)
        facilities = [f for f in facilities if predicate(f)]
        removed = before - len(facilities)
        if removed:
            notes.append(f"{removed} {label}")
    return facilities, notes
