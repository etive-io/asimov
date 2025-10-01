"""
Code for interacting with the condor scheduler.

An important function of asimov is interaction with condor schedulers in order to track the status of running jobs.

In order to improve performance the code caches results from the query to the scheduler.

"""

import os
import datetime
from dateutil import tz
import htcondor
import yaml

from asimov import config, logger, LOGGER_LEVEL

UTC = tz.tzutc()

logger = logger.getChild("condor")
logger.setLevel(LOGGER_LEVEL)


def datetime_from_epoch(dt, tzinfo=UTC):
    """Returns the `datetime.datetime` for a given Unix epoch

    Parameters
    ----------
    dt : `float`
        a Unix timestamp

    tzinfo : `datetime.tzinfo`, optional
        the desired timezone for the output `datetime.datetime`

    Returns
    -------
    datetime.datetime
        the datetime that represents the given Unix epoch
    """
    return datetime.datetime.utcfromtimestamp(dt).replace(tzinfo=tzinfo)


def submit_job(submit_description):
    """
    Submit a new job to the condor scheduller
    """

    hostname_job = htcondor.Submit(submit_description)

    try:
        # There should really be a specified submit node, and if there is, use it.
        schedulers = htcondor.Collector().locate(
            htcondor.DaemonTypes.Schedd, config.get("condor", "scheduler")
        )
        schedd = htcondor.Schedd(schedulers)
        logger.info(f"Found scheduler: {schedd}")
    except:  # NoQA
        # If you can't find a specified scheduler, try until it works
        collectors = htcondor.Collector().locateAll(htcondor.DaemonTypes.Schedd)
        logger.info("Searching for a scheduler of any kind")
        for collector in collectors:
            logger.info(f"Found {collector}")
            schedd = htcondor.Schedd(collector)
            try:
                with schedd.transaction() as txn:
                    cluster_id = hostname_job.queue(txn)
                    break
            except htcondor.HTCondorIOError:
                logger.info(f"{collector} cannot receive jobs")

    return cluster_id


def delete_job(cluster_id):
    try:
        # There should really be a specified submit node, and if there is, use it.
        schedulers = htcondor.Collector().locate(
            htcondor.DaemonTypes.Schedd, config.get("condor", "scheduler")
        )
        schedd = htcondor.Schedd(schedulers)
    except:  # NoQA
        # If you can't find a specified scheduler, use the first one you find
        schedd = htcondor.Schedd()
    schedd.act(htcondor.JobAction.Remove, f"ClusterId == {cluster_id}")


def collect_history(cluster_id):
    try:
        # There should really be a specified submit node, and if there is, use it.
        schedulers = htcondor.Collector().locate(
            htcondor.DaemonTypes.Schedd, config.get("condor", "scheduler")
        )
        schedd = htcondor.Schedd(schedulers)
    except:  # NoQA
        # If you can't find a specified scheduler, use the first one you find
        collectors = htcondor.Collector().locateAll(htcondor.DaemonTypes.Schedd)
        logger.info("Searching for a scheduler of any kind")
        for collector in collectors:
            logger.info(f"Found {collector}")
            schedd = htcondor.Schedd(collector)
            HISTORY_CLASSADS = [
                "CompletionDate",
                "CpusProvisioned",
                "GpusProvisioned",
                "CumulativeSuspensionTime",
                "EnteredCurrentStatus",
                "MaxHosts",
                "RemoteWallClockTime",
                "RequestCpus",
            ]
            try:
                jobs = schedd.history(
                    f"ClusterId == {cluster_id}", projection=HISTORY_CLASSADS
                )
                logger.info(f"Jobs found: {jobs}")
                break
            except htcondor.HTCondorIOError:
                logger.info(f"{collector} cannot receive jobs")
        if len(list(jobs)) == 0:
            raise ValueError
        output = {}
        for job in jobs:
            end = float(job["CompletionDate"]) or float(job["EnteredCurrentStatus"])
            output["end"] = datetime_from_epoch(end).strftime("%Y-%m-%d")
            # get cpus and gpus
            try:
                cpus = float(job["CpusProvisioned"])
            except (KeyError, ValueError):
                cpus = float(job.get("RequestCpus", 1))
            try:
                gpus = float(job["GpusProvisioned"])
            except (KeyError, ValueError):
                gpus = float(job.get("RequestGpus", 1))
            output["cpus"] = cpus
            output["gpus"] = gpus
            # get total job time (seconds)
            runtime = float(job["RemoteWallClockTime"]) - float(
                job["CumulativeSuspensionTime"]
            )
            # if the job didn't get assigned a MATCH_GLIDEIN_Site,
            # then it ran in the local pool
            output["runtime"] = runtime
        return output


class CondorJob(yaml.YAMLObject):
    """
    Represent a specific condor Job.
    """

    yaml_loader = yaml.SafeLoader
    yaml_tag = "!CondorJob"

    def __init__(self, idno, command, hosts, status, **kwargs):
        """
        A representation of a condor job on a scheduler.

        Parameters
        ----------
        idno : int
           The jobId or ClusterId for the job.
        command: str
           The command being run.
        hosts: int
           The number of hosts currently processing the job.
        status: int
           The status condition for the job.
        """

        self.idno = idno
        self.command = command
        self.hosts = hosts
        self._status = status

        for key, value in kwargs.items():
            setattr(self, key, value)

        for key, value in kwargs.items():
            setattr(self, key, value)

    def __repr__(self):
        out = f"<htcondor job | {self.idno} | {self.status} "
        out += f"| {self.hosts} | {self.name} | {len(self.subjobs)} subjobs >"
        return out

    def __str__(self):
        return repr(self)

    def to_dict(self):
        """
        Turn a job into a dictionary representation.
        """
        output = {}

        output["name"] = self.name
        output["id"] = self.idno
        output["hosts"] = self.hosts
        output["status"] = self._status
        output["command"] = self.command

        if self.dag:
            output["dag id"] = self.dag

        return output

    @classmethod
    def from_dict(cls, dictionary):
        """
        Create a respresentation from a dictionary.

        Parameters
        ----------
        dictionary : dict
           The dictionary of job parameters.

        Returns
        -------
        `CondorJob`
           A condor job object.
        """
        cls = cls(
            idno=dictionary["id"],
            command=dictionary["command"],
            hosts=dictionary["hosts"],
            status=dictionary["status"],
        )
        if "name" in dictionary:
            cls.name = dictionary["name"]
        else:
            cls.name = "asimov job"
        if "dag id" in dictionary:
            cls.dag = dictionary["dag id"]
        else:
            cls.dag = None
        cls.subjobs = []

        return cls

    def add_subjob(self, job):
        """
        Add a subjob of this job.

        Parameters
        ----------
        job : `CondorJob`
           The job which is a subjob.
        """
        self.subjobs.append(job)

    @property
    def status(self):
        """
        Get the status of the job.

        Returns
        -------
        str
          A description of the status of the job.
        """
        statuses = {
            0: "Unexplained",
            1: "Idle",
            2: "Running",
            3: "Removed",
            4: "Completed",
            5: "Held",
            6: "Submission error",
        }
        return statuses[self._status]


class CondorJobList:
    """
    Store the list of running condor jobs.

    The list is automatically pulled from the condor scheduller if it is
    more than 15 minutes old (by default)
    """

    def __init__(self):
        self.jobs = {}
        cache = os.path.join(".asimov", "_cache_jobs.yaml")
        if not os.path.exists(cache):
            self.refresh()
        else:
            age = -os.stat(cache).st_mtime + datetime.datetime.now().timestamp()
            logger.info(f"Condor cache is {age} seconds old")
            if float(age) < float(config.get("condor", "cache_time")):
                with open(cache, "r") as f:
                    self.jobs = yaml.safe_load(f)
            else:
                self.refresh()

    def refresh(self):
        """
        Poll the schedulers to get the list of running jobs and update the database.
        """
        data = []

        logger.info("Updating the condor cache")

        try:
            collectors = htcondor.Collector().locateAll(htcondor.DaemonTypes.Schedd)
        except htcondor.HTCondorLocateError as e:
            logger.error("Could not find a valid condor scheduler")
            logger.exception(e)
            raise e

        for schedd_ad in collectors:
            try:
                schedd = htcondor.Schedd(schedd_ad)
                jobs = schedd.query(
                    opts=htcondor.htcondor.QueryOpts.DefaultMyJobsOnly,
                    projection=[
                        "ClusterId",
                        "Cmd",
                        "CurrentHosts",
                        "HoldReason",
                        "JobStatus",
                        "DAG_Status",
                        "JobBatchName",
                        "DAGManJobId",
                    ],
                )
                data += jobs
            except:  # NoQA
                pass

            retdat = []
            for datum in data:
                if "ClusterId" in datum:
                    job = dict(
                        id=int(float(datum["ClusterId"])),
                        command=datum["Cmd"],
                        hosts=datum["CurrentHosts"],
                        status=datum["JobStatus"],
                    )
                    if "HoldReason" in datum:
                        job["hold"] = datum["HoldReason"]
                    if "JobBatchName" in datum:
                        job["name"] = datum["JobBatchName"]
                    if "DAG_Status" not in datum and "DAGManJobID" in datum:
                        job["dag id"] = int(float(datum["DAGManJobId"]))

                retdat.append(CondorJob.from_dict(job))

        for datum in retdat:
            if not datum.dag:
                self.jobs[datum.idno] = datum
                # # Now search for subjobs
        for datum in retdat:
            if datum.dag:
                if datum.dag in self.jobs:
                    self.jobs[datum.dag].add_subjob(datum)
                else:
                    self.jobs[datum.idno] = datum.to_dict()

        with open(os.path.join(".asimov", "_cache_jobs.yaml"), "w") as f:
            f.write(yaml.dump(self.jobs))


def get_job_priority(job_id):
    """
    Returns the priority of a job given its id.
    This is useful when some conitioning happens and should lead
    to a change in the analysis priority compared to other events.
    This returns None if the information cannot be found.

    Parameters
    ----------
    - job_id: the condor job id for which we want to get the priority
    """

    # make collector to query the info
    schedd = htcondor.Schedd()

    # query job info
    job_info = schedd.query(f"ClusterId == {job_id}.0")
    if job_info:
        priority = job_info[0].get("JobPrio", None)
        return priority
    else:
        return None


def change_job_priority(job_id, extra_priority, use_old=False):
    """
    Function to change the job priority for a given job.

    Parameters:
    -----------
    - job_id: the condor job id for which we want to change the priority
    - extra_priority: the extra priority that we want to add to the job
    - use_old: if True, we add the new priority to the old one. Else, we simply replace it
    """

    # setup a schedduler to query the priority
    schedd = htcondor.Schedd()
    main_job_info = schedd.query(f"ClusterId == {job_id}")
    all_jobs = schedd.query()

    if main_job_info:
        # look for all the jobs needing to be updated (also child jobs)
        jobs_to_update = []
        for job in all_jobs:
            if "JobBatchId" in job.keys():
                if job["JobBatchId"] == main_job_info[0]["JobBatchId"]:
                    jobs_to_update.append(job["ClusterId"])

        for j_id in jobs_to_update:
            if use_old:
                extra_priority += get_job_priority(j_id)
            schedd.edit(f"ClusterId == {j_id}", {"JobPrio": extra_priority})
            logger.info(f"Changed the priority of job {j_id} to {extra_priority}")
    else:
        logger.warning(f"Unable to adapt the priority for job {job_id}")
