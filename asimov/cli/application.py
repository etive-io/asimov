"""
Tools for adding data from JSON and YAML files.
Inspired by the kubectl apply approach from kubernetes.
"""

import os
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path

import click
import requests
import yaml

from asimov import LOGGER_LEVEL, logger
import asimov.event
from asimov.analysis import ProjectAnalysis
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


def get_ledger():
    """
    Get the current ledger instance.
    
    Reloads the ledger to ensure we have the latest state,
    preventing issues where the ledger is cached at import time.
    
    Returns
    -------
    Ledger
        The current ledger instance.
    """
    from asimov import config
    if config.get("ledger", "engine") == "yamlfile":
        from asimov.ledger import YAMLLedger
        return YAMLLedger(config.get("ledger", "location"))
    else:
        from asimov import current_ledger
        return current_ledger


def apply_page(file, event=None, ledger=None, update_page=False):
    # Get ledger if not provided
    if ledger is None:
        ledger = get_ledger()

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
            # ledger.events is a dict with event names as keys
            event_exists = event.name in ledger.events

            if event_exists and update_page is True:
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

            elif not event_exists and update_page is False:
                ledger.update_event(event)
                click.echo(
                    click.style("●", fg="green") + f" Successfully added {event.name}"
                )
                logger.info(f"Added {event.name} to project")

            elif not event_exists and update_page is True:
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
            
            # Determine event once for all expanded analyses
            if event:
                event_s = event
            else:
                if "event" in document:
                    event_s = document["event"]
                else:
                    num_analyses = len(expanded_documents)
                    if num_analyses > 1:
                        prompt = f"Which event should these {num_analyses} analyses be applied to?"
                    else:
                        prompt = "Which event should these be applied to?"
                    event_s = str(click.prompt(prompt))
                    
            for expanded_doc in expanded_documents:
                    
              try:
                  event_obj = ledger.get_event(event_s)[0]
              except KeyError as e:
                  click.echo(
                      click.style("●", fg="red")
                      + f" Could not apply a production, couldn't find the event {event}"
                  )
                  logger.exception(e)
              production = asimov.event.Production.from_dict(
                  parameters=expanded_doc, subject=event_obj, ledger=ledger
              )
              try:
                  ledger.add_analysis(production, event=event_obj)
                  click.echo(
                      click.style("●", fg="green")
                      + f" Successfully applied {production.name} to {event_obj.name}"
                  )
                  logger.info(f"Added {production.name} to {event_obj.name}")
              except ValueError as e:
                  click.echo(
                      click.style("●", fg="red")
                      + f" Could not apply {production.name} to {event_obj.name} as "
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
                    event_obj = ledger.get_event(event_s)[0]
                    level = event_obj
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

        elif document["kind"].lower() == "analysisbundle":
            # Handle analysis bundle - a collection of analysis references
            logger.info("Found an analysis bundle")
            bundle_name = document.get("name", "unnamed bundle")
            analyses_refs = document.get("analyses", [])

            if not event:
                click.echo(
                    click.style("●", fg="red")
                    + f" Analysis bundle '{bundle_name}' requires an event to be specified with -e"
                )
                logger.error(f"Analysis bundle '{bundle_name}' requires an event to be specified")
                continue

            try:
                event_obj = ledger.get_event(event)[0]
            except KeyError as e:
                click.echo(
                    click.style("●", fg="red")
                    + f" Could not apply bundle '{bundle_name}', couldn't find the event {event}"
                )
                logger.exception(e)
                continue

            click.echo(
                click.style("●", fg="cyan")
                + f" Applying bundle '{bundle_name}' ({len(analyses_refs)} analyses) to {event_obj.name}"
            )

            # Resolve and apply each analysis in the bundle
            for analysis_ref in analyses_refs:
                # Analysis ref can be:
                # - A string: "bayeswave-psd" (references file stem)
                # - A dict: {"name": "...", ...} (inline definition)

                if isinstance(analysis_ref, str):
                    # Reference by file stem - need to find and load the file
                    analysis_file_name = f"{analysis_ref}.yaml"

                    # Try to find the file in common locations
                    search_paths = [
                        Path.cwd(),  # Current directory
                        Path.cwd() / "analyses",  # Local analyses dir
                    ]

                    # Also check ASIMOV_DATA_PATH if set
                    if "ASIMOV_DATA_PATH" in os.environ:
                        data_path = Path(os.environ["ASIMOV_DATA_PATH"])
                        search_paths.append(data_path / "analyses")

                    # Check default asimov-data location
                    home = Path.home()
                    search_paths.append(home / ".asimov" / "gwdata" / "asimov-data" / "analyses")

                    analysis_file = None
                    for search_path in search_paths:
                        candidate = search_path / analysis_file_name
                        # Ensure the resolved path is within the expected search path
                        try:
                            candidate = candidate.resolve()
                            search_path_resolved = search_path.resolve()
                            if candidate.is_relative_to(search_path_resolved) and candidate.exists():
                                analysis_file = candidate
                                break
                        except (ValueError, OSError):
                            # Skip if path resolution fails or is invalid
                            continue

                    if not analysis_file:
                        click.echo(
                            click.style("  ●", fg="yellow")
                            + f" Could not find analysis file '{analysis_file_name}', skipping"
                        )
                        logger.warning(f"Could not find analysis file '{analysis_file_name}'")
                        continue

                    # Load and apply the analysis file
                    with open(analysis_file, "r") as f:
                        analysis_content = f.read()

                    # Parse the analysis file (might be multi-document)
                    for analysis_doc in yaml.safe_load_all(analysis_content):
                        if analysis_doc and analysis_doc.get("kind") == "analysis":
                            try:
                                production = asimov.event.Production.from_dict(
                                    parameters=analysis_doc, subject=event_obj, ledger=ledger
                                )
                                ledger.add_analysis(production, event=event_obj)
                                click.echo(
                                    click.style("  ●", fg="green")
                                    + f" Applied {production.name} from {analysis_ref}"
                                )
                            except ValueError as e:
                                click.echo(
                                    click.style("  ●", fg="yellow")
                                    + f" {analysis_doc.get('name', 'analysis')} from {analysis_ref} already exists, skipping"
                                )
                                logger.warning(f"Analysis {analysis_doc.get('name', 'analysis')} already exists: {e}")

                elif isinstance(analysis_ref, dict):
                    # Inline analysis definition
                    try:
                        production = asimov.event.Production.from_dict(
                            parameters=analysis_ref, subject=event_obj, ledger=ledger
                        )
                        ledger.add_analysis(production, event=event_obj)
                        click.echo(
                            click.style("  ●", fg="green")
                            + f" Applied {production.name} (inline)"
                        )
                    except ValueError as e:
                        click.echo(
                            click.style("  ●", fg="yellow")
                            + f" {analysis_ref.get('name', 'analysis')} already exists, skipping"
                        )
                        logger.warning(f"Analysis {analysis_ref.get('name', 'analysis')} already exists: {e}")

            click.echo(
                click.style("●", fg="green")
                + f" Successfully applied bundle '{bundle_name}' to {event_obj.name}"
            )

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
    from asimov import setup_file_logging
    current_ledger = get_ledger()
    setup_file_logging()
    if plugin:
        apply_via_plugin(event, hookname=plugin)
    elif file:
        apply_page(file, event, ledger=current_ledger, update_page=update)
