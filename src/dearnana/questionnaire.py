"""Interactive, deterministic care-needs builder — no AI, no tokens.

Walks the family through the fixed need categories with a yes/no + severity
prompt and builds a NeedsProfile directly. This replaces the LLM parse step for
users without an API key, and is more reliable than keyword matching because the
family confirms each need explicitly.
"""

import click

from dearnana.condition import CATEGORY_LABELS, Need, NeedsProfile

# Severity choice -> relative weight (matches the 0-1 weight the LLM path emits).
_SEVERITY_WEIGHTS = {"1": 0.4, "2": 0.7, "3": 1.0}
_SEVERITY_LABELS = {"1": "mild", "2": "moderate", "3": "primary concern"}


def prompt_needs(echo=click.echo, confirm=click.confirm, prompt=click.prompt) -> NeedsProfile:
    """Interactively build a NeedsProfile. The prompt callables are injectable for tests."""
    echo(
        "\nLet's identify your loved one's care needs. "
        "Answer a few quick questions (no AI, nothing leaves your computer).\n"
    )
    needs: list[Need] = []
    for category, label in CATEGORY_LABELS.items():
        if not confirm(f"Is {label} a concern?", default=False):
            continue
        severity = prompt(
            "  How significant? 1=mild, 2=moderate, 3=primary concern",
            type=click.Choice(["1", "2", "3"]),
            default="2",
            show_choices=False,
        )
        needs.append(
            Need(
                category=category,
                weight=_SEVERITY_WEIGHTS[severity],
                rationale=f"{_SEVERITY_LABELS[severity]} (entered interactively)",
            )
        )

    if not needs:
        echo("No specific needs selected — using standard quality ranking.")
        return NeedsProfile(source="interactive")

    summary = ", ".join(
        f"{CATEGORY_LABELS[n.category]} ({_severity_word(n.weight)})" for n in needs
    )
    return NeedsProfile(needs=needs, summary=summary, source="interactive")


def _severity_word(weight: float) -> str:
    if weight >= 1.0:
        return "primary concern"
    if weight >= 0.7:
        return "moderate"
    return "mild"
