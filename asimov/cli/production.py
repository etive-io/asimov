from copy import copy

import click
import yaml

from asimov import config
from asimov import current_ledger as ledger

from asimov.event import Production
from asimov.storage import Store


@click.group()
def production():
    """
    Commands to handle productions.
    """
    pass


@click.argument("pipeline")
@click.argument("event")
@click.option(
    "--family",
    "family",
    default="Prod",
    help="The family name of the production, e.g. `prod`.",
)
@click.option(
    "--comment", "comment", default=None, help="A comment to attach to the production"
)
@click.option(
    "--needs",
    "needs",
    multiple=True,
    default=[],
    help="A list of productions which are requirements",
)
@click.option(
    "--template",
    "template",
    default=None,
    help="The configuration template for the production.",
)
@click.option(
    "--status", "status", default="ready", help="The initial status of the production."
)
@click.option(
    "--approximant",
    "approximant",
    default=None,
    help="The waveform approximant to be used in the production.",
)
@production.command(help="Add a new production to an event")
def create(event, pipeline, family, comment, needs, template, status, approximant):
    """
    Add a new production to an event.

    """

    event = ledger.get_event(event)[0]
    #
    event_prods = event.productions
    names = [production.name for production in event_prods]
    family_entries = [int(name.split(family)[1]) for name in names if family in name]
    #
    if "bayeswave" in needs:
        bw_entries = [
            production.name
            for production in event_prods
            if ("bayeswave" in production.pipeline.lower())
            and (production.review.status not in {"REJECTED", "DEPRECATED"})
        ]
        needs = bw_entries
    #
    production = {
        "comment": comment,
        "pipeline": pipeline,
        "status": status,
        "waveform": {},
    }
    if needs:
        production["needs"] = needs
    if template:
        production["template"] = template
    if approximant:
        production["waveform"]["approximant"] = approximant
    if len(family_entries) > 0:
        number = max(family_entries) + 1
    else:
        number = 0
    production_dict = {f"{family}{number}": production}
    production = Production.from_dict(production_dict, event=event)
    #
    event.add_production(production)
    click.secho(f"Production added to {event.name}")
    click.echo(f"\t{production}")

    if config.get("ledger", "engine") == "yamlfile":
        ledger.events[event.name] = event.to_dict()
        ledger.save()


@click.option(
    "--status",
    "-s",
    default=None,
    help="Change the run status. Options: ready | wait | stuck | stop | cancelled",
)
@click.argument("production")
@click.argument("event")
@production.command()
def set(event, production, status):
    """
    Set or update properties such as the status of a production.
    Note that some properties cannot be updated once the production is being run,
    and you should create a new production instead.
    """
    event = ledger.get_event(event=event)[0]
    production = [
        production_o
        for production_o in event.productions
        if production_o.name == production
    ][0]

    accepted_states = {"ready", "wait", "stuck", "stop", "cancelled"}
    if status:
        if status in accepted_states:
            production.status = status
            # ledger.save()
            click.echo(
                click.style("●", fg="green")
                + f" {production.name} status updated to {status}"
            )
        else:
            click.echo(
                click.style("●", fg="red")
                + f" Unable to change the state of {production.name} to {status}."
            )


@click.argument("production")
@click.argument("event")
@production.command()
def show(event, production):
    """
    Show the entire metadata for a given production.
    """
    event = ledger.get_event(event=event)[0]
    production = [
        production_o
        for production_o in event.productions
        if production_o.name == production
    ][0]

    meta = copy(production.meta)
    meta.pop("ledger")
    output = yaml.dump(meta, default_flow_style=False)
    click.echo_via_pager(output)


@click.option("--file", "file", default=None)
@click.argument("production")
@click.argument("event")
@production.command()
def results(event, production, file, hash=None):
    """
    Fetch or list the results of a production.
    """
    event = ledger.get_event(event)[0]
    production = [
        production_o
        for production_o in event.productions
        if production_o.name == production
    ][0]
    store = Store(root=config.get("storage", "directory"))

    if not file:
        try:
            items = store.manifest.list_resources(event.name, production.name).items()
            click.secho(f"{'Resource':30} {'Hash':32} {'UUID':32}")
            click.secho("-" * 96)
            for resource, details in items:
                click.secho(f"{resource:30} {details['hash']:32} {details['uuid']:32}")
        except KeyError:
            click.secho("There are no results for this production.")
    else:
        try:
            click.echo(store.fetch_file(event, production, file, hash))
        except FileNotFoundError:
            click.secho(f"{file} could not be found for this production.")
