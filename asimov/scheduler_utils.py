"""
Helper utilities for scheduler integration in asimov.

This module provides convenience functions and decorators for using
the scheduler API in pipelines and other parts of asimov.
"""

import configparser
import functools
from asimov import config, logger
from asimov.scheduler import get_scheduler, JobDescription

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
        except (configparser.NoOptionError, configparser.NoSectionError, KeyError):
            pass
    
    return get_scheduler(scheduler_type, **kwargs)


def create_job_from_dict(job_dict):
    """
    Create a JobDescription from a dictionary.
    
    This is a convenience function to convert existing HTCondor-style
    job dictionaries to JobDescription objects.
    
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
    """
    # Extract required parameters
    executable = job_dict.pop("executable")
    output = job_dict.pop("output")
    error = job_dict.pop("error")
    log = job_dict.pop("log")
    
    # Convert HTCondor-specific resource parameters to generic ones
    kwargs = job_dict.copy()
    
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
