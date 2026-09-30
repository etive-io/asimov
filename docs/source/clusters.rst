Interacting with compute clusters
=================================

Asimov is designed to form a layer between you, a data analyst, and the computing cluster which performs your analysis.

An important part of its job is therefore interacting with that cluster, including submitting jobs to it, checking on how they're running, and collecting results once jobs have finished.

Asimov currently supports two scheduling systems: ``htcondor`` and ``slurm``. See
:doc:`scheduler-integration` for the full configuration reference, including how to switch between
them via the ``[scheduler] type`` setting, and how DAGs are translated between the two formats.

``HTCondor``, which we'll sometimes call ``condor`` for short, can be run both on a full-scale computing cluster and on a single machine (their ``minicondor`` distribution is ideal for this) and allows jobs to be queued, and run in the correct order to ensure that required inputs are produced for each stage of an analysis.

Interacting with the scheduler
-------------------------------

Asimov handles all interactions which are required with the configured scheduler.
If you're using the command line interface to Asimov then the ``asimov manage submit`` and ``asimov monitor`` commands will initiate interaction between Asimov and the cluster.

The ``asimov manage submit`` command will submit a job to the cluster, and each pipeline which Asimov supports will provide sufficient logic to set a job up on the cluster based on the configuration files created by running ``asimov manage build``.

The ``asimov monitor`` command will check the status of a job in a cluster, and update the ledger as appropriate, to indicate if a job has completed or become stuck.
In the case of a completed job the pipeline's post-completion hook will be run, allowing post-processing to be started for a finished job.

Caching
-------

In order to improve the performance of Asimov's interactions with clusters, and to reduce the strain placed on the schedulers' databases by default asimov will cache job information for 15 minutes.
This can be adjusted in the main configuration file for asimov.


Configuration settings
----------------------

Configuration options for ``HTCondor`` are stored in the ``htcondor`` namespace of the main configuration file for asimov;
the equivalent options for ``Slurm`` live under ``[slurm]`` — see :doc:`scheduler-integration` for the full set of options
for both schedulers.

``cache_time``
~~~~~~~~~~~~~~~

::

   [htcondor]
   cache_time = 900

The time for which job status information should be cached, in seconds.
The default setting is 900 seconds (15 minutes).
Please take care when reducing this setting, as excessively frequent querying of busy schedulers can result in reduced performance.
