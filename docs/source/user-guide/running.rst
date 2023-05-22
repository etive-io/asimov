Running analyses
================

Once all of the information has been gathered together in order to prepare an event and an analysis, asimov needs to construct the analysis pipeline, and then run it.
This process is highly automated, and this document will discuss the process for these two steps.

Preparing a pipeline
--------------------

Pipelines are built by asimov from analysis data stored in the ledger.
An analysis in the ledger will be built into an analysis pipeline, along with all of the necessary metadata to submit the job to the job scheduling system.

The ``asimov manage build`` command will search the ledger for all analyses which are ready to start running, and will build the necessary files to produce the pipeline.

For example running in the root directory of an asimov project,

.. code-block:: console

		$ asimov manage build
		
		● Working on GW150914_095045
		   Working on production Prod0
		Prod0 C01_offline checkouts/GW150914_095045
		Production config Prod0 created.

We can see that an analysis called ``Prod0`` has been build, and the configuration file required for the submission step has been created.
Asimov will only build the configuration files for analyses which are ready to be submitted, and will skip analyses which have unmet dependencies.
For example, if a bilby job has a dependency on a bayeswave job to produce its PSDs, asimov will wait until the PSDs are ready before producing the configuration for the bilby pipeline.

Submitting jobs to the scheduler
--------------------------------

Once the configuration files have been build by ``asimov manage build``, asimov is ready to submit the pipeline to the cluster.

This can be done by running the ``asimov manage submit`` command in the root directory of the project.

For example

.. code-block:: console

		$ asimov manage submit

		Prod0 C01_offline checkouts/GW150914_095045
		● Submitted GW150914_095045/Prod0

You can also run the ``build`` and ``submit`` stages in a single command:

.. code-block:: console

		$ asimov manage build submit

Which is identical to running both commands sequentially.
