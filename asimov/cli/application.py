"""
Tools for adding data from JSON and YAML files.
Inspired by the kubectl apply approach from kubernetes.
"""

import os
import re
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path

import click
import requests
import yaml

from asimov import LOGGER_LEVEL, logger
from asimov.context import current_context
from asimov.principal import current_principal
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


#: The key under which an analysis records who requested it.
REQUESTED_BY = "requested by"


def _requested_by():
    """
    Who is requesting what is being applied now, as data for the ledger.

    Always the current principal, never anything the blueprint says: a
    blueprint is content from the requester, and must not be able to name
    someone else, since this is what accounting and review rules rely on.
    """
    return current_principal().to_dict()


def get_ledger():
    """
    Get the current ledger instance.

    Reloads the ledger to ensure we have the latest state,
    preventing issues where the ledger is cached at import time.

    If called from inside a ``with project:`` block, returns
    ``project.ledger`` instead of constructing a fresh ``Ledger``, since
    only ``project.ledger`` is saved when that block exits -- mutations
    made via an independently constructed ledger would otherwise be
    silently discarded.

    Returns
    -------
    Ledger
        The current ledger instance.
    """
    from asimov.context import get_active_context

    active = get_active_context()
    if active is not None:
        return active.ledger

    from asimov import config
    if config.get("ledger", "engine") == "yamlfile":
        from asimov.ledger import YAMLLedger
        return YAMLLedger(config.get("ledger", "location"))
    else:
        from asimov import current_ledger
        return current_ledger


def _raw_production_names(ledger, event_name):
    """Return the set of production names for an event from raw ledger data.

    Reads directly from ``ledger.events`` (a plain dict) or, for the database
    ledger, from the stored rows, rather than constructing a full ``Event``
    object, avoiding expensive git and Production initialisation just to
    obtain a set of strings.
    """
    names = set()
    db = getattr(ledger, "db", None)
    if db is not None:
        # The database ledger: read the persisted rows directly. Loading the
        # event would skip any analysis which fails to load, and collapse
        # duplicates, so its names could be handed out a second time.
        return {row["name"] for row in db.query("production", "event_name", event_name)}
    events = ledger.events
    for prod in events.get(event_name, {}).get("productions", []):
        if isinstance(prod, dict) and len(prod) == 1:
            names.add(next(iter(prod)))
        elif isinstance(prod, dict) and "name" in prod:
            names.add(prod["name"])
    return names


def next_available_name(name, existing_names):
    """Return the next available analysis name, incrementing a numeric suffix if needed.

    If ``name`` is not already taken, it is returned unchanged.  Otherwise the
    trailing ``-N`` suffix (if present) is stripped to find the stem, and the
    lowest integer >= 2 that produces a free name is appended.

    Examples
    --------
    >>> next_available_name("bilby-IMRPhenomXPHM", {"bilby-IMRPhenomXPHM"})
    'bilby-IMRPhenomXPHM-2'
    >>> next_available_name("bilby-IMRPhenomXPHM-2", {"bilby-IMRPhenomXPHM-2"})
    'bilby-IMRPhenomXPHM-3'
    """
    if name not in existing_names:
        return name
    match = re.match(r"^(.*)-(\d+)$", name)
    stem, n = (match.group(1), int(match.group(2))) if match else (name, 1)
    n += 1
    while f"{stem}-{n}" in existing_names:
        n += 1
    return f"{stem}-{n}"


# Analyses in these states have not yet used the event settings, so an event
# update with update_unstarted=True lets them inherit the new values.
UNSTARTED_STATES = {"ready", "wait"}


def _refresh_inherited(analysis_meta, old_event, new_event):
    """
    Give an analysis the new event values for every setting it merely
    inherited (i.e. still equal to the old event value), leaving any setting
    the analysis overrides untouched.
    """
    for key, value in new_event.items():
        current = analysis_meta.get(key)
        if isinstance(value, dict) and isinstance(current, dict):
            _refresh_inherited(current, old_event.get(key) or {}, value)
        elif key not in analysis_meta or current == old_event.get(key):
            analysis_meta[key] = deepcopy(value)


def _update_event_in_database_ledger(ledger, event_obj, update_unstarted=False):
    """
    Merge a new event definition into an existing event in a database ledger.

    The analyses attached to the event are never removed. Event-level
    settings which are about to be changed are frozen into each analysis
    (unless the analysis already sets them) so that existing analyses keep
    the configuration they were created with, and the previous event
    settings are kept in the ledger history. If update_unstarted is set,
    analyses which have not yet started are left to inherit the new values.
    """
    existing = ledger.get_event(event_obj.name)[0]
    old_event = deepcopy(existing.meta)
    for key in ["name", "productions", "working directory", "repository", "ledger"]:
        old_event.pop(key, None)

    new_meta = deepcopy(event_obj.meta)
    new_meta.pop("ledger", None)

    for production in existing.productions:
        if update_unstarted and str(production.status).lower() in UNSTARTED_STATES:
            _refresh_inherited(production.meta, old_event, new_meta)
            continue
        merged = update(deepcopy(old_event), production.meta)
        production.meta.clear()
        production.meta.update(merged)

    history = ledger.data.setdefault("history", {})
    event_history = history.setdefault(event_obj.name, {})
    version = f"version-{len(event_history) + 1}"
    event_history[version] = old_event
    event_history[version]["date changed"] = datetime.now().isoformat()

    update(existing.meta, new_meta)
    ledger.update_event(existing)
    ledger.save()


def apply_page(file, event=None, ledger=None, update_page=False, name=None, iterate=False, update_unstarted=False):
    if update_unstarted:
        update_page = True
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

    # Events loaded for applying analyses, by name. Loading an event builds every
    # analysis in it, so doing that once per analysis made applying a large
    # blueprint quadratic in the number of analyses. Each analysis which is added
    # is also added to its cached event, so the next one is built against the same
    # state a reload would give. Any other kind of document may change an event,
    # so it empties the cache.
    loaded_events = {}

    for document in quick_parse:
        if document["kind"] != "analysis":
            loaded_events.clear()
        if document["kind"] in ("event", "subject"):
            logger.info("Found an event")
            document.pop("kind")
            event_obj = asimov.event.Event.from_yaml(yaml.dump(document))

            # Check if the event is in the ledger already. ledger.events is a
            # plain dict for the YAML ledger, so that is cheap. For the database
            # ledger it builds every event, and every analysis in them, so ask
            # for just this event's row instead: doing the former for each event
            # in a blueprint made applying many subjects quadratic.
            database = getattr(ledger, "db", None)
            if database is None:
                event_exists = event_obj.name in ledger.events
            else:
                event_exists = len(database.query("event", "name", event_obj.name)) > 0

            if event_exists and update_page is True and database is not None:
                _update_event_in_database_ledger(ledger, event_obj, update_unstarted=update_unstarted)
                click.echo(
                    click.style("●", fg="green") + f" Successfully updated {event_obj.name}"
                )

            elif event_exists and update_page is True:
                old_event = deepcopy(ledger.events[event_obj.name])
                for key in ["name", "productions", "working directory", "repository", "ledger"]:
                    old_event.pop(key, None)
                analyses = []
                for prod in ledger.events[event_obj.name].get("productions", []):
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

                    status = str(prod_data.get("status", "")).lower()
                    if update_unstarted and status in UNSTARTED_STATES:
                        merged = prod_data
                    else:
                        merged = update(prod_data, old_event, inplace=False)

                    if prod_name:
                        analyses.append({prod_name: merged})
                    else:
                        analyses.append(merged)

                # Add the old version to the history
                if "history" not in ledger.data:
                    ledger.data["history"] = {}
                history = ledger.data["history"].get(event_obj.name, {})
                version = f"version-{len(history)+1}"
                history[version] = old_event
                history[version]["date changed"] = datetime.now()

                ledger.data["history"][event_obj.name] = history
                update(ledger.events[event_obj.name], event_obj.meta)
                ledger.events[event_obj.name]["productions"] = analyses
                ledger.events[event_obj.name].pop("ledger", None)
                ledger.save()

                click.echo(
                    click.style("●", fg="green") + f" Successfully updated {event_obj.name}"
                )

            elif not event_exists and update_page is False:
                ledger.update_event(event_obj)
                click.echo(
                    click.style("●", fg="green") + f" Successfully added {event_obj.name}"
                )
                logger.info(f"Added {event_obj.name} to project")

            elif not event_exists and update_page is True:
                click.echo(
                    click.style("●", fg="red")
                    + f" {event_obj.name} cannot be updated as there is no record of it in the project."
                )
            else:
                click.echo(
                    click.style("●", fg="red")
                    + f" {event_obj.name} already exists in this project."
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
                    
            # Resolve name overrides before constructing the Event object.
            # Reading from the raw ledger dict is cheap; get_event() is expensive
            # (it instantiates Production objects and runs git/graph operations).
            if name is not None or iterate:
                existing_names = _raw_production_names(ledger, event_s)
            for expanded_doc in expanded_documents:
                if name is not None:
                    expanded_doc["name"] = name
                elif iterate:
                    expanded_doc["name"] = next_available_name(expanded_doc["name"], existing_names)
                    # Keep existing_names current so consecutive iterations in a
                    # strategy expansion don't collide with each other.
                    existing_names.add(expanded_doc["name"])

                try:
                    if event_s not in loaded_events:
                        loaded_events[event_s] = ledger.get_event(event_s)[0]
                    event_obj = loaded_events[event_s]
                except KeyError as e:
                    click.echo(
                        click.style("●", fg="red")
                        + f" Could not apply a production, couldn't find the event {event_s}"
                    )
                    logger.exception(e)
                    continue
                expanded_doc[REQUESTED_BY] = _requested_by()
                production = asimov.event.Production.from_dict(
                    parameters=expanded_doc, subject=event_obj, ledger=ledger
                )
                try:
                    ledger.add_analysis(production, event=event_obj)
                    # The YAML ledger adds it to the event itself; the database
                    # ledger only stores it.
                    if not event_obj.productions or event_obj.productions[-1] is not production:
                        event_obj.add_production(production)
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
            document[REQUESTED_BY] = _requested_by()
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
                        Path(current_context().root),  # The project directory
                        Path(current_context().root) / "analyses",  # Local analyses dir
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
                            analysis_doc[REQUESTED_BY] = _requested_by()
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
                    analysis_ref[REQUESTED_BY] = _requested_by()
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
    current_ledger = get_ledger()
    for hook in discovered_hooks:
        if hook.name in hookname:
            hook.load()(current_ledger).run(event)
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
@click.option(
    "--update-unstarted",
    is_flag=True,
    default=False,
    help="Update the event (implies --update), and let analyses which have not yet "
    "started inherit the new event settings. Analyses which have started or "
    "finished keep the settings they were created with.",
)
@click.option(
    "--name",
    "-n",
    default=None,
    help="Override the analysis name specified in the blueprint.",
)
@click.option(
    "--iterate",
    "-I",
    is_flag=True,
    default=False,
    help="Automatically increment the analysis name suffix to avoid a name conflict.",
)
def apply(file, event, plugin, update, update_unstarted, name, iterate):
    from asimov import setup_file_logging
    current_ledger = get_ledger()
    setup_file_logging()
    if plugin:
        apply_via_plugin(event, hookname=plugin)
    elif file:
        apply_page(file, event, ledger=current_ledger, update_page=update, name=name, iterate=iterate, update_unstarted=update_unstarted)
