"""DearNana CLI — find and rank nursing homes."""

import os
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
from dearnana.condition import build_measure_weights, describe_profile, parse_condition
from dearnana.config import (
    DEFAULT_RADIUS_MILES,
    DEFAULT_TOP_N,
    NATIONAL_MEDIAN_MONTHLY_COST,
    STATE_MEDIAN_MONTHLY_COST,
)
from dearnana.errors import DataFetchError
from dearnana.geocode import geocode_address
from dearnana.llm_advisor import generate_recommendation
from dearnana.models import RankedFacility
from dearnana.ranker import (
    compute_measure_benchmarks,
    rank_facilities,
    score_condition_match,
)


def _reports_dir() -> Path:
    override = os.environ.get("DEARNANA_REPORTS_DIR")
    if override:
        return Path(override)
    return Path.cwd() / "dearnana-reports"


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
            pct = d.get("percentile")
            better = f" (better than {round((1 - pct) * 100)}% of {f.state} facilities)" if pct is not None else ""
            lines.append(
                f"    {d['label']}: {d['value']:.1f}% vs state median "
                f"{d['state_median']:.1f}%{better}"
            )
            shown += 1
    for warning in r.chain_warnings:
        lines.append(f"    WARNING: {warning}")
    return "\n".join(lines)


@click.command()
@click.option("--address", required=True, help="Your address or the area to search near")
@click.option("--budget", required=True, type=float, help="Monthly budget in dollars")
@click.option("--condition", required=True, help="Description of your loved one's condition and care needs")
@click.option("--radius", default=DEFAULT_RADIUS_MILES, type=float, help="Search radius in miles")
@click.option("--top", "top_n", default=DEFAULT_TOP_N, type=int, help="Number of top results")
@click.option("--no-ai", is_flag=True, help="Skip AI recommendation (just show ranked list)")
def main(address: str, budget: float, condition: str, radius: float, top_n: int, no_ai: bool):
    """Find and rank nursing homes near you using CMS public data."""

    if not no_ai and not os.environ.get("ANTHROPIC_API_KEY"):
        click.echo(
            "Note: no ANTHROPIC_API_KEY found — continuing in data-only mode.\n"
            "  Ranking and keyword-based personalization still work; you just won't\n"
            "  get the AI-written recommendation report. To enable it, get a key at\n"
            "  https://console.anthropic.com and set ANTHROPIC_API_KEY (or put it in a .env file).\n"
        )

    # Step 1: Geocode
    click.echo(f"Geocoding: {address}")
    try:
        lat, lng, state = geocode_address(address)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)
    click.echo(f"  -> ({lat:.4f}, {lng:.4f}) in {state}")

    # Step 2: Parse care needs into a structured profile
    profile = parse_condition(condition, use_llm=not no_ai)
    if not profile.is_empty:
        source = "AI" if profile.source == "ai" else "keyword matching"
        click.echo(f"Personalizing for: {describe_profile(profile)} — parsed via {source}")
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

    # Step 7: Build the ranked list
    facility_blocks = [_format_facility_lines(i, r) for i, r in enumerate(ranked)]

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

    click.echo("\n--- DearNana Top {} ---\n".format(len(ranked)))
    for block in facility_blocks:
        click.echo(block + "\n")

    # Step 8: Generate detailed AI recommendation
    if no_ai:
        click.echo("(Skipping AI recommendation — use without --no-ai for a detailed report)")
    else:
        click.echo("Generating detailed recommendation report...\n")
        recommendation = generate_recommendation(
            ranked, condition, budget, budget_note, needs_summary=profile.summary
        )
        report_lines.append("## Detailed Recommendation\n")
        report_lines.append(recommendation)
        click.echo("--- DearNana Detailed Report ---\n")
        click.echo(recommendation)

    # Step 9: Save report
    reports_dir = _reports_dir()
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    city = ranked[0].facility.city.lower().replace(" ", "_") if ranked else "unknown"
    report_path = reports_dir / f"dearnana_{city}_{timestamp}.md"
    report_path.write_text("\n".join(report_lines))
    click.echo(f"\nReport saved to: {report_path}")


if __name__ == "__main__":
    main()
