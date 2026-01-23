The Schedulers module
=====================

This module contains the logic for interacting with schedulers, for example, ``HTCondor`` and ``Slurm``.

The scheduler module provides a unified interface for submitting and managing jobs across different scheduling systems.
Currently supported schedulers include:

* **HTCondor**: The High-Throughput Computing (HTC) workload manager commonly used in scientific computing
* **Slurm**: The Simple Linux Utility for Resource Management, widely used in HPC clusters

Configuration
-------------

Asimov can automatically detect which scheduler is available on your system during project initialization.
You can also manually configure the scheduler type in your ``.asimov/asimov.conf`` file:

For HTCondor::

    [scheduler]
    type = htcondor
    
    [condor]
    user = your_username
    scheduler = optional_schedd_name

For Slurm::

    [scheduler]
    type = slurm
    
    [slurm]
    user = your_username
    partition = optional_partition_name

Using the Scheduler API
------------------------

Pipelines can use the scheduler API through the ``self.scheduler`` property, which provides
a scheduler-agnostic interface for job submission and management.

Example::

    # Submit a DAG file
    cluster_id = self.scheduler.submit_dag(
        dag_file="/path/to/dag.dag",
        batch_name="my-analysis"
    )
    
    # Query job status
    jobs = self.scheduler.query_all_jobs()
    
    # Delete a job
    self.scheduler.delete(cluster_id)

DAG File Translation
--------------------

When using Slurm, HTCondor DAG (Directed Acyclic Graph) files are automatically converted
to equivalent Slurm batch scripts with job dependencies. This allows pipelines that generate
HTCondor DAGs (such as bilby, bayeswave, and lalinference) to work seamlessly with Slurm.

The conversion handles:

* Job dependencies (PARENT-CHILD relationships)
* Job submission files
* Batch names and job metadata

API Reference
-------------

.. automodule:: asimov.scheduler
   :members:
   :undoc-members:
   :show-inheritance: