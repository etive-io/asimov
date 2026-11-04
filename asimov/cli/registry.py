"""
Commands for the registry of projects an instance serves (see #184).
"""

import json

import click

from asimov.registry import (
    FileRegistry,
    ProjectEntry,
    RegistryError,
    default_registry_path,
)


def _registry(ctx):
    return FileRegistry(ctx.obj["path"])


@click.group(help="Manage the projects an asimov instance serves.")
@click.option(
    "--registry",
    "path",
    type=click.Path(dir_okay=False),
    default=None,
    help="The registry file (default: $ASIMOV_REGISTRY, or asimov/registry.yaml in your "
    "configuration directory).",
)
@click.pass_context
def registry(ctx, path):
    """Group for the registry commands."""
    ctx.obj = {"path": path or default_registry_path()}


@registry.command("add", help="Register the project in DIRECTORY under NAME.")
@click.argument("name")
@click.argument("directory", type=click.Path(exists=True, file_okay=False))
@click.option("--group", "-g", "groups", multiple=True, help="A group which owns it (repeat for more).")
@click.option("--ledger-engine", default=None, help="The ledger engine, if not the project's own.")
@click.option(
    "--ledger-location",
    default=None,
    help="The ledger's location or database URL, if not the project's own. "
    "May use $VARIABLES, so that a password needn't be written down.",
)
@click.option("--storage", default=None, help="Where its results are stored.")
@click.option("--scheduler", default=None, help="The scheduler it submits to, e.g. htcondor.")
@click.option(
    "--quota",
    "quotas",
    multiple=True,
    metavar="NAME=VALUE",
    help="A limit, e.g. max_queued=100 (also max_submit_per_pass, submit_interval).",
)
@click.pass_context
def add(ctx, name, directory, groups, ledger_engine, ledger_location, storage, scheduler, quotas):
    """Register a project."""
    import os

    ledger = {}
    if ledger_engine:
        ledger["engine"] = ledger_engine
    if ledger_location:
        ledger["location"] = ledger_location
    parsed = {}
    for quota in quotas:
        key, separator, value = quota.partition("=")
        if not separator:
            raise click.UsageError(f"{quota!r} should be NAME=VALUE.")
        try:
            parsed[key] = float(value) if "." in value else int(value)
        except ValueError:
            raise click.UsageError(f"The value of {key} must be a number, not {value!r}.")
    try:
        entry = ProjectEntry(
            name=name,
            root=os.path.abspath(directory),
            groups=list(groups),
            ledger=ledger or None,
            storage=storage,
            scheduler=scheduler,
            quotas=parsed,
        )
        _registry(ctx).add(entry)
    except RegistryError as error:
        raise click.ClickException(str(error))
    click.echo(click.style("●", fg="green") + f" Registered {name}")


@registry.command("list", help="List the registered projects.")
@click.option("--format", "output", type=click.Choice(["text", "json"]), default="text")
@click.pass_context
def list_projects(ctx, output):
    """List projects."""
    try:
        entries = _registry(ctx).list()
    except RegistryError as error:
        raise click.ClickException(str(error))
    if output == "json":
        click.echo(json.dumps({e.name: e.to_dict(mask=True) for e in entries}, indent=2))
        return
    if not entries:
        click.echo("No projects are registered.")
    for entry in entries:
        groups = ", ".join(entry.groups) or "-"
        click.echo(f"{entry.name:24} {groups:24} {entry.root}")


@registry.command("show", help="Show a project's registry entry.")
@click.argument("name")
@click.pass_context
def show(ctx, name):
    """Show a project."""
    try:
        entry = _registry(ctx).get(name)
    except RegistryError as error:
        raise click.ClickException(str(error))
    click.echo(json.dumps({entry.name: entry.to_dict(mask=True)}, indent=2))


@registry.command("remove", help="Remove a project from the registry. Its directory is left alone.")
@click.argument("name")
@click.pass_context
def remove(ctx, name):
    """Remove a project."""
    try:
        _registry(ctx).remove(name)
    except RegistryError as error:
        raise click.ClickException(str(error))
    click.echo(click.style("●", fg="green") + f" Removed {name} from the registry")


@registry.command("grant", help="Give GROUP the ROLE on the project NAME.")
@click.argument("name")
@click.argument("group")
@click.argument("role", type=click.Choice(["viewer", "reviewer", "analyst", "maintainer"]))
@click.pass_context
def grant(ctx, name, group, role):
    """Grant a role."""

    def change(entry):
        roles = entry.grants.setdefault(group, [])
        if role not in roles:
            roles.append(role)

    try:
        _registry(ctx).update(name, change)
    except RegistryError as error:
        raise click.ClickException(str(error))
    click.echo(click.style("●", fg="green") + f" {group} is {role} on {name}")


@registry.command("revoke", help="Take ROLE (or every role) on the project NAME from GROUP.")
@click.argument("name")
@click.argument("group")
@click.argument("role", required=False)
@click.pass_context
def revoke(ctx, name, group, role):
    """Revoke a role. The owning groups are changed by editing the registry."""

    def change(entry):
        if group not in entry.grants:
            raise RegistryError(f"{group} holds no granted role on {name}.")
        if role is None:
            del entry.grants[group]
            return
        remaining = [r for r in entry.grants[group] if r != role]
        if remaining:
            entry.grants[group] = remaining
        else:
            del entry.grants[group]

    try:
        _registry(ctx).update(name, change)
    except RegistryError as error:
        raise click.ClickException(str(error))
    click.echo(click.style("●", fg="green") + f" Revoked {role or 'every role'} on {name} from {group}")


@registry.command(
    "self-approval",
    help="Allow (on) or forbid (off) whoever applied an analysis in NAME to approve it.",
)
@click.argument("name")
@click.argument("setting", type=click.Choice(["on", "off"]))
@click.pass_context
def self_approval(ctx, name, setting):
    """Set whether self-approval is allowed."""

    def change(entry):
        entry.self_approval = setting == "on"

    try:
        _registry(ctx).update(name, change)
    except RegistryError as error:
        raise click.ClickException(str(error))
    state = "allowed" if setting == "on" else "forbidden"
    click.echo(click.style("●", fg="green") + f" Self-approval is {state} on {name}")


@registry.command("members", help="Show the members of GROUP, adding or removing people first.")
@click.argument("group")
@click.option("--add", "add", multiple=True, help="A person to add (repeat for more).")
@click.option("--remove", "remove", multiple=True, help="A person to remove (repeat for more).")
@click.pass_context
def members(ctx, group, add, remove):
    """Manage a group's members in the instance's groups file."""
    from asimov.membership import FileGroupDirectory, MembershipError, default_groups_path

    directory = FileGroupDirectory(default_groups_path(ctx.obj["path"]))
    try:
        if add or remove:
            people = directory.change_members(group, add=add, remove=remove)
        else:
            _, groups = directory.load()
            if group not in groups:
                raise MembershipError(f"There is no group called {group!r}.")
            people = groups[group]
    except MembershipError as error:
        raise click.ClickException(str(error))
    click.echo(f"{group}: {', '.join(sorted(people)) or '(no members)'}")
