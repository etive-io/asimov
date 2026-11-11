"""
Commands for who an analysis's jobs are charged to (#181).
"""

import click

from asimov import accounting as charging
from asimov.context import active_ledger as ledger


def _analysis(subject, name):
    events = ledger.get_event(subject)
    if not events:
        raise click.ClickException(f"There is no subject called {subject!r}.")
    for analysis in events[0].productions:
        if analysis.name == name:
            return analysis
    raise click.ClickException(f"{subject} has no analysis called {name!r}.")


@click.group(help="Who an analysis's jobs are charged to.")
def accounting():
    """Group for the accounting commands."""


@accounting.command("show", help="Show who ANALYSIS of SUBJECT is charged to, and why.")
@click.argument("subject")
@click.argument("analysis")
def show(subject, analysis):
    """Show the accounting identity of an analysis."""
    found = _analysis(subject, analysis)
    from asimov.context import get_active_context

    context = get_active_context()
    entry, directory = charging.rules_for(getattr(context, "root", None))
    try:
        result = charging.resolve(ledger, found, entry, directory)
    except charging.AccountingError as error:
        raise click.ClickException(str(error))
    for key, value in result.to_dict().items():
        click.echo(f"{key:14} {value}")
    if directory is None:
        click.echo("(this project isn't served with groups, so its own settings apply)")


@accounting.command("hand-over", help="Make PERSON the requester of ANALYSIS of SUBJECT.")
@click.argument("subject")
@click.argument("analysis")
@click.argument("person")
@click.option("--accounting-name", default=None, help="The name PERSON is charged under, if not PERSON.")
@click.option("--reason", default=None, help="Why, for the record.")
def hand_over(subject, analysis, person, accounting_name, reason):
    """Hand an analysis over to someone else, who is then charged for it."""
    found = _analysis(subject, analysis)
    try:
        charging.hand_over(ledger, found, person, accounting=accounting_name, reason=reason)
    except charging.AccountingError as error:
        raise click.ClickException(str(error))
    click.echo(click.style("●", fg="green") + f" {subject}/{analysis} is now charged to {person}")
