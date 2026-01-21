"""
Tools for adding data from JSON and YAML files.
Inspired by the kubectl apply approach from kubernetes.
"""

import click
import requests
import yaml

from asimov import LOGGER_LEVEL, logger
import asimov.event
from asimov.analysis import ProjectAnalysis
from asimov import current_ledger as ledger
from asimov.ledger import Ledger
from asimov.utils import update
from asimov.strategies import expand_strategy
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
    if file[:4] == "http":
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
                    prod_name = None
                    prod_data = None

                    if isinstance(prod, dict) and len(prod) == 1:
                        prod_name, prod_data = next(iter(prod.items()))
                    elif isinstance(prod, dict):
                        prod_name = prod.get("name")
                        if prod_name:
                            prod_data = {k: v for k, v in prod.items() if k != "name"}
                        else:
                            prod_data = prod

                    if prod_data is None:
                        prod_data = {}

                    merged = update(prod_data, old_event, inplace=False)

                    if prod_name:
                        analyses.append({prod_name: merged})
                    else:
                        analyses.append(merged)

                # Add the old version to the history
                if "history" not in ledger.data:
                    ledger.data["history"] = {}
                history = ledger.data["history"].get(event.name, {})
                version = f"version-{len(history)+1}"
                history[version] = old_event
                history[version]["date changed"] = datetime.now()

                ledger.data["history"][event.name] = history
                ledger.save()
                update(ledger.events[event.name], event.meta)
                ledger.events[event.name]["productions"] = analyses
                ledger.events[event.name].pop("ledger", None)

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
            
            # Expand strategy if present
            expanded_documents = expand_strategy(document)
            
            for expanded_doc in expanded_documents:
                if event:
                    event_s = event
                else:
                    if "event" in expanded_doc:
                        event_s = expanded_doc["event"]
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
                    continue
                production = asimov.event.Production.from_dict(
                    parameters=expanded_doc, subject=event_o, ledger=ledger
                )
                try:
                    ledger.add_analysis(production, event=event_o)
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

        elif document["kind"].lower() == "postprocessing":
            # Handle a project analysis
            logger.info("Found a postprocessing description")
            document.pop("kind")
            if event:
                event_s = event

            if event:
                try:
                    event_o = ledger.get_event(event_s)[0]
                    level = event_o
                except KeyError as e:
                    click.echo(
                        click.style("●", fg="red")
                        + f" Could not apply postprocessing, couldn't find the event {event}"
                    )
                    logger.exception(e)
            else:
                level = ledger
            try:
                if document["name"] in level.data.get("postprocessing stages", {}):
                    click.echo(
                        click.style("●", fg="red")
                        + f" Could not apply postprocessing, as {document['name']} is already in the ledger."
                    )
                    logger.error(
                        f" Could not apply postprocessing, as {document['name']} is already in the ledger."
                    )
                else:
                    if "postprocessing stages" not in level.data:
                        level.data["postprocessing stages"] = {}
                    if isinstance(level, asimov.event.Event):
                        level.meta["postprocessing stages"][document["name"]] = document
                    elif isinstance(level, Ledger):
                        level.data["postprocessing stages"][document["name"]] = document
                        level.name = "the project"
                    ledger.save()
                    click.echo(
                        click.style("●", fg="green")
                        + f" Successfully added {document['name']} to {level.name}."
                    )
                    logger.info(f"Added {document['name']}")
            except ValueError as e:
                click.echo(
                    click.style("●", fg="red")
                    + f" Could not apply {document['name']} to project as "
                    + "a post-process already exists with this name"
                )
                logger.exception(e)

        elif document["kind"].lower() == "projectanalysis":
            # Handle a project analysis
            logger.info("Found a project analysis")
            document.pop("kind")
            analysis = ProjectAnalysis.from_dict(document, ledger=ledger)

            try:
                ledger.add_analysis(analysis)
                click.echo(
                    click.style("●", fg="green")
                    + f" Successfully added {analysis.name} to this project."
                )
                ledger.save()
                logger.info(f"Added {analysis.name}")
            except ValueError as e:
                click.echo(
                    click.style("●", fg="red")
                    + f" Could not apply {analysis.name} to project as "
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
            click.echo(click.style("●", fg="green") + f"{event} has been applied.")

            break
    else:
        click.echo(
            click.style("●", fg="red") + f"No hook found matching {hookname}. "
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
