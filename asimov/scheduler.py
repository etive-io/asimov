"""
This module contains logic for interacting with a scheduling system.

Supported Schedulers are:

- HTCondor
- Slurm (planned)

"""

import htcondor
from abc import ABC, abstractmethod


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
            with self.schedd.transaction() as txn:
                cluster_id = submit_obj.queue(txn)
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

        # Map generic resource parameters to HTCondor-specific ones
        description["request_cpus"] = self.kwargs.get("cpus", 1)
        description["request_memory"] = self.kwargs.get("memory", "1GB")
        description["request_disk"] = self.kwargs.get("disk", "1GB")
        
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