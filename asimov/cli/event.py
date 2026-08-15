import json
import os
from math import floor

import click

from asimov import config
from asimov import current_ledger as ledger
from asimov.utils import update
from asimov.event import Event


@click.group()
def event():
    """
    Commands to handle events & collections.
    """
    pass


@click.option(
    "--old", "oldname", default=None, help="The old superevent ID for this event."
)
@click.option(
    "--repository",
    "repo",
    default=None,
    help="The location of the repository for this event.",
)
@click.option("--name", "-n", "name", default=None, help="The name for the event.")
@event.command()
def create(name=None, oldname=None, repo=None):
    """
    Create a new event record in the ledger.

    Parameters
    ----------
    name : str
       The name of the event to be recorded in the issue tracker
    oldname : str, optional
        The old name of the event.
    repo : str, optional
        The location of the repository for this event.

    Notes
    -----
    To create an event from a GraceDB GID or superevent, install the
    ``asimov-gracedb`` plugin and use
    ``asimov apply -p gracedb -e <gid-or-superevent>`` instead.
    """
    import pathlib

    if not repo:
        repo = None

    event = Event(
        name=name,
        repository=repo,
        calibration={},
    )

    if oldname:
        event.meta["old superevent"] = oldname

    working_dir = os.path.join(config.get("general", "rundir_default"), name)

    event.meta["working directory"] = working_dir
    pathlib.Path(working_dir).mkdir(parents=True, exist_ok=True)
    ledger.update_event(event)


@click.argument("event", default=None)
@event.command()
def delete(event):
    """
    Delete an event from the ledger.
    """
    ledger.delete_event(event_name=event)


@click.argument("event", default=None)
@click.option("--json", "json_data", default=None)
@event.command()
def configurator(event, json_data=None):
    """Add data from the configurator."""
    event = ledger.get_event(event)
    if json_data:
        with open(json_data, "r") as datafile:
            data = json.load(datafile)

    new_data = {"quality": {}, "priors": {}}
    new_data["quality"]["sample-rate"] = int(data["srate"])
    new_data["quality"]["lower-frequency"] = {}
    # Factor 0.875 to account for PSD roll off
    new_data["likelihood"]["upper-frequency"] = {
        ifo: int(0.875 * data["srate"] / 2) for ifo in event.meta["interferometers"]
    }
    new_data["quality"]["start-frequency"] = data["f_start"]
    new_data["quality"]["segment-length"] = int(data["seglen"])
    new_data["quality"]["window-length"] = int(data["seglen"])
    new_data["quality"]["psd-length"] = int(data["seglen"])

    def decide_fref(freq):
        if (freq >= 5) and (freq < 10):
            return 5
        else:
            return floor(freq / 10) * 10

    new_data["quality"]["reference-frequency"] = decide_fref(data["f_ref"])

    new_data["priors"]["amp order"] = data["amp_order"]
    new_data["priors"]["chirp-mass"] = [data["chirpmass_min"], data["chirpmass_max"]]

    update(event.meta, new_data)
    ledger.update_event(event)


@click.option(
    "--calibration",
    "calibration",
    multiple=True,
    default=[None],
    help="The location of the calibration files.",
)
@click.argument("event")
@event.command()
def calibration(event, calibration):
    """
    Add calibration files to an event from a filepath.
    """
    event = ledger.get_event(event)[0]
    calibrations = {}
    for cal in calibration:
        calibrations[cal.split(":")[0]] = cal.split(":")[1]
    update(event.meta["data"]["calibration"], calibrations)
    ledger.update_event(event)
