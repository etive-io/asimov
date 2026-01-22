"""
Make the event issues on the gitlab issue tracker from gracedb.
"""
import os

import asimov
from asimov.event import Event, DescriptionException
from asimov import config

from asimov import gitlab
from asimov import config

import numpy as np
import yaml

from git.exc import GitCommandError
import click

#from ligo.gracedb.rest import GraceDb, HTTPError 
#client = GraceDb(service_url=config.get("gracedb", "url"))
#r = client.ping()

#superevent_iterator = client.superevents('O3B_CBC_CATALOG')
#superevent_ids = [superevent['superevent_id'] for superevent in superevent_iterator]

server = gitlab.gitlab.Gitlab(config.get("gitlab", "url"), private_token=config.get("gitlab", "token"))
repository = server.projects.get(config.get("olivaw", "tracking_repository"))

CALIBRATION_NOTE = """
## Calibration envelopes
The following calibration envelopes have been found.
```yaml
---
{}
---
```
"""

@click.group()
def olivaw():
    """
    This is the main olivaw program which runs the DAGs for each event issue.
    """
    click.echo("Running olivaw")

    global rundir
    rundir = os.getcwd()


def find_calibrations(time):
    with open("LLO_calibs.txt") as llo_file:
        data_llo = llo_file.read().split("\n")
        data_llo = [datum for datum in data_llo if datum[-16:]=="FinalResults.txt"]
        times_llo = {int(datum.split("GPSTime_")[1].split("_C01")[0]): datum for datum in data_llo}
    
    with open("LHO_calibs.txt") as llo_file:
        data_lho = llo_file.read().split("\n")
        data_lho = [datum for datum in data_lho if datum[-16:]=="FinalResults.txt"]
        times_lho = {int(datum.split("GPSTime_")[1].split("_C01")[0]): datum for datum in data_lho}
        
    keys_llo = np.array(list(times_llo.keys())) 
    keys_lho = np.array(list(times_lho.keys())) 

    return {"H1": times_lho[keys_lho[np.argmin(np.abs(keys_lho - time))]], "L1": times_llo[keys_llo[np.argmin(np.abs(keys_llo - time))]], "V1": "/home/cbc/pe/O3/calibrationenvelopes/Virgo/V_O3a_calibrationUncertaintyEnvelope_magnitude5percent_phase35milliradians10microseconds.txt"}

    
# Update existing events
for event in gitlab_events:
    print(event.name)
    try:
        event.event_object._check_calibration()
    except DescriptionException:
        time = event.event_object.meta['event time'] 

        calibrations = find_calibrations(time)

        envelopes = yaml.dump({"calibration": calibrations})
        event.add_note(f"""
## Calibration envelopes
The following calibration envelopes have been found.
```yaml
---
{envelopes}
---
```
""")
>>>>>>> cb204b61f687395eb980468da3b8ced48c5c7e40

@click.option("--event", "event", default=None, help="The event which the ledger should be returned for, optional.")
@olivaw.command()
def calibration(event):    
    gitlab_events = gitlab.find_events(repository, subset=event)
    # Update existing events
    for event in gitlab_events:
        if "disable_repo" in event.event_object.meta:
            if event.event_object.meta['disable_repo'] == True:
                continue
        try:
            event.event_object._check_calibration()
        except DescriptionException:
            print(event.title)
            time = event.event_object.meta['event time'] 

            calibrations = find_calibrations(time)
            print(calibrations)
            # try:
            for ifo, envelope in calibrations.items():
                description = f"Added calibration {envelope} for {ifo}."
                try:
                    event.event_object.repository.add_file(os.path.join(f"/home/cal/public_html/uncertainty/O3C01/{ifo}", envelope), f"analyses/calibration/{ifo}.dat", 
                                                       commit_message=description)
                except GitCommandError as e:
                    if "nothing to commit," in e.stderr:
                        pass
                calibrations[ifo] = f"analyses/calibration/{ifo}.dat"
            envelopes = yaml.dump({"calibration": calibrations})
            event.add_note(CALIBRATION_NOTE.format(envelopes))

olivaw()
