.. _lalinference-pipelines:

LALInference Pipelines
======================

Asimov provides full support for the LALInference pipeline.
While LALInference has been largely superseded by newer sampling techniques it can still be helpful to be able to run jobs using it both for carrying-out cross checks, and for replicating older analyses.

Review status
-------------

.. warning::

   **v0.4.0**
     The integration with LALInference has been deprecated.
     It *must not* be used for collaboration parameter estimation analyses.

Examples
--------

LALInference with Markov Chain Monte Carlo
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   - Prod0:
       pipeline: lalinference
       approximant: IMRPhenomXPHM
       nparallel: 25
       engine: lalinferencemcmc
       status: ready

LALInference with Nested sampling
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
       
.. code-block:: yaml

   - Prod0:
       pipeline: lalinference
       approximant: IMRPhenomXPHM
       nparallel: 25
       engine: lalinferencenest
       status: ready


LALInference interface
----------------------

The LALInference interface can be used to submit jobs to condor clusters which use lalinference as the inference engine.
LALInference jobs must be specified by an appropriately formatted ``ini`` file.

Status messages
~~~~~~~~~~~~~~~

Events run by the LALInference pipeline can have the following status values:

``wait``
   In this state the pipeline will ignore the production

``ready``
   In this state asimov will attempt to submit the job to the condor scheduler

``running``
   Applied after the job is submitted to the cluster

``stuck``
   Applied when the job is held or an error is detected in the pipeline's execution

``finished``
   Applied when normal termination of the pipeline is detected.


Event metadata
~~~~~~~~~~~~~~

In addition to the required event metadata, the LALInferance interface accepts the following event metadata fields:

``rundir``
   The run directory for this event (this will become the parent for unspecified production run directories).

``webdir``
   The web directory for this event (this will become the parent for production web directories).

Production metadata
~~~~~~~~~~~~~~~~~~~

In addition to the required production metadata the LALInference interface accepts the following metadata fields:

``queue``
   The condor queue which the job should be submitted to.
   Defaults to ``Priority_PE`` if not specified.

``rundir``
   The desired run directory for the job.
   DEfaults to ``<event.rundir>/<production.name>`` if event run directory is specified.
   Defaults to ``~/event/production`` if the event run directory specified.

Run data
~~~~~~~~

The following values will be added to the production meta data by asimov as a production is running

``user``
   The accounting user who submitted the event.

``job id``
   The JobID for this event on the condor cluster.

