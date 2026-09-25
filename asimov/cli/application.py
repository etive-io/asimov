"""
Tools for adding data from JSON and YAML files.
Inspired by the kubectl apply approach from kubernetes.
"""

import click
import requests
import yaml

from asimov import LOGGER_LEVEL, logger
import asimov.event
from asimov import current_ledger as ledger
from asimov.utils import update
from copy import deepcopy
from datetime import datetime
import sys

if sys.version_info < (3, 10):
    from importlib_metadata import entry_points
else:
    from importlib.metadata import entry_points


logger = logger.getChild("cli").getChild("apply")
logger.setLevel(LOGGER_LEVEL)


def apply_page(file, event=None, ledger=ledger, update_page=False):
    if file.startswith("http://") or file.startswith("https://"):
        r = requests.get(file)
        if r.status_code == 200:
            data = r.text
            logger.info(f"Downloaded {file}")
        else:
            raise ValueError(f"Could not download this file: {file}")
    else:
        with open(file, "r") as apply_file:
            data = apply_file.read()

    quick_parse = yaml.safe_load_all(
        data
    )  # Load as a dictionary so we can identify the object type it contains

    for document in quick_parse:

        if document["kind"] == "event":
            logger.info("Found an event")
            document.pop("kind")
            event = asimov.event.Event.from_yaml(yaml.dump(document))
            # Check if the event is in the ledger already
            if event.name in ledger.events and update_page is True:
                old_event = deepcopy(ledger.events[event.name])
                for key in ["name", "productions", "working directory", "repository", "ledger"]:
                    old_event.pop(key, None)
                analyses = []
                for prod in ledger.events[event.name].get("productions", []):
                    if isinstance(prod, dict) and len(prod) == 1:
                        prod_name, prod_data = next(iter(prod.items()))
                    elif isinstance(prod, dict):
                        prod_name = prod.get("name")
                        prod_data = {k: v for k, v in prod.items() if k != "name"} if prod_name else prod
                    else:
                        continue

                    if prod_data is None:
                        prod_data = {}

                    merged = update(old_event, prod_data, inplace=False)
                    analyses.append({prod_name: merged} if prod_name else merged)

                # Add the old version to the history
                if "history" not in ledger.data:
                    ledger.data["history"] = {}
                history = ledger.data["history"].get(event.name, {})
                version = f"version-{len(history)+1}"
                history[version] = old_event
                history[version]["date changed"] = datetime.now()

                ledger.data["history"][event.name] = history
                update(ledger.events[event.name], event.meta)
                ledger.events[event.name]["productions"] = analyses
                ledger.events[event.name].pop("ledger", None)
                ledger.save()

                click.echo(
                    click.style("●", fg="green") + f" Successfully updated {event.name}"
                )

            elif event.name not in ledger.events and update_page is False:
                ledger.update_event(event)
                click.echo(
                    click.style("●", fg="green") + f" Successfully added {event.name}"
                )
                logger.info(f"Added {event.name} to project")

            elif event.name not in ledger.events and update_page is True:
                click.echo(
                    click.style("●", fg="red")
                    + f" {event.name} cannot be updated as there is no record of it in the project."
                )
            else:
                click.echo(
                    click.style("●", fg="red")
                    + f" {event.name} already exists in this project."
                )

        elif document["kind"] == "analysis":
            logger.info("Found an analysis")
            document.pop("kind")
            if event:
                event_s = event
            else:
                if "event" in document:
                    event_s = document["event"]
                else:
                    prompt = "Which event should these be applied to?"
                    event_s = str(click.prompt(prompt))
            try:
                event_o = ledger.get_event(event_s)[0]
            except KeyError as e:
                click.echo(
                    click.style("●", fg="red")
                    + f" Could not apply a production, couldn't find the event {event}"
                )
                logger.exception(e)
            production = asimov.event.Production.from_dict(document, event=event_o)
            try:
                event_o.add_production(production)
                ledger.update_event(event_o)
                click.echo(
                    click.style("●", fg="green")
                    + f" Successfully applied {production.name} to {event_o.name}"
                )
                logger.info(f"Added {production.name} to {event_o.name}")
            except ValueError as e:
                click.echo(
                    click.style("●", fg="red")
                    + f" Could not apply {production.name} to {event_o.name} as "
                    + "an analysis already exists with this name"
                )
                logger.exception(e)

        elif document["kind"] == "configuration":
            logger.info("Found configurations")
            document.pop("kind")
            update(ledger.data, document)
            ledger.save()
            click.echo(
                click.style("●", fg="green")
                + " Successfully applied a configuration update"
            )


def apply_via_plugin(event, hookname, **kwargs):
    discovered_hooks = entry_points(group="asimov.hooks.applicator")
    for hook in discovered_hooks:
        if hook.name in hookname:
            hook.load()(ledger).run(event)
            click.echo(
                click.style("●", fg="green")
                + f"{event} has been applied."
            )

            break
    else:
        click.echo(
            click.style("●", fg="red")
            + f"No hook found matching {hookname}. "
            f"Installed hooks are {', '.join(discovered_hooks.names)}"
        )


@click.command()
@click.option("--file", "-f", help="Location of the file containing the ledger items.")
@click.option(
    "--event",
    "-e",
    help="The event which the ledger items should be applied to (e.g. for analyses)",
    default=None,
)
@click.option(
    "--plugin", "-p", help="The plugin to use to apply this data", default=None
)
@click.option(
    "--update",
    "-U",
    is_flag=True,
    show_default=True,
    default=False,
    help="Update the project with this blueprint rather than adding a new record.",
)
def apply(file, event, plugin, update):
    if plugin:
        apply_via_plugin(event, hookname=plugin)
    elif file:
        apply_page(file, event, update_page=update)
