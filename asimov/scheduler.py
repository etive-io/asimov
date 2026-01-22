"""
This module contains logic for interacting with a scheduling system.

Supported Schedulers are:

- HTCondor
- Slurm (planned)

"""

import os
import datetime
import yaml
import warnings
from abc import ABC, abstractmethod

try:
    warnings.filterwarnings("ignore", module="htcondor2")
    import htcondor2 as htcondor  # NoQA
    import classad2 as classad  # NoQA
except ImportError:
    warnings.filterwarnings("ignore", module="htcondor")
    import htcondor  # NoQA
    import classad  # NoQA


class Scheduler(ABC):
    """ 
    The base class which represents all supported schedulers.
    """

    @abstractmethod
    def submit(self, job_description):
        """
        Submit a job to the scheduler.
        
        Parameters
        ----------
        job_description : JobDescription or dict
            The job description to submit.
            
        Returns
        -------
        str or int
            The job ID returned by the scheduler.
        """
        raise NotImplementedError
    
    @abstractmethod
    def delete(self, job_id):
        """
        Delete a job from the scheduler.
        
        Parameters
        ----------
        job_id : str or int
            The job ID to delete.
        """
        raise NotImplementedError
    
    @abstractmethod
    def query(self, job_id=None):
        """
        Query the scheduler for job status.
        
        Parameters
        ----------
        job_id : str or int, optional
            The job ID to query. If None, query all jobs.
            
        Returns
        -------
        dict or list
            Job status information.
        """
        raise NotImplementedError
    
    @abstractmethod
    def submit_dag(self, dag_file, batch_name=None, **kwargs):
        """
        Submit a DAG (Directed Acyclic Graph) workflow to the scheduler.
        
        Parameters
        ----------
        dag_file : str
            Path to the DAG file to submit.
        batch_name : str, optional
            A name for the batch of jobs.
        **kwargs
            Additional scheduler-specific parameters.
            
        Returns
        -------
        int
            The job ID (cluster ID) returned by the scheduler.
        """
        raise NotImplementedError
    
    @abstractmethod
    def query_all_jobs(self):
        """
        Query all jobs from the scheduler.
        
        This method is used to get a list of all jobs currently in the scheduler
        queue, which is useful for monitoring and status checking.
        
        Returns
        -------
        list of dict
            A list of dictionaries, each containing job information with keys:
            - id: Job ID
            - command: Command being executed
            - hosts: Number of hosts
            - status: Job status (integer code or string)
            - name: Job name (optional)
            - dag id: Parent DAG ID if this is a subjob (optional)
        """
        raise NotImplementedError


class HTCondor(Scheduler):
    """
    Scheduler implementation for HTCondor.
    """
    
    def __init__(self, schedd_name=None):
        """
        Initialize the HTCondor scheduler.
        
        Parameters
        ----------
        schedd_name : str, optional
            The name of the schedd to use. If None, will try to find one automatically.
        """
        self.schedd_name = schedd_name
        self._schedd = None
    
    @property
    def schedd(self):
        """Get or create the schedd connection."""
        if self._schedd is None:
            if self.schedd_name:
                try:
                    schedulers = htcondor.Collector().locate(
                        htcondor.DaemonTypes.Schedd, self.schedd_name
                    )
                    self._schedd = htcondor.Schedd(schedulers)
                except (htcondor.HTCondorLocateError, htcondor.HTCondorIOError):
                    # Fall back to default schedd if we can't locate the named one
                    self._schedd = htcondor.Schedd()
            else:
                self._schedd = htcondor.Schedd()
        return self._schedd
    
    def submit(self, job_description):
        """
        Submit a job to the condor schedd.
        
        Parameters
        ----------
        job_description : JobDescription or dict
            The job description to submit.
            
        Returns
        -------
        int
            The cluster ID of the submitted job.
        """
        # Convert JobDescription to dict if needed
        if isinstance(job_description, JobDescription):
            submit_dict = job_description.to_htcondor()
        else:
            submit_dict = job_description
            
        # Create HTCondor Submit object
        submit_obj = htcondor.Submit(submit_dict)
        
        # Submit the job
        try:
            result = self.schedd.submit(submit_obj)
            cluster_id = result.cluster()
            return cluster_id
        except htcondor.HTCondorIOError as e:
            raise RuntimeError(f"Failed to submit job to HTCondor: {e}")
    
    def delete(self, job_id):
        """
        Delete a job from the HTCondor scheduler.
        
        Parameters
        ----------
        job_id : int
            The cluster ID to delete.
        """
        self.schedd.act(htcondor.JobAction.Remove, f"ClusterId == {job_id}")
    
    def query(self, job_id=None, projection=None):
        """
        Query the HTCondor scheduler for job status.
        
        Parameters
        ----------
        job_id : int, optional
            The cluster ID to query. If None, query all jobs.
        projection : list, optional
            List of attributes to retrieve.
            
        Returns
        -------
        list
            List of job ClassAds.
        """
        if job_id is not None:
            constraint = f"ClusterId == {job_id}"
        else:
            constraint = None
            
        if projection:
            return list(self.schedd.query(constraint=constraint, projection=projection))
        else:
            return list(self.schedd.query(constraint=constraint))
    
    def submit_dag(self, dag_file, batch_name=None, **kwargs):
        """
        Submit a DAG file to the HTCondor scheduler.
        
        Parameters
        ----------
        dag_file : str
            Path to the DAG submit file.
        batch_name : str, optional
            A name for the batch of jobs.
        **kwargs
            Additional HTCondor-specific parameters.
            
        Returns
        -------
        int
            The cluster ID of the submitted DAG.
            
        Raises
        ------
        RuntimeError
            If the DAG submission fails.
        FileNotFoundError
            If the DAG file does not exist.
        """
        if not os.path.exists(dag_file):
            raise FileNotFoundError(f"DAG file not found: {dag_file}")
        
        try:
            # Use HTCondor's Submit.from_dag to create a submit description from the DAG file
            submit_obj = htcondor.Submit.from_dag(dag_file, options={})
            
            # Add batch name if provided
            if batch_name:
                # Set the batch name in the submit description
                submit_obj['JobBatchName'] = batch_name
            
            # Add any additional kwargs to the submit description
            for key, value in kwargs.items():
                submit_obj[key] = value
            
            # Submit the DAG
            result = self.schedd.submit(submit_obj)
            cluster_id = result.cluster()
            
            return cluster_id
            
        except htcondor.HTCondorIOError as e:
            raise RuntimeError(f"Failed to submit DAG to HTCondor: {e}")
        except Exception as e:
            raise RuntimeError(f"Unexpected error submitting DAG: {e}")
    
    def query_all_jobs(self):
        """
        Query all jobs from HTCondor schedulers.
        
        This method queries all available HTCondor schedulers to get a complete
        list of jobs. It's used by the JobList class for monitoring.
        
        Returns
        -------
        list of dict
            A list of dictionaries containing job information.
        """
        data = []
        
        try:
            collectors = htcondor.Collector().locateAll(htcondor.DaemonTypes.Schedd)
        except htcondor.HTCondorLocateError as e:
            raise RuntimeError(f"Could not find a valid HTCondor scheduler: {e}")
        
        for schedd_ad in collectors:
            try:
                schedd = htcondor.Schedd(schedd_ad)
                jobs = schedd.query(
                    opts=htcondor.QueryOpts.DefaultMyJobsOnly,
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
                
                # Convert HTCondor ClassAds to dictionaries
                for job_ad in jobs:
                    if "ClusterId" in job_ad:
                        job_dict = {
                            "id": int(float(job_ad["ClusterId"])),
                            "command": job_ad.get("Cmd", ""),
                            "hosts": job_ad.get("CurrentHosts", 0),
                            "status": job_ad.get("JobStatus", 0),
                        }
                        
                        if "HoldReason" in job_ad:
                            job_dict["hold"] = job_ad["HoldReason"]
                        if "JobBatchName" in job_ad:
                            job_dict["name"] = job_ad["JobBatchName"]
                        if "DAG_Status" not in job_ad and "DAGManJobId" in job_ad:
                            job_dict["dag id"] = int(float(job_ad["DAGManJobId"]))
                        
                        data.append(job_dict)
                        
            except Exception:
                # Skip problematic schedulers
                pass
        
        return data


class Slurm(Scheduler):
    """
    Scheduler implementation for Slurm.
    
    Note: This is a placeholder implementation for future Slurm support.
    """
    
    def __init__(self):
        """Initialize the Slurm scheduler."""
        raise NotImplementedError("Slurm scheduler is not yet implemented")
    
    def submit(self, job_description):
        """Submit a job to Slurm."""
        raise NotImplementedError("Slurm scheduler is not yet implemented")
    
    def delete(self, job_id):
        """Delete a job from Slurm."""
        raise NotImplementedError("Slurm scheduler is not yet implemented")
    
    def query(self, job_id=None):
        """Query Slurm for job status."""
        raise NotImplementedError("Slurm scheduler is not yet implemented")
    
    def submit_dag(self, dag_file, batch_name=None, **kwargs):
        """Submit a DAG to Slurm."""
        raise NotImplementedError("Slurm scheduler is not yet implemented")
    
    def query_all_jobs(self):
        """Query all jobs from Slurm."""
        raise NotImplementedError("Slurm scheduler is not yet implemented")


class Job:
    """
    Scheduler-agnostic representation of a job.
    
    This class provides a common interface for job information across
    different schedulers.
    """
    
    def __init__(self, job_id, command, hosts, status, name=None, dag_id=None, **kwargs):
        """
        Create a Job object.
        
        Parameters
        ----------
        job_id : int
            The job ID or cluster ID.
        command : str
            The command being run.
        hosts : int
            The number of hosts currently processing the job.
        status : int or str
            The status of the job.
        name : str, optional
            The name or batch name of the job.
        dag_id : int, optional
            The DAG ID if this is a subjob.
        **kwargs
            Additional scheduler-specific attributes.
        """
        self.job_id = job_id
        self.command = command
        self.hosts = hosts
        self._status = status
        self.name = name or "asimov job"
        self.dag_id = dag_id
        self.subjobs = []
        
        # Store any additional attributes
        for key, value in kwargs.items():
            setattr(self, key, value)
    
    def add_subjob(self, job):
        """
        Add a subjob to this job.
        
        Parameters
        ----------
        job : Job
            The subjob to add.
        """
        self.subjobs.append(job)
    
    @property
    def status(self):
        """
        Get the status of the job as a string.
        
        Returns
        -------
        str
            A description of the status of the job.
        """
        # Handle both integer status codes and string status
        if isinstance(self._status, int):
            # HTCondor status codes
            statuses = {
                0: "Unexplained",
                1: "Idle",
                2: "Running",
                3: "Removed",
                4: "Completed",
                5: "Held",
                6: "Submission error",
            }
            return statuses.get(self._status, "Unknown")
        else:
            return str(self._status)
    
    def __repr__(self):
        return f"<Job | {self.job_id} | {self.status} | {self.hosts} | {self.name} | {len(self.subjobs)} subjobs>"
    
    def __str__(self):
        return repr(self)
    
    def to_dict(self):
        """
        Convert the job to a dictionary representation.
        
        Returns
        -------
        dict
            Dictionary representation of the job.
        """
        output = {
            "name": self.name,
            "id": self.job_id,
            "hosts": self.hosts,
            "status": self._status,
            "command": self.command,
        }
        
        if self.dag_id:
            output["dag_id"] = self.dag_id
        
        return output


class JobList:
    """
    Scheduler-agnostic list of running jobs.
    
    This class queries the scheduler and caches the results for performance.
    """
    
    def __init__(self, scheduler, cache_file=None, cache_time=900):
        """
        Initialize the job list.
        
        Parameters
        ----------
        scheduler : Scheduler
            The scheduler instance to query.
        cache_file : str, optional
            Path to the cache file. If None, uses ".asimov/_cache_jobs.yaml"
        cache_time : int, optional
            Maximum age of cache in seconds. Default is 900 (15 minutes).
        """
        self.scheduler = scheduler
        self.jobs = {}
        self.cache_file = cache_file or os.path.join(".asimov", "_cache_jobs.yaml")
        self.cache_time = cache_time
        
        # Try to load from cache
        if os.path.exists(self.cache_file):
            age = -os.stat(self.cache_file).st_mtime + datetime.datetime.now().timestamp()
            if float(age) < float(self.cache_time):
                with open(self.cache_file, "r") as f:
                    cached_data = yaml.safe_load(f)
                    # Only use the cached data if it appears to be a mapping of
                    # job-like objects (i.e., dictionaries with the keys
                    # that JobList relies on). Otherwise, fall back to a refresh.
                    if isinstance(cached_data, dict) and cached_data:
                        valid_cache = True
                        for job_obj in cached_data.values():
                            # Cached jobs are stored as dictionaries produced by
                            # Job.to_dict(), so we validate based on required keys.
                            if not isinstance(job_obj, dict):
                                valid_cache = False
                                break
                            if "job_id" not in job_obj or "dag_id" not in job_obj:
                                valid_cache = False
                                break
                        if valid_cache:
                            self.jobs = cached_data
                            return
        
        # Cache is stale, invalid, or doesn't exist, refresh from scheduler
        self.refresh()
    
    def refresh(self):
        """
        Poll the scheduler to get the list of running jobs and update the cache.
        """
        # Query all jobs from the scheduler
        try:
            raw_jobs = self.scheduler.query_all_jobs()
        except Exception as e:
            raise RuntimeError(f"Failed to query jobs from scheduler: {e}")
        
        # Process the raw jobs into Job objects
        self.jobs = {}
        all_jobs = []
        
        for job_data in raw_jobs:
            job = self._create_job_from_data(job_data)
            all_jobs.append(job)
        
        # Organize jobs by main jobs and subjobs
        for job in all_jobs:
            if not job.dag_id:
                self.jobs[job.job_id] = job
        
        # Add subjobs to their parent jobs
        for job in all_jobs:
            if job.dag_id:
                if job.dag_id in self.jobs:
                    self.jobs[job.dag_id].add_subjob(job)
                else:
                    # If DAG parent doesn't exist, store this job as a standalone job
                    self.jobs[job.job_id] = job
        
        # Save to cache
        os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
        # Store Job objects directly so that cache loading logic, which expects
        # Job instances with methods, can validate and use the cached data.
        with open(self.cache_file, "w") as f:
            f.write(yaml.dump(self.jobs))
    
    def _create_job_from_data(self, job_data):
        """
        Create a Job object from scheduler-specific data.
        
        Parameters
        ----------
        job_data : dict
            Scheduler-specific job data.
            
        Returns
        -------
        Job
            A Job object.
        """
        # This method can be overridden by scheduler-specific implementations
        # For now, we assume the data is already in a compatible format
        return Job(
            job_id=job_data.get("id", job_data.get("job_id")),
            command=job_data.get("command", ""),
            hosts=job_data.get("hosts", 0),
            status=job_data.get("status", 0),
            name=job_data.get("name"),
            dag_id=job_data.get("dag_id", job_data.get("dag id")),
            **{k: v for k, v in job_data.items() if k not in ["id", "job_id", "command", "hosts", "status", "name", "dag id", "dag_id"]}
        )


def get_scheduler(scheduler_type="htcondor", **kwargs):
    """
    Factory function to get the appropriate scheduler instance.
    
    Parameters
    ----------
    scheduler_type : str
        The type of scheduler to create. Options: "htcondor", "slurm"
    **kwargs
        Additional keyword arguments to pass to the scheduler constructor.
        
    Returns
    -------
    Scheduler
        An instance of the requested scheduler.
        
    Raises
    ------
    ValueError
        If an unknown scheduler type is requested.
    """
    scheduler_type = scheduler_type.lower()
    
    if scheduler_type == "htcondor":
        return HTCondor(**kwargs)
    elif scheduler_type == "slurm":
        return Slurm(**kwargs)
    else:
        raise ValueError(f"Unknown scheduler type: {scheduler_type}")

class JobDescription: 
    """
    A class which represents the description of a job to be submitted to a scheduler.

    This will allow jobs to be easily described in a scheduler-agnostic way.
    """
    
    # Mapping of generic resource parameters to HTCondor-specific parameters
    HTCONDOR_RESOURCE_MAPPING = {
        "cpus": "request_cpus",
        "memory": "request_memory",
        "disk": "request_disk",
    }

    def __init__(self, 
                 executable,
                 output,
                 error,
                 log,
                 **kwargs,
                 ):
        """
        Create a job description object.

        Parameters
        ----------
        executable : str, path
          The path to the executable to be used to run this job.
        output : str, path
          The location where stdout from the program should be written.
        error : str, path 
          The location where the stderr from the program should be written.
        log : str, path
          The location where log messages from the scheduler should be written for this job.
        **kwargs
          Additional scheduler-specific parameters.

        """
        self.executable = executable
        self.output = output
        self.error = error
        self.log = log
        self.kwargs = kwargs


    def to_htcondor(self):
        """
        Create a submit description for the htcondor scheduler.
        
        Returns
        -------
        dict
            A dictionary containing the HTCondor submit description.
        """
        description = {}
        description["executable"] = self.executable
        description["output"] = self.output
        description["error"] = self.error
        description["log"] = self.log 

        # Map generic resource parameters to HTCondor-specific ones using the mapping
        for generic_key, htcondor_key in self.HTCONDOR_RESOURCE_MAPPING.items():
            if generic_key in self.kwargs:
                description[htcondor_key] = self.kwargs[generic_key]
        
        # Set defaults for resource parameters if not provided
        description.setdefault("request_cpus", 1)
        description.setdefault("request_memory", "1GB")
        description.setdefault("request_disk", "1GB")
        
        # Add any additional kwargs to the description
        # Skip the generic resource parameters as they've already been mapped
        for key, value in self.kwargs.items():
            if key not in self.HTCONDOR_RESOURCE_MAPPING:
                description[key] = value
        
        return description
    
    def to_slurm(self):
        """
        Create a submit description for the Slurm scheduler.
        
        Returns
        -------
        dict
            A dictionary containing the Slurm submit description.
            
        Note
        ----
        This is a placeholder for future Slurm support.
        """
        raise NotImplementedError("Slurm conversion is not yet implemented")
    
    def to_dict(self, scheduler_type="htcondor"):
        """
        Convert the job description to a scheduler-specific dictionary.
        
        Parameters
        ----------
        scheduler_type : str
            The type of scheduler. Options: "htcondor", "slurm"
            
        Returns
        -------
        dict
            The scheduler-specific job description.
        """
        scheduler_type = scheduler_type.lower()
        
        if scheduler_type == "htcondor":
            return self.to_htcondor()
        elif scheduler_type == "slurm":
            return self.to_slurm()
        else:
            raise ValueError(f"Unknown scheduler type: {scheduler_type}")