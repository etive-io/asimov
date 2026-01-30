Scheduler Integration Guide
============================

This guide explains how to use the scheduler abstraction in asimov pipelines and other components.

Overview
--------

Asimov includes a scheduler abstraction layer that provides a uniform interface for
interacting with different job schedulers. Currently supported schedulers:

* **HTCondor**: The High-Throughput Computing (HTC) workload manager
* **Slurm**: The Simple Linux Utility for Resource Management

This abstraction reduces code duplication and makes it easy to switch between schedulers.

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
``condor_submit_dag`` directly.

For Slurm backends, HTCondor DAG files are automatically converted to Slurm batch scripts
with proper job dependencies. This allows pipelines that generate HTCondor DAGs (such as
bilby, bayeswave, and lalinference) to work seamlessly with Slurm.

Using the Scheduler in CLI Commands
------------------------------------

The monitor loop and other CLI commands use the scheduler API:

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

Monitor Daemon
~~~~~~~~~~~~~~

The monitor daemon behavior differs based on the scheduler:

**HTCondor**: Uses HTCondor's cron functionality to run periodic jobs

.. code-block:: bash

    asimov start  # Submits a recurring job via HTCondor
    asimov stop   # Removes the HTCondor job

**Slurm**: Uses system cron to schedule periodic monitor runs

.. code-block:: bash

    asimov start  # Creates a cron job (requires python-crontab)
    asimov stop   # Removes the cron job

For Slurm support, install the optional dependency:

.. code-block:: bash

    pip install asimov[slurm]

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

Asimov automatically detects which scheduler is available during ``asimov init``.
You can manually configure the scheduler in your ``asimov.conf`` file:

**HTCondor Configuration**

.. code-block:: ini

    [scheduler]
    type = htcondor
    
    [condor]
    user = your_username
    scheduler = my-schedd.example.com  # Optional: specific schedd

**Slurm Configuration**

.. code-block:: ini

    [scheduler]
    type = slurm
    
    [slurm]
    user = your_username
    partition = compute  # Optional: specific partition
    cron_minute = */15   # Optional: monitor frequency (default: every 15 minutes)

Switching Schedulers
--------------------

To switch between schedulers, simply update the ``[scheduler]`` section in your
``asimov.conf`` file and restart your workflows. All code using the scheduler API
will automatically use the new scheduler without requiring any code changes.

Example: Switching from HTCondor to Slurm

.. code-block:: ini

    # Before
    [scheduler]
    type = htcondor
    
    # After
    [scheduler]
    type = slurm
