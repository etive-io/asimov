"""
Commands for a group of analyses which a strategy made, and for re-running an
analysis and what depends on it (#234).

Every command that changes anything says what it would change, takes
``--dry-run`` to stop there, and asks before it goes on unless given ``--yes``.
"""
import click

from asimov import groups
from asimov.context import active_ledger as ledger
from asimov.groups import GroupError


@click.group(help="Commands for analyses, and for the groups which a strategy makes.")
def analysis():
    """Group for the analysis commands."""


def _show(members, limit=25):
    for member in members[:limit]:
        click.echo(f"  {member.label}  [{member.status}]")
    if len(members) > limit:
        click.echo(f"  ... and {len(members) - limit} more")


def _confirm(what, members, dry_run, yes):
    """
    Say what would change. Returns whether to go ahead.
    """
    if not members:
        click.echo("Nothing to do.")
        return False
    click.echo(f"{what} {len(members)} {'analysis' if len(members) == 1 else 'analyses'}:")
    _show(members)
    if dry_run:
        click.echo(click.style("Dry run: nothing was changed.", fg="yellow"))
        return False
    if not yes and not click.confirm("Go ahead?"):
        click.echo("Nothing was changed.")
        return False
    return True


def _fail(error):
    raise click.ClickException(str(error))


@analysis.command(
    "list",
    help="List analyses, with how many there are in each status. "
    "--group lists only those which the strategy group made.",
)
@click.option("--group", "-g", "group", default=None, help="The name of the group (its blueprint).")
def list_analyses(group):
    try:
        members = groups.group_members(ledger, group) if group else groups.everything(ledger)
    except GroupError as error:
        _fail(error)
    for member in members:
        click.echo(f"{member.label}  {member.status}")
    click.echo(groups.summary(members))


@analysis.command(
    "set",
    help="Set the status of every analysis in a group. Use 'stop' to stop ones which are running "
    "(the monitor cancels their jobs); 'stopped' only records that they are stopped.",
)
@click.option("--group", "-g", "group", required=True, help="The name of the group (its blueprint).")
@click.option("--status", "-s", required=True, help="ready | wait | stuck | stop | stopped | cancelled")
@click.option("--dry-run", is_flag=True, help="Say what would change, and change nothing.")
@click.option("--yes", "-y", is_flag=True, help="Do not ask first.")
def set_status(group, status, dry_run, yes):
    try:
        members = [m for m in groups.group_members(ledger, group) if m.status != status]
        if status not in groups.SETTABLE:
            raise GroupError(f"'{status}' cannot be set. Use one of: {', '.join(sorted(groups.SETTABLE))}.")
        if _confirm(f"Set to '{status}'", members, dry_run, yes):
            changed = groups.set_status(ledger, members, status)
            click.echo(click.style("●", fg="green") + f" {len(changed)} analyses set to {status}")
    except GroupError as error:
        _fail(error)


@analysis.command("delete", help="Remove every analysis of a group from the project.")
@click.option("--group", "-g", "group", required=True, help="The name of the group (its blueprint).")
@click.option("--force", is_flag=True, help="Remove analyses which are running too.")
@click.option("--dry-run", is_flag=True, help="Say what would be removed, and remove nothing.")
@click.option("--yes", "-y", is_flag=True, help="Do not ask first.")
def delete(group, force, dry_run, yes):
    try:
        members = groups.group_members(ledger, group)
        running = [m for m in members if m.status in groups.RUNNING]
        if running and not force:
            groups.delete(ledger, members, force=False)  # raises, and says which
        if _confirm("Remove", members, dry_run, yes):
            removed = groups.delete(ledger, members, force=force)
            click.echo(click.style("●", fg="green") + f" Removed {len(removed)} analyses")
    except GroupError as error:
        _fail(error)


@analysis.command(
    "rerun",
    help="Make an analysis ready to run again. With --downstream, so is everything which "
    "depends on it, in any subject. --clean also removes what each has produced.",
)
@click.argument("subject")
@click.argument("name")
@click.option("--downstream", is_flag=True, help="Include everything which depends on it.")
@click.option("--clean", is_flag=True, help="Remove the artefacts of each analysis (its pipeline's clean()).")
@click.option("--dry-run", is_flag=True, help="Say what would be reset, and reset nothing.")
@click.option("--yes", "-y", is_flag=True, help="Do not ask first.")
def rerun(subject, name, downstream, clean, dry_run, yes):
    try:
        members = groups.everything(ledger)
        start = groups.find(ledger, subject, name, members)
        chosen = groups.downstream(ledger, start, members) if downstream else [start]
        running = [m for m in chosen if m.status in groups.RUNNING]
        if running:
            raise GroupError(
                f"{len(running)} of these are running ({', '.join(m.label for m in running[:5])}); "
                "stop them first (asimov analysis set, or asimov production set -s stop)."
            )
        if _confirm("Reset to 'ready'" + (" and clean" if clean else ""), chosen, dry_run, yes):
            groups.reset(ledger, chosen, clean=clean)
            click.echo(click.style("●", fg="green") + f" {len(chosen)} analyses ready to run again")
    except GroupError as error:
        _fail(error)
