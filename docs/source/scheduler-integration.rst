Scheduler Integration Guide
============================

This guide explains how to use the scheduler abstraction in asimov pipelines and other components.

Overview
--------

Asimov now includes a scheduler abstraction layer that provides a uniform interface for
interacting with different job schedulers (HTCondor, Slurm, etc.). This reduces code
duplication and makes it easier to switch between schedulers.

Using the Scheduler in Pipelines
---------------------------------

All Pipeline objects now have a ``scheduler`` property that provides access to the configured
scheduler instance. This can be used for custom job submissions within pipeline methods.

Example
~~~~~~~

.. code-block:: python

    from asimov.pipeline import Pipeline
    from asimov.scheduler import JobDescription
    
    class MyPipeline(Pipeline):
        def submit_custom_job(self):
            """Submit a custom job using the scheduler."""
            
            # The scheduler is automatically available
            job = JobDescription(
                executable="/path/to/script",
                output="output.log",
                error="error.log",
                log="job.log",
                cpus=4,
                memory="8GB"
            )
            
            cluster_id = self.scheduler.submit(job)
            self.logger.info(f"Submitted job with cluster ID: {cluster_id}")
            return cluster_id

DAG Submission
--------------

DAG submission (via ``submit_dag`` methods) now uses the scheduler API. For HTCondor backends,
this wraps the Python bindings (e.g., ``htcondor.Submit.from_dag()``) rather than calling
``condor_submit_dag`` directly. The scheduler property remains available in these methods for
any additional, non-DAG job submissions that may be needed.

Using the Scheduler in CLI Commands
------------------------------------

The monitor loop and other CLI commands can use the scheduler API directly:

.. code-block:: python

    from asimov.scheduler_utils import get_configured_scheduler, create_job_from_dict
    
    # Get the configured scheduler
    scheduler = get_configured_scheduler()
    
    # Submit a job using a dictionary
    job_dict = {
        "executable": "/bin/echo",
        "output": "out.log",
        "error": "err.log",
        "log": "job.log",
        "request_cpus": "1",
        "request_memory": "1GB"
    }
    
    job = create_job_from_dict(job_dict)
    cluster_id = scheduler.submit(job)

The ``asimov monitor start`` and ``asimov monitor stop`` commands now support the
``--use-scheduler-api`` flag to use the new scheduler API directly:

.. code-block:: bash

    # Use the new scheduler API
    asimov monitor start --use-scheduler-api
    
    # Use the legacy interface (default)
    asimov monitor start

Backward Compatibility
----------------------

The existing ``asimov.condor`` module continues to work unchanged. Functions like
``condor.submit_job()`` and ``condor.delete_job()`` now use the scheduler API internally
while maintaining full backward compatibility.

This means existing code continues to work without modification:

.. code-block:: python

    from asimov import condor
    
    # This still works and uses the scheduler internally
    cluster = condor.submit_job(submit_description)
    condor.delete_job(cluster)

Configuration
-------------

You can configure the scheduler in your ``asimov.conf`` file:

.. code-block:: ini

    [scheduler]
    type = htcondor
    
    [condor]
    scheduler = my-schedd.example.com  # Optional: specific schedd

Future Schedulers
-----------------

When Slurm or other schedulers are fully implemented, you'll be able to switch by
simply changing the configuration:

.. code-block:: ini

    [scheduler]
    type = slurm

All code using the scheduler API will automatically use the new scheduler without
requiring any code changes.
