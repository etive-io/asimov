"""
This module contains logic for interacting with a scheduling system.

Supported Schedulers are:

- HTCondor

"""

import htcondor

class Scheduler:
    """ 
    The base class which represents all supported schedulers.
    """

    def submit(self, job_description):
        raise NotImplementedError 
    

class HTCondor(Scheduler):
    def submit(self, job_description):
        """
        Submit a job to the condor schedd.
        """
        schedd = htcondor.Schedd()
        submit_result = schedd.submit(job_description)

        return submit_result

class JobDescription: 
    """
    A class which represents the description of a job to be submitted to a scheduler.

    This will allow jobs to be easily described in a scheduler-agnostic way.
    """

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

        """
        self.executable = executable
        self.output = output
        self.error = error
        self.log = log
        self.kwargs = kwargs


    def to_htcondor(self):
        """
        Create a submit description for the htcondor scheduler.
        """
        description = {}
        description["executable"] = self.executable
        description["output"] = self.output
        description["error"] = self.error
        description["log"] = self.log 

        description["request_cpus"] = self.kwargs.get("cpus", 1)
        description["request_memory"] = self.kwargs.get("memory", "1GB")
        description["request_disk"] = self.kwargs.get("disk", "1GB")