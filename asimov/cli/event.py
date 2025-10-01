import ast
import json
import os
from math import floor

import click
import gwpy
import gwpy.timeseries
import numpy as np
from glue.lal import Cache
from gwdatafind import find_urls

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


@click.option("--search", "-s", "search", default=None, help="Search criteria.")
@click.option(
    "--old", "oldname", default=None, help="The old superevent ID for this event."
)
@click.option(
    "--gid",
    "gid",
    default=None,
    help="The GraceDB GID for the event (for legacy events)",
)
@click.option(
    "--superevent", "superevent", default=None, help="The superevent for the event."
)
@click.option(
    "--repository",
    "repo",
    default=None,
    help="The location of the repository for this event.",
)
@click.option("--name", "-n", "name", default=None, help="The name for the event.")
@event.command()
def create(name=None, oldname=None, gid=None, superevent=None, repo=None, search=None):
    """
    Create a new event record in the ledger.

    Parameters
    ----------
    superevent : str
       The ID of the superevent to be used from GraceDB
    name : str
       The name of the event to be recorded in the issue tracker
    names : path, optional
        The path to the name file which maps between old and new super event IDs
    oldname : str, optional
        The old name of the event.
    search : str, optional
        A string of search criteria
    """
    import pathlib

    if gid or superevent or search:
        from ligo.gracedb.rest import GraceDb

        client = GraceDb(service_url=config.get("gracedb", "url"))

    if search:
        event_iterator = client.events(search)

        for event in event_iterator:

            event = Event(
                name=name,
                repository=repo,
                calibration={},
            )
            working_dir = os.path.join(config.get("general", "rundir_default"), name)

            event.meta["working directory"] = working_dir
            pathlib.Path(working_dir).mkdir(parents=True, exist_ok=True)
            ledger.update_event(event)

    if superevent:
        data = client.superevent(superevent).json()
        try:
            event_data = client.event(data["preferred_event"]).json()
        except KeyError:
            event_data = data["preferred_event_data"]

        gid = data["preferred_event_data"]["graceid"]
        interferometers = event_data["instruments"].split(",")
        if not name:
            name = superevent
    elif gid:
        event_data = client.event(gid).json()
        interferometers = event_data["instruments"].split(",")
        if not name:
            name = gid
    else:
        event_data = None
        interferometers = []

    if not repo:
        repo = None

    event = Event(
        name=name,
        repository=repo,
        calibration={},
        interferometers=interferometers,
    )

    if oldname:
        event.meta["old superevent"] = oldname
    if gid:
        event.meta["event time"] = event_data["gpstime"]

    if "ligo" not in event.meta:
        event.meta["ligo"] = {}

    event.meta["ligo"]["preferred event"] = gid

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


# @click.option("--event", "event", default=None, help="The event which the ledger should be returned for, optional.")
# @olivaw.command()
@click.argument("event")
@event.command()
def checkifo(event):
    event = ledger.get_event(event)
    if "event time" not in event.event_object.meta:
        print(f"Time not found {event.event_object.name}")
    time = event.event_object.meta["event time"]
    gpsstart = time - 600
    gpsend = time + 600
    bits = ["Bit 0", "Bit 1", "Bit 2"]

    active_ifo = []
    for ifo in ["L1", "H1", "V1"]:
        frametypes = event.event_object.meta["data"]["frame-types"]
        urls = find_urls(
            site=f"{ifo[0]}",
            frametype=frametypes[ifo],
            gpsstart=gpsstart,
            gpsend=gpsend,
        )
        datacache = Cache.from_urls(urls)
        if len(datacache) == 0:
            print(f"No {ifo} data found.")
            continue

        if "state vector" in event.meta:
            state_vector_channel = event.meta["state vector"]
        else:
            state_vector_channel = ast.literal_eval(config.get("data", "state-vector"))

        state = gwpy.timeseries.StateVector.read(
            datacache,
            state_vector_channel[ifo],
            start=gpsstart,
            end=gpsend,
            pad=0,  # padding data so that errors are not raised even if found data are not continuous.
        )
        if not np.issubdtype(state.dtype, np.unsignedinteger):
            # if data are not unsigned integers, cast to them now so that
            # we can determine the bit content for the flags
            state = state.astype(
                "uint32",
                casting="unsafe",
                subok=True,
                copy=False,
            )
        flags = state.to_dqflags()

        segments = flags[bits[0]].active
        for bit in bits:
            segments -= ~flags[bit].active

        if len(segments) > 0:
            active_ifo += [ifo]
    click.echo(event.name)
    if event.meta["interferometers"] != active_ifo:
        print(f"Gitlab data\t{event.meta['interferometers']}")
        print(f"Recommended IFOS\t{active_ifo}")

    event.meta["interferometers"] = active_ifo
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
