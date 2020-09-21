"""
Make the event issues on the gitlab issue tracker from gracedb.
"""


import asimov
from asimov.event import Event
from asimov import config

from asimov import gitlab
from asimov import config

import numpy as np
import yaml

from ligo.gracedb.rest import GraceDb, HTTPError 
client = GraceDb(service_url=config.get("gracedb", "url"))
r = client.ping()

superevent_iterator = client.superevents('O3B_CBC_CATALOG')
superevent_ids = [superevent['superevent_id'] for superevent in superevent_iterator]

server = gitlab.gitlab.Gitlab(config.get("gitlab", "url"), private_token=config.get("gitlab", "token"))
repository = server.projects.get(config.get("olivaw", "tracking_repository"))


gitlab_events = gitlab.find_events(repository)


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
    return {"LHO": times_lho[keys_lho[np.argmin(np.abs(keys_lho - time))]], "LLO": times_llo[keys_llo[np.argmin(np.abs(keys_llo - time))]]}

    
# Update existing events
for event in gitlab_events:
    
    time = event.event_object.meta['event time'] 

    print(find_calibrations(time))

    envelopes = yaml.dump(find_calibrations(time))
    event.add_note(f"""
## Calibration envelopes
The following calibration envelopes have been found.
```yaml
---
{envelopes}
---
```
""")
