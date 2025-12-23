"""
Helper utilities for scheduler integration in asimov.

This module provides convenience functions and decorators for using
the scheduler API in pipelines and other parts of asimov.
"""

import configparser
import functools
from asimov import config, logger
from asimov.scheduler import get_scheduler, JobDescription, JobList

logger = logger.getChild("scheduler_utils")


def get_configured_scheduler():
    """
    Get a scheduler instance based on the asimov configuration.
    
    This function reads the scheduler configuration from asimov.conf
    and returns an appropriate scheduler instance.
    
    Returns
    -------
    Scheduler
        A configured scheduler instance (default: HTCondor)
        
    Examples
    --------
    >>> scheduler = get_configured_scheduler()
    >>> job = JobDescription(executable="/bin/echo", output="out.log", 
    ...                      error="err.log", log="job.log")
    >>> cluster_id = scheduler.submit(job)
    """
    try:
        scheduler_type = config.get("scheduler", "type")
    except (configparser.NoOptionError, configparser.NoSectionError, KeyError):
        scheduler_type = "htcondor"
    
    # Get scheduler-specific configuration
    kwargs = {}
    if scheduler_type == "htcondor":
        try:
            schedd_name = config.get("condor", "scheduler")
            kwargs["schedd_name"] = schedd_name
        except (configparser.NoOptionError, configparser.NoSectionError, KeyError) as exc:
            logger.debug(
                "No specific Condor scheduler configured; using default schedd. (%s)",
                exc,
            )
    
    return get_scheduler(scheduler_type, **kwargs)


def create_job_from_dict(job_dict):
    """
    Create a JobDescription from a dictionary.
    
    This is a convenience function to convert existing HTCondor-style
    job dictionaries to JobDescription objects. The input dictionary
    is not modified.
    
    Parameters
    ----------
    job_dict : dict
        A dictionary containing job parameters. Should have at least:
        - executable: path to the executable
        - output: path for stdout
        - error: path for stderr
        - log: path for job log
        
    Returns
    -------
    JobDescription
        A JobDescription object created from the dictionary
        
    Examples
    --------
    >>> job_dict = {
    ...     "executable": "/bin/echo",
    ...     "output": "out.log",
    ...     "error": "err.log",
    ...     "log": "job.log",
    ...     "request_cpus": "4",
    ...     "request_memory": "8GB"
    ... }
    >>> job = create_job_from_dict(job_dict)
    >>> # job_dict is unchanged after the call
    """
    # Make a copy to avoid modifying the original dictionary
    job_dict_copy = job_dict.copy()
    
    # Extract required parameters
    executable = job_dict_copy.pop("executable")
    output = job_dict_copy.pop("output")
    error = job_dict_copy.pop("error")
    log = job_dict_copy.pop("log")
    
    # Convert HTCondor-specific resource parameters to generic ones
    kwargs = job_dict_copy
    
    # Map HTCondor resource parameters to generic ones
    if "request_cpus" in kwargs:
        kwargs["cpus"] = kwargs.pop("request_cpus")
    if "request_memory" in kwargs:
        kwargs["memory"] = kwargs.pop("request_memory")
    if "request_disk" in kwargs:
        kwargs["disk"] = kwargs.pop("request_disk")
    
    return JobDescription(
        executable=executable,
        output=output,
        error=error,
        log=log,
        **kwargs
    )


def scheduler_aware(func):
    """
    Decorator to make pipeline methods scheduler-aware.
    
    This decorator wraps pipeline methods (like submit_dag) to provide
    access to the configured scheduler instance via self.scheduler.
    
    Parameters
    ----------
    func : callable
        The method to decorate
        
    Returns
    -------
    callable
        The wrapped method
        
    Examples
    --------
    >>> class MyPipeline:
    ...     @scheduler_aware
    ...     def submit_dag(self):
    ...         # self.scheduler is now available
    ...         cluster_id = self.scheduler.submit(job)
    ...         return cluster_id
    """
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        # Add scheduler instance to the pipeline object if not already present
        if not hasattr(self, 'scheduler'):
            self.scheduler = get_configured_scheduler()
        return func(self, *args, **kwargs)
    return wrapper


def get_job_list(cache_time=None):
    """
    Get a JobList instance for monitoring running jobs.
    
    This function creates a JobList that queries the configured scheduler
    and caches the results for performance.
    
    Parameters
    ----------
    cache_time : int, optional
        Maximum age of cache in seconds. If None, uses the value from
        config or defaults to 900 (15 minutes).
        
    Returns
    -------
    JobList
        A JobList instance containing all running jobs.
        
    Examples
    --------
    >>> job_list = get_job_list()
    >>> if 12345 in job_list.jobs:
    ...     job = job_list.jobs[12345]
    ...     print(f"Job status: {job.status}")
    """
    scheduler = get_configured_scheduler()
    
    if cache_time is None:
        try:
            cache_time = float(config.get("condor", "cache_time"))
        except (configparser.NoOptionError, configparser.NoSectionError, KeyError):
            cache_time = 900  # Default to 15 minutes
    
    return JobList(scheduler, cache_time=cache_time)
