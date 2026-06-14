"""DearNana CLI — find and rank nursing homes."""

import os
import re
from datetime import datetime
from pathlib import Path

import click
from dotenv import load_dotenv

load_dotenv()

from dearnana.cms_client import (
    enrich_facilities,
    fetch_mds_measures_by_state,
    fetch_state_facilities,
)
from dearnana.comparison import build_comparison_table
from dearnana.condition import build_measure_weights, describe_profile, parse_condition
from dearnana.config import (
    DEFAULT_RADIUS_MILES,
    DEFAULT_TOP_N,
    NATIONAL_MEDIAN_MONTHLY_COST,
    STATE_MEDIAN_MONTHLY_COST,
)
from dearnana.errors import DataFetchError
from dearnana.export import (
    format_watchlist,
    load_watchlist,
    save_to_watchlist,
    to_csv,
    to_html,
)
from dearnana.geocode import geocode_address
from dearnana.llm_advisor import generate_recommendation
from dearnana.models import Facility, RankedFacility
from dearnana.questionnaire import prompt_needs
from dearnana.ranker import (
    compute_measure_benchmarks,
    rank_facilities,
    score_condition_match,
)
from dearnana.report import build_data_report, percentile_phrase


def _reports_dir() -> Path:
    override = os.environ.get("DEARNANA_REPORTS_DIR")
    if override:
        return Path(override)
    return Path.cwd() / "dearnana-reports"


def _apply_filters(
    facilities: list[Facility],
    min_stars: int,
    exclude_abuse: bool,
    exclude_special_focus: bool,
    sprinkler_only: bool,
    independent_only: bool,
) -> tuple[list[Facility], list[str]]:
    """Drop facilities failing any active filter. Returns (kept, drop notes)."""
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


def _format_facility_lines(i: int, r: RankedFacility) -> str:
    f = r.facility
    rating = f"{f.overall_rating}/5" if f.overall_rating > 0 else "not yet rated"
    lines = [
        f"#{i+1}. {f.name}",
        f"    {f.address}, {f.city}, {f.state} {f.zip_code}",
        f"    {r.distance_miles} mi | Score: {r.composite_score}/100 | "
        f"CMS: {rating} | Phone: {f.phone}",
    ]
    if f.chain_name:
        chain = f"    Chain: {f.chain_name}"
        if f.chain_facility_count:
            chain += f" ({f.chain_facility_count} facilities"
            if f.chain_avg_overall is not None:
                chain += f", avg {f.chain_avg_overall:.1f}/5"
            chain += ")"
        lines.append(chain)
    if r.condition_details:
        shown = 0
        for d in r.condition_details:
            if d.get("value") is None or shown >= 2:
                continue
            median = d.get("state_median")
            if median is None:
                # Thin benchmark — no usable state median/percentile
                lines.append(f"    {d['label']}: {d['value']:.1f}% (state benchmark unavailable)")
                shown += 1
                continue
            pct = d.get("percentile")
            better = f" ({percentile_phrase(pct)} of {f.state} facilities)" if pct is not None else ""
            lines.append(
                f"    {d['label']}: {d['value']:.1f}% vs state median {median:.1f}%{better}"
            )
            shown += 1
    for warning in r.chain_warnings:
        lines.append(f"    WARNING: {warning}")
    return "\n".join(lines)


@click.command()
@click.option("--address", help="Your address or the area to search near")
@click.option("--budget", type=float, help="Monthly budget in dollars")
@click.option("--condition", help="Description of your loved one's condition and care needs")
@click.option("--interactive", is_flag=True, help="Answer guided questions to build the needs profile (no AI)")
@click.option("--radius", default=DEFAULT_RADIUS_MILES, type=click.FloatRange(min=0, min_open=True), help="Search radius in miles")
@click.option("--top", "top_n", default=DEFAULT_TOP_N, type=click.IntRange(min=1), help="Number of top results")
@click.option("--no-ai", is_flag=True, help="Skip AI recommendation (rule-based report instead)")
@click.option("--min-stars", default=0, type=click.IntRange(0, 5), help="Only include facilities with at least this CMS overall rating")
@click.option("--exclude-abuse", is_flag=True, help="Exclude facilities flagged for abuse/neglect")
@click.option("--exclude-special-focus", is_flag=True, help="Exclude CMS Special Focus facilities")
@click.option("--sprinkler-only", is_flag=True, help="Only include facilities with full sprinkler coverage")
@click.option("--independent-only", is_flag=True, help="Exclude chain-affiliated facilities")
@click.option("--export", "export_format", type=click.Choice(["csv", "html"]), help="Also write results as CSV or HTML")
@click.option("--save-watchlist", is_flag=True, help="Save the top results to your local watchlist")
@click.option("--show-watchlist", is_flag=True, help="Print your saved watchlist and exit")
def main(
    address: str | None,
    budget: float | None,
    condition: str | None,
    interactive: bool,
    radius: float,
    top_n: int,
    no_ai: bool,
    min_stars: int,
    exclude_abuse: bool,
    exclude_special_focus: bool,
    sprinkler_only: bool,
    independent_only: bool,
    export_format: str | None,
    save_watchlist: bool,
    show_watchlist: bool,
):
    """Find and rank nursing homes near you using CMS public data."""

    if show_watchlist:
        click.echo(format_watchlist(load_watchlist()))
        return

    # address/budget are required for a search (kept optional so --show-watchlist
    # works without them).
    missing = [name for name, val in (("--address", address), ("--budget", budget)) if val is None]
    if missing:
        raise click.UsageError(f"Missing required option(s): {', '.join(missing)}")
    if not interactive and not condition:
        raise click.UsageError("Provide --condition, or use --interactive to answer guided questions.")

    provider = os.environ.get("DEARNANA_LLM_PROVIDER", "anthropic").strip().lower()
    if not no_ai and provider == "anthropic" and not os.environ.get("ANTHROPIC_API_KEY"):
        click.echo(
            "Note: no ANTHROPIC_API_KEY found — continuing in data-only mode.\n"
            "  You still get the full quality ranking and a detailed rule-based\n"
            "  report; you just won't get the AI-written version. To enable it, get\n"
            "  a key at https://console.anthropic.com and set ANTHROPIC_API_KEY (or\n"
            "  put it in a .env file), or run a local model: install Ollama\n"
            "  (https://ollama.com) and set DEARNANA_LLM_PROVIDER=ollama.\n"
        )

    # Step 1: Geocode
    click.echo(f"Geocoding: {address}")
    try:
        lat, lng, state = geocode_address(address)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)
    click.echo(f"  -> ({lat:.4f}, {lng:.4f}) in {state}")

    # Step 2: Build the care-needs profile (interactive questionnaire or parse)
    if interactive:
        profile = prompt_needs()
        if not condition:
            condition = profile.summary or "(needs entered interactively)"
    else:
        profile = parse_condition(condition, use_llm=not no_ai)

    if not profile.is_empty:
        source = {"ai": "AI", "interactive": "your answers"}.get(
            profile.source, "keyword matching"
        )
        click.echo(f"Personalizing for: {describe_profile(profile)} — via {source}")
    else:
        click.echo("No specific care needs recognized — using standard quality ranking.")

    # Step 3: Fetch CMS data
    click.echo(f"Fetching nursing homes in {state}...")
    try:
        result = fetch_state_facilities(state)
    except DataFetchError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)
    facilities = result.facilities
    notes = []
    if result.excluded_no_location:
        notes.append(f"{result.excluded_no_location} excluded: missing location")
    if result.unrated_count:
        notes.append(f"{result.unrated_count} not yet rated by CMS")
    suffix = f" ({'; '.join(notes)})" if notes else ""
    click.echo(f"  -> {len(facilities)} facilities found{suffix}")

    if not facilities:
        click.echo("No facilities found for this state.", err=True)
        raise SystemExit(1)

    # Step 3b: Apply user filters
    facilities, filter_notes = _apply_filters(
        facilities, min_stars, exclude_abuse, exclude_special_focus,
        sprinkler_only, independent_only,
    )
    if filter_notes:
        click.echo(f"  Filters removed: {'; '.join(filter_notes)} -> {len(facilities)} remain")
    if not facilities:
        click.echo("No facilities left after filtering. Loosen the filters and try again.", err=True)
        raise SystemExit(1)

    # Step 4: Condition-specific quality measures (skipped when no needs found)
    condition_scores = None
    if not profile.is_empty:
        measure_weights = build_measure_weights(profile)
        if measure_weights:
            click.echo(f"Fetching care quality measures for {state}...")
            try:
                mds = fetch_mds_measures_by_state(state)
            except DataFetchError:
                click.echo(
                    "  Warning: could not fetch quality measures — "
                    "ranking without condition component.",
                    err=True,
                )
                mds = {}
            if mds:
                benchmarks = compute_measure_benchmarks(mds)
                condition_scores = {
                    ccn: score_condition_match(facility_mds, measure_weights, benchmarks)
                    for ccn, facility_mds in mds.items()
                }

    vulnerable = bool(profile.categories() & {"dementia", "mental_health"})

    # Step 5: Rank
    click.echo(f"Ranking within {radius} miles...")
    ranked = rank_facilities(
        facilities,
        lat,
        lng,
        radius_miles=radius,
        top_n=top_n,
        condition_scores=condition_scores,
        vulnerable=vulnerable,
    )

    if not ranked:
        click.echo(f"No facilities found within {radius} miles. Try a larger radius.", err=True)
        raise SystemExit(1)

    click.echo(f"  -> {len(ranked)} facilities ranked\n")

    # Budget note
    state_median = STATE_MEDIAN_MONTHLY_COST.get(state, NATIONAL_MEDIAN_MONTHLY_COST)
    budget_note = ""
    if budget < state_median * 0.7:
        budget_note = (
            f"Note: Your budget (${budget:,.0f}/mo) is below the {state} median "
            f"for semi-private rooms (~${state_median:,}/mo). Options may be limited. "
            "Contact facilities directly for current pricing — many accept Medicaid."
        )
        click.echo(f"Budget warning: {budget_note}\n")

    # Step 6: Enrich top results with deficiency/penalty/ownership details
    click.echo("Fetching detailed inspection and ownership data for top picks...")
    try:
        enrichment = enrich_facilities([r.facility.ccn for r in ranked])
    except DataFetchError:
        click.echo("  Warning: enrichment unavailable — continuing without it.", err=True)
        enrichment = {}
    for r in ranked:
        data = enrichment.get(r.facility.ccn, {})
        r.deficiencies = data.get("deficiencies")
        r.penalties = data.get("penalties")
        r.ownership = data.get("ownership")

    # Step 7: Build the ranked list + comparison table
    facility_blocks = [_format_facility_lines(i, r) for i, r in enumerate(ranked)]
    comparison_table = build_comparison_table(ranked)

    report_lines = ["# DearNana Report"]
    report_lines.append(f"**Search:** {address}")
    report_lines.append(f"**Budget:** ${budget:,.0f}/mo")
    report_lines.append(f"**Condition:** {condition}")
    if not profile.is_empty:
        report_lines.append(f"**Personalized for:** {describe_profile(profile)}")
    report_lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    if budget_note:
        report_lines.append(f"\n> {budget_note}")
    report_lines.append(f"\n## Top {len(ranked)} Nursing Homes\n")
    report_lines.extend(f"{block}\n" for block in facility_blocks)
    report_lines.append("## At a Glance\n")
    report_lines.append(comparison_table + "\n")

    click.echo("\n--- DearNana Top {} ---\n".format(len(ranked)))
    for block in facility_blocks:
        click.echo(block + "\n")
    click.echo("At a glance:\n")
    click.echo(comparison_table + "\n")

    # Step 8: Detailed recommendation (AI when available, otherwise rule-based)
    if no_ai:
        recommendation = build_data_report(
            ranked, condition, budget, budget_note, needs_summary=profile.summary
        )
        heading = "## Detailed Recommendation (rule-based)\n"
    else:
        click.echo("Generating detailed recommendation report...\n")
        recommendation = generate_recommendation(
            ranked, condition, budget, budget_note, needs_summary=profile.summary
        )
        heading = "## Detailed Recommendation\n"
    report_lines.append(heading)
    report_lines.append(recommendation)
    click.echo("--- DearNana Detailed Report ---\n")
    click.echo(recommendation)

    # Step 9: Save report
    reports_dir = _reports_dir()
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # City comes from external CMS data — restrict to a safe filename charset
    city = re.sub(r"[^a-z0-9_-]", "_", ranked[0].facility.city.lower().replace(" ", "_")) or "unknown"
    stem = f"dearnana_{city}_{timestamp}"
    report_path = reports_dir / f"{stem}.md"
    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    click.echo(f"\nReport saved to: {report_path}")

    # Step 10: Optional export + watchlist
    if export_format:
        content = to_csv(ranked) if export_format == "csv" else to_html(ranked)
        export_path = reports_dir / f"{stem}.{export_format}"
        export_path.write_text(content, encoding="utf-8")
        click.echo(f"Exported {export_format.upper()} to: {export_path}")

    if save_watchlist:
        added = save_to_watchlist(ranked)
        click.echo(f"Saved to watchlist ({added} new) — view anytime with: dearnana --show-watchlist")


if __name__ == "__main__":
    main()
