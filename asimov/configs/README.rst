Default configuration templates
===============================

This directory contains the default configuration templates for the various pipelines.

The templates are written using the liquidpy templating language.

Scheduler Configuration
-----------------------

Asimov now supports multiple scheduler backends (HTCondor, Slurm, etc.) through the 
``asimov.scheduler`` module. You can configure the scheduler in your ``asimov.conf`` file:

HTCondor Configuration
~~~~~~~~~~~~~~~~~~~~~~

To use HTCondor (the default scheduler)::

    [scheduler]
    type = htcondor
    
You can also specify a specific schedd::

    [condor]
    scheduler = my-schedd.example.com
    
Slurm Configuration (Future)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Support for Slurm is planned for future releases::

    [scheduler]
    type = slurm

Using the Scheduler API
~~~~~~~~~~~~~~~~~~~~~~~

You can also use the scheduler API directly in your code::

    from asimov.scheduler import get_scheduler, JobDescription
    
    # Get a scheduler instance
    scheduler = get_scheduler("htcondor")
    
    # Create a job description
    job = JobDescription(
        executable="/path/to/executable",
        output="stdout.log",
        error="stderr.log",
        log="job.log",
        cpus=4,
        memory="8GB"
    )
    
    # Submit the job
    cluster_id = scheduler.submit(job)
    
    # Query job status
    status = scheduler.query(cluster_id)
    
    # Delete the job
    scheduler.delete(cluster_id)
