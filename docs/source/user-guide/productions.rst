.. _analysis-guide:

Setting-up analyses
===================

Once we have a project and at least one event we can start to add analyses.
A single analysis with asimov is called a "production".

Asimov interacts with a number of different analysis pipelines in order to produce configuration files, generate DAGs (files used to launch the jobs on compute clusters), submit those jobs to clusters, and then handle any post-processing of the results.

In order to make starting an analysis as easy as possible asimov maps its standard configuration values to all of its supported pipelines.
This means that setting-up equivalent jobs with two different pipelines requires only a couple of commands.

Adding an analysis from a YAML file
-----------------------------------

One of the easiest ways to add an analysis to an event is to use a YAML file which describes its main settings.
Default settings can be added to a project on a pipeline-by-pipeline basis, so that they apply to all analyses using that pipeline.
For example, you might want to set some defaults which are applied to all ``bilby`` jobs which are run by asimov.

These pipeline defaults can be added by a ``configuration`` type YAML file.
For example, to set some sensible defaults for ``bilby`` we could make a file called ``bilby-defaults.yaml``, and then add this YAML data to the file:

.. code-block:: yaml

		kind: configuration
		pipelines:
  		  bilby:
		    sampler:
  		      sampler: dynesty
		    scheduler:
		      accounting group: ligo.dev.o4.cbc.pe.bilby
		      request cpus: 4

These settings will then be used by all of the bilby analyses in the project unless one of the settings is explicitly overwritten by the analysis settings.
We must apply these configurations to the project before they can be used.
This should be done with the ``asimov apply`` command.

.. code-block:: console

		$ asimov apply -f bilby-defaults.yaml

We can also add specific analyses to each event in the project using ``analysis`` type YAML files.
For example, to create a bilby analysis we would make a file called ``bilby-analysis.yaml``, and add this YAML data to the file:

.. code-block:: yaml

		kind: analysis
		name: Prod1
		pipeline: bilby
		approximant: IMRPhenomXPHM
		comment: Bilby parameter estimation job
		needs:
		  - Prod0

This will create an analysis called ``Prod1`` which uses bilby, and depends on another analysis called ``Prod1`` completing before it will be run.
Again we can add this analysis to the project with ``asimov apply`` by running

.. code-block:: console

		$ asimov apply -f bilby-analysis.yaml -e GW150914

Note how we had to specify ``-e GW150914`` so that asimov knew which event to add the analysis to (in this case, an event called ``GW150914``).
We could also add this information directly to the YAML file:

.. code-block:: yaml
		:emphasize-lines: 2

		kind: analysis
		event: GW150914
		name: Prod1
		pipeline: bilby
		approximant: IMRPhenomXPHM
		comment: Bilby parameter estimation job
		needs:
		  - Prod0

It's also possible to add multiple analyses to the same file, should you want to always add the same set of analyses to every event.
This is very useful if you want to add a set of analyses with a set of dependency relationships.
To take the above example, where there is a dependency on ``Prod0``, it might be helpful for your own organisation to keep its specification in the same file.
This can be done by separating the analysis descriptions with three hyphens (``---``).
For example:

.. code-block:: yaml

		kind: analysis
		name: Prod0
		pipeline: bayeswave
		comment: Bayeswave on-source PSD estimation job
		---
		kind: analysis
		name: Prod1
		pipeline: bilby
		approximant: IMRPhenomXPHM
		comment: Bilby parameter estimation job
		needs:
		  - Prod0

Now if we run ``asimov apply`` with this file both ``Prod0`` and ``Prod1`` will be added at the same time.

You can find curated analysis blueprint in the `curated settings repository <https://git.ligo.org/asimov/data/-/tree/main/analyses>`_.
Documentation for these blueprint files can be found in its repository: https://git.ligo.org/asimov/data/

For example, you can add the standard set of GWTC-3 analyses by running

.. code-block:: console

		$ asimov apply -f https://git.ligo.org/asimov/data/-/raw/main/analyses/production-default.yaml
		
Using the command line
----------------------

.. note:: Future changes

	  In future versions of ``asimov`` this command is likely to change signficantly to make it more useful than the current version.

We can also use the command line to add an analysis, but we'll be much more limited as to which settings can be changed for the analysis.
We can do this with the ``asimov production create`` command.
For example, to add a ``bilby`` analysis to an event called ``GW150914`` we can run

.. code-block:: console

		$ asimov production create GW150914 bilby --approximant IMRPhenomPv2

This command will add a ``bilby`` analysis using the ``IMRPhenomXPHM`` approximant to the event ``GW150914``.
		
When creating the production we can also add a comment, which may be useful to help distinguish it from similar analyses when we're looking at many jobs.
We can do that by adding the ``--comment`` option:

.. code-block:: console

		$ asimov production create GW150914 bilby --comment "Higher mode analysis"


.. note:: Naming analyses
		
	  Asimov names analyses automatically when they're created , with the first becoming ``Prod0`` by default, and future jobs being incremented, so ``Prod1``, ``Prod2``, and so on.
	  We can customise the prefix of the name with the ``--family`` option.
	  For example, if you wanted to call your exploratory runs ``Exp0``, ``Exp1``, and so-forth you could do that by using this command:

	  .. code-block:: console

			  $ asimov production create GW150914 bilby --family Exp

Analysis dependencies
---------------------

When we create the analysis we can supply some additional information, including a list of dependencies.
Any analysis can have multiple other analyses as a dependency; asimov will construct a graph by analysing the dependencies for all analyses, and will ensure that they are executed in the correct order.

Suppose you have set up a job which produces PSDs which are required for all subsequent analyses.
This analysis is called ``Prod0``.
Then we can set up  a subsequent analysis with

.. code-block:: console

		$ asimov production create GW150914 bilby --needs Prod0

This production will not be set-up and run until ``Prod0`` has been completed.
		
.. note::

   If you need to add multiple dependencies, just add the ``--needs`` option several times, e.g. ``--needs Prod0 --needs Prod1``.


Analysis status
---------------

Asimov uses its ledger to record the last known state of a production, in the form of a state machine.
Details of the possible states are documented in the :ref:`detailed analysis documentation<states>`.

By default a new production is assigned a ``wait`` state, which prevents asimov from generating the configuration file for the pipeline, or starting the analysis.
This is a useful state to put jobs into until you're happy that all of the settings are correct.

If you want a production to be ready to start as soon as it is created, however, you can pass the ``--status`` option, for example

.. code-block:: console

		$ asimov production create GW150914 lalinference --status ready


Pipeline template
-----------------

In order to start an analysis using one of the pipelines asimov must produce an appropriate configuration file for the pipeline generator.
These are generated using template files, which are specific to each pipeline.
When asimov builds pipelines it substitutes configuration values for each production into these templates.

A default template is included with asimov for each supported pipeline, however there may be situations where these are insufficient and another template is required.

A custom template can be included using the ``--template`` option, for example

.. code-block:: console

		$ asimov production create GW150914 lalinference --template testinggr.ini


You can find more information about configuration templates at the :ref:`templates` page of the documentation.
