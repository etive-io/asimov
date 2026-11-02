"""
Commands for a group of analyses which a strategy made, and for re-running an
analysis and what depends on it (#234).

Every command that changes anything says what it would change, takes
``--dry-run`` to stop there, and asks before it goes on unless given ``--yes``.
"""
import os

import click

from asimov import groups, retention
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
    "du",
    help="How much disk space analyses take: what they produced (recorded when they finished), "
    "what is in their run directory now, and what has been released.",
)
@click.option("--group", "-g", "group", default=None, help="The name of the group (its blueprint).")
def du(group):
    try:
        members = groups.group_members(ledger, group) if group else groups.everything(ledger)
    except GroupError as error:
        _fail(error)
    on_disk = produced = freed = 0
    for member in members:
        rundir = getattr(member.analysis, "rundir", None)
        now = retention.size_of(rundir)[0] if rundir and os.path.isdir(rundir) else 0
        made = retention.recorded_size(member.analysis) or sum(
            retention.size_of(path)[0]
            for paths in retention.output_paths(member.analysis).values()
            for path in paths
        )
        gone = sum(int(r.get("size", 0) or 0) for r in retention.released(member.analysis))
        on_disk, produced, freed = on_disk + now, produced + made, freed + gone
        click.echo(
            f"{member.label:40} {member.status:10} {retention.human(now):>10} on disk "
            f"{retention.human(made):>10} outputs {retention.human(gone):>10} released"
        )
    click.echo(
        f"{len(members)} analyses: {retention.human(on_disk)} on disk, "
        f"{retention.human(produced)} of outputs, {retention.human(freed)} released"
    )


@analysis.command(
    "prune",
    help="Release the outputs which their pipelines say can go once consumed (retention: until_consumed), "
    "when everything which needs them has finished. Nothing in the results store, outside a run directory, "
    "or marked keep is touched.",
)
@click.option("--group", "-g", "group", default=None, help="Only the analyses of this group.")
@click.option(
    "--done",
    is_flag=True,
    help="The group will not grow any more, so what a strategy might still consume is not kept.",
)
@click.option("--dry-run", is_flag=True, help="Say what would be released, and release nothing.")
@click.option("--yes", "-y", is_flag=True, help="Do not ask first.")
def prune(group, done, dry_run, yes):
    if not retention.enabled():
        raise click.ClickException("Releasing assets is switched off for this project ([retention] release = false).")
    try:
        members = groups.everything(ledger)
        scope = groups.group_members(ledger, group, members) if group else members
    except GroupError as error:
        _fail(error)
    result = retention.plan(ledger, members, scope, done)
    if result.kept:
        reasons = {}
        for _, _, why in result.kept:
            reasons[why] = reasons.get(why, 0) + 1
        click.echo("Kept:")
        for why, number in sorted(reasons.items(), key=lambda pair: (-pair[1], pair[0]))[:8]:
            click.echo(f"  {number} x {why}")
    if not result.items:
        click.echo("Nothing to release.")
        return
    click.echo(f"Release {len(result.items)} outputs, {retention.human(result.size)}:")
    for item in result.items[:25]:
        click.echo(f"  {item.member.label}  {item.asset}  {retention.human(item.size)}")
    if len(result.items) > 25:
        click.echo(f"  ... and {len(result.items) - 25} more")
    if dry_run:
        click.echo(click.style("Dry run: nothing was released.", fg="yellow"))
        return
    if not yes and not click.confirm("Go ahead?"):
        click.echo("Nothing was released.")
        return
    records = retention.release(ledger, result.items)
    click.echo(
        click.style("●", fg="green")
        + f" Released {len(records)} outputs, {retention.human(sum(r['size'] for r in records))}"
    )


@analysis.command(
    "rerun",
    help="Make an analysis ready to run again. With --downstream, so is everything which "
    "depends on it, in any subject. --clean also removes what each has produced.",
)
@click.argument("subject")
@click.argument("name")
@click.option("--downstream", is_flag=True, help="Include everything which depends on it.")
@click.option("--clean", is_flag=True, help="Remove the artefacts of each analysis (its pipeline's clean()).")
@click.option(
    "--regenerate",
    is_flag=True,
    help="Also run again what made an input which was released, so that it is there again.",
)
@click.option("--dry-run", is_flag=True, help="Say what would be reset, and reset nothing.")
@click.option("--yes", "-y", is_flag=True, help="Do not ask first.")
def rerun(subject, name, downstream, clean, regenerate, dry_run, yes):
    try:
        members = groups.everything(ledger)
        start = groups.find(ledger, subject, name, members)
        chosen = groups.downstream(ledger, start, members) if downstream else [start]
        if regenerate:
            chosen = retention.regenerate(chosen, members)
        missing = retention.pruned_inputs(chosen, members)
        if missing:
            lines = "\n".join(f"  {user} needs {what} of {maker}" for user, maker, what in missing[:10])
            raise GroupError(
                "These were released to save space, and what would be run again needs them:\n"
                f"{lines}\nRun again what made them (--regenerate does that), or release less."
            )
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
