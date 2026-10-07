"""
Commands for reading the project's audit trail (see #143).
"""

import json

import click

from asimov.audit import prov_document
from asimov.context import active_ledger as ledger

_DATES = ["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"]


@click.group(help="Read the record of who changed this project.")
def audit():
    """Group for the audit-trail commands."""


@audit.command(
    "show",
    help="Show what has been applied to this project, oldest first. "
    "Each filter given narrows the records shown.",
)
@click.option(
    "--target",
    "-t",
    default=None,
    help="An event, or event/analysis, or @project. Includes what is under it.",
)
@click.option(
    "--principal",
    "-p",
    default=None,
    help="Changes made by this person or agent, or by an agent acting for them.",
)
@click.option("--kind", "-k", default=None, help="The kind of document applied.")
@click.option("--since", type=click.DateTime(formats=_DATES), default=None, help="From this time (UTC).")
@click.option("--until", type=click.DateTime(formats=_DATES), default=None, help="Until this time (UTC).")
@click.option("--limit", "-n", type=click.IntRange(min=1), default=None, help="Only the most recent N.")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["table", "json", "prov"]),
    default="table",
    show_default=True,
    help="json includes what was applied; prov is W3C PROV (JSON-LD).",
)
def show(target, principal, kind, since, until, limit, output_format):
    """Show the audit log."""
    records = ledger.audit_log(
        target=target,
        principal=principal,
        kind=kind,
        since=since,
        until=until,
        limit=limit,
    )

    if output_format == "json":
        click.echo(json.dumps([record.to_dict() for record in records], indent=2, default=str))
        return
    if output_format == "prov":
        click.echo(json.dumps(prov_document(records), indent=2, default=str))
        return

    if not records:
        click.echo("There are no matching records.")
        return
    for record in records:
        click.echo(
            f"{record.id}\t{record.timestamp}\t{record.principal_obj}\t"
            f"{record.action} {record.kind} ({record.outcome})\t{record.target}"
        )
