Analyses
========

Analyses are the fundamental operations which asimov conducts on data.

Asimov defintes three types of analysis, depending on the inputs of the analysis.

Simple analyses
  These analyses operate only on a single event, and will generally use a 
  very specific set of configuration settings.
  An example of a simple analysis is a bilby or RIFT parameter estimation analysis,
  as these only require access to the data for a single event.
  Before version 0.6 these were called `Productions`.

Subject analyses
  These analyses can access the results of all of the simple analyses which have been
  performed on a single subject (event), or a subset of them.
  An example of a subject analysis is the production of mixed posterior samples from multiple
  PE analyses, implemented as the ``SubjectAnalysis`` class.
  These were previously referred to as "event analyses".

Project analyses
  These are the most general type of analysis, and have access to the results of all analyses
  on all subjects, including subject and simple analyses.
  This type of analysis is useful for defining a population analysis, for example.


An analysis is defined as a series of configuration variables in an asimov project's ledger, which are then used to configure analysis pipelines.

.. _states:
Analysis state
--------------

In order to track each of the jobs asimov monitors it employs a simple state machine on each production.
This state is tracked within :ref:`the production ledger<ledger>` for each production with the value of ``status``.

Under normal running conditions the sequence of these states is

::
   
   ready --> running --> finished --> processing --> uploaded 

A number of additional states are also possible which interupt the normal flow of the job through ``asimov``'s workflow.

+ ``ready`` : This job should be started automatically. This state must be applied manually. The job will then be started once its dependencies are met.
+ ``stopped`` : This run has been manually stopped; stop tracking it. Must be applied manually. 
+ ``stuck`` : A problem has been discovered with this run, and needs manual intervention.
+ ``uploaded`` : This event has been uploaded to the event repository.
+ ``restart`` : This job should be restarted by Olivaw. Must be applied manually.
+ ``finished`` : This job has finished running and the results are ready to be processed on the next bot check.
+ ``processing`` : The results of this job are currently being processed by ``PESummary``.
+ ``uploaded`` : This job has been uploaded to the data store.


.. note::
   The way that analyses are handled by asimov changed considerably in ``asimov 0.6.0``, but generally you shouldn't notice any major differences if you've been using ``Productions`` in the past.

Creating Analyses
=================

The easiest way to create a new analysis is using an YAML Blueprint file.
We settled on using these because analyses often contain a very large number of settings, and trying to set everything up on the command line becomes rapidly impractical, and difficult to reproduce reliably, without writing a shell script.
It is also possible to create simple analyses via the command line, but a blueprint is normally the best way.

A Blueprint for a simple analysis
---------------------------------

A simple analysis is designed to only perform analysis on a single subject or event.
The blueprint for these analyses can be very short if you don't need to specify many settings for the analysis.
For example, ``Bayeswave`` is a gravitational wave analysis pipeline which is designed to perform analysis on a single stretch of data, and a single gravitational wave event.
It doesn't require information about other gravitational wave events to be shared with the analysis, and so is best modelled in asimov as a simple analysis.
A blueprint to set up a default ``Bayeswave`` run is just a handful of lines long.

.. code-block:: yaml

		kind: analysis
		name: sample-analysis
		pipeline: bayeswave
		comment: This is a simple analysis pipeline.

Save this as ``bayeswave-blueprint.yaml``, and you can then add this analysis to an event in a project by running

.. code-block:: console

		$ asimov apply -e <subject name> -f bayeswave-blueprint.yaml

replacing ``<subject name>`` with the name of the subject you're adding the analysis to.
		
It's also possible to make a simple analysis depend on the results of a previous analysis using the ``needs`` keyword in the blueprint.
The pipeline ``giskard`` needs a datafile which is produced by the ``bayeswave`` pipeline defined in the first blueprint, so it can be created with this blueprint:

.. code-block:: yaml

		kind: analysis
		name: stage-2-analysis
		pipeline: giskard
		comment: Search for evidence of gravitational wave bending.
		needs:
		  - sample-analysis

Here we defined the requirement by the *name* of the previous analysis, but we can also use various properties of the analysis.
This can be useful if you don't want to rely on having consistent naming between events or even projects, but you want to be able to reuse a blueprint for many subjects or even many projects.

You can update the previous blueprint to always require a ``Bayeswave`` pipeline to have completed before starting the ``giskard`` analysis:

.. code-block:: yaml

		kind: analysis
		name: stage-2-analysis
		pipeline: giskard
		comment: Search for evidence of gravitational wave bending.
		waveform:
		  approximant: impecableOstritchv56PHMX
		needs:
		  - "pipeline:bayeswave"

We can use any of the metadata for an analysis to create the dependencies.
For example, we can require an analysis which used the ``impecableOstritchv56PHMX`` waveform by stating ``"waveform.approximant:impecableOstritchv56PHMX"`` in the ``needs`` section.
		    
You can also define mutliple criteria for an analyses dependencies, and asimov will wait until all of the requirements are satisfied before starting.
For example:

.. code-block:: yaml

		kind: analysis
		name: stage-3-analysis
		pipeline: calvin
		comment: A third step analysis.
		needs:
		  - "pipeline:giskard"
		  - "waveform.approximant:impecableOstritchv56PHMX"

Optional Dependencies
^^^^^^^^^^^^^^^^^^^^^

By default, all dependencies specified in the ``needs`` list are required.
An entry which matches no analysis in the ledger, for example a misspelt name, contributes no dependency.
Asimov reports it as a warning each time it builds or submits the analysis, and, unless you ask it not to, the analysis is otherwise treated as if it did not depend on that entry.

To make an analysis wait until every required entry matches at least one analysis, set ``strict needs: true``:

.. code-block:: yaml

		kind: analysis
		name: fit-r002
		pipeline: example
		strict needs: true
		needs:
		  - fit-r001

While ``fit-r001`` does not exist, ``fit-r002`` is reported as not ready, and is neither built nor submitted.
A name which matches nothing is reported as "no analysis is named ...", and a property query which matches nothing as "no analysis matches ...", since the second is often just a sign that nothing has been added yet.

Alternatively, you can mark dependencies as optional, which stops them being reported, and allows the analysis to run even if the dependency is missing.
This is useful for creating reusable blueprints that can adapt to different situations.

To mark a dependency as optional, use the dict format with an ``optional: true`` key:

.. code-block:: yaml

		kind: analysis
		name: flexible-analysis
		pipeline: example
		needs:
		  - pipeline: bilby            # Required
		  - optional: true             # Optional
		    pipeline: rift

In this example, the analysis will only run if at least one ``bilby`` analysis is present.
However, if a ``rift`` analysis is also available, it will be included as a dependency.

Needing an analysis in another subject
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

An entry in ``needs`` is looked for among the analyses of the same subject.
To need an analysis in another subject of the same project, write its name as ``subject/name``:

.. code-block:: yaml

		kind: analysis
		name: fit-r002
		pipeline: example
		needs:
		  - central/combine-r001   # in the subject "central"
		  - fit-r001               # in this subject, as always

The analysis waits until ``central/combine-r001`` has finished, in the same way as for an analysis in its own subject, and can use its results.
This works in either direction, so a step in one subject can need a step in another which itself needs a step in the first, as long as there is no cycle.

* An entry which names an analysis as ``subject/name`` and does not resolve, because of a misspelling or because the subject or analysis has not been added yet, always holds the analysis back and is reported as not ready.
  Unlike an entry which is just a name, it is not ignored, because starting a job early for want of a typo is rarely what is meant.
  Mark it ``optional: true`` to ignore it.
* A name which contains ``/`` and is the name of an analysis in the same subject is that analysis, as it always has been.
  Only if there is no such analysis is it read as ``subject/name``.
  Deleting that analysis would therefore change what the entry means.
* Two parts always mean ``subject/name``; a third part is reserved for naming analyses in other projects.
* In ``resolved_dependencies``, which is used to tell whether an analysis is stale, a dependency in the same subject is still its bare name, and one in another subject is ``subject/name``.
* A version of asimov without this feature ignores such an entry, so it would start the analysis without waiting.
  Do not run a ledger which uses it with an older version.

Selecting analyses in other subjects
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

To need, or to combine, every analysis which matches some properties, in some subjects, use a ``subject`` condition.
It can be used on its own or in a group with other conditions, which apply to the analyses of the subjects it selects:

.. code-block:: yaml

		kind: analysis
		name: combine-r002
		pipeline: example
		needs:
		  - - subject: "*"           # any subject
		    - round: 1
		  - - "subject: !noise"      # any subject except "noise"
		    - "status: finished"
		  - subject: central         # every analysis of the subject "central"

* Without a ``subject`` condition, only the analyses of this analysis's own subject are considered, as always.
* ``subject: name`` selects that subject, ``subject: "*"`` every subject, and ``subject: "!name"`` every subject except that one (including this one).
* ``subject`` is a reserved name.
  Before it was, it was looked up in an analysis's metadata like any other property; a property which is nested under ``subject`` (``subject.group``) is still a metadata lookup.
* In a project analysis, ``subject`` only narrows the subjects it was declared with; it never adds one.
* As for ``subject/name``, the analysis waits for the analyses which match to finish, and an entry which matches nothing at all holds it back and is reported, unless it is ``optional``.
  Selecting from every subject reads every subject of the project each time asimov looks at the analysis, so use a named subject where you can.

.. _subject-analysis:

A Blueprint for a subject analysis
-----------------------------------

Subject analyses (also called "event analyses") can access the results of multiple simple analyses on a single event.
A common use case is combining results from different parameter estimation runs into a single summary.

For example, PESummary can be used as a subject analysis to combine results from multiple PE runs:

.. code-block:: yaml

		kind: analysis
		name: CombinedPESummary
		pipeline: pesummary
		analyses:
		  - pipeline: bilby  # Combine all bilby analyses
		refreshable: true    # Auto-update when new analyses finish

The ``analyses`` field is matched in the same way as ``needs``, but is used specifically for subject analyses to specify which analyses to include.
A subject analysis starts when every analysis which matches has finished, so one which has not been added yet does not hold it up, and a new one which appears later makes it stale (and, if it is refreshable, it is run again).
An entry may name an analysis in another subject as ``subject/name``, as in ``needs``.

A subject analysis can have ``needs`` as well.
These are ordinary dependencies, in this subject or another (``subject/name``): the analysis waits until they have finished, but they are not among the analyses which it combines.

.. code-block:: yaml

		kind: analysis
		name: CentralCombine
		pipeline: pesummary
		needs:
		  - central/prep-r001      # must have finished first, but is not combined
		analyses:
		  - pipeline: bilby        # what is combined

.. note::

   An analysis which has ``needs`` but no ``analyses`` is not a subject analysis.
   Older versions read ``needs`` as ``analyses`` when both were given; now ``analyses`` says what is combined and ``needs`` is a dependency.

You can also use optional dependencies in subject analyses:

.. code-block:: yaml

		kind: analysis
		name: FlexiblePESummary
		pipeline: pesummary
		analyses:
		  - pipeline: bilby       # Required
		  - optional: true        # Optional
		    pipeline: rift
		refreshable: true

Refreshable Analyses
^^^^^^^^^^^^^^^^^^^^

Subject analyses can be marked as ``refreshable: true``.
When an analysis is refreshable, asimov will automatically re-run it when:

1. New analyses matching the dependencies complete
2. The list of matching analyses changes

This is particularly useful for PESummary subject analyses, which can automatically regenerate summary pages as new parameter estimation runs complete.

A Blueprint for a project analysis
----------------------------------

Creating a project analysis in asimov is very similar to a simple analysis, except that we can also provide a list of subjects which should be included in the analysis.
For example, the ``gladia`` pipeline is used to perform a joint analysis between two gravitational waves.

To create a ``gladia`` pipeline which analyses two events, ``GW150914`` and ``GW151012`` you need to add a ``subjects`` list to the blueprint, for example:

.. code-block:: yaml

		kind: projectanalysis
		name: gladia-joint
		pipeline: gladia
		comment: An example joint analysis.
		subjects:
		  - GW150914
		  - GW151012
		    

Creating a Project Analysis Pipeline
====================================

For the most part a Project Analysis pipeline is similar to a simple analysis pipeline.
The main difference will be how you access metadata from each event.

In the template configuration file project analyses have access to the ``analysis.subjects`` property, which provides a list of subjects available to the analysis.
These then give access to all of the metadata for each subject.

The example below uses two subjects, and to make the sample template easier to read we've assigned each to its own liquid variable.

.. code-block:: liquid

		{%- assign subject_1 = analysis.subjects[0] -%}
		{%- assign subject_2 = analysis.subjects[1] -%}

		[event_1_settings]
		{%- assign ifos = subject_1.meta['interferometers'] -%}
		channel-dict = { {% for ifo in ifos %}{{ subject_1.meta['data']['channels'][ifo] }},{% endfor %} } 
		psd-dict = { {% for ifo in ifos %}{{ifo}}:{{subject_1.psds[ifo]}},{% endfor %} }

		[event_2_settings]
		{%- assign ifos = subject_2.meta['interferometers'] -%}
		channel-dict = { {% for ifo in ifos %}{{ subject_2.meta['data']['channels'][ifo] }},{% endfor %} } 
		psd-dict = { {% for ifo in ifos %}{{ifo}}:{{subject_2.psds[ifo]}},{% endfor %} }


Postprocessing Workflows
========================

It's common to have workflows where one process produces a result which then needs some additional processing which may not fit neatly into the notion of a single analysis.
For example, in gravitational wave transient analyses it is common to perform parameter estimation in an ``Analysis``, but then want to run a tool which combines and summarises the outputs once the analysis is complete.

.. note::
   Earlier versions of asimov had a dedicated ``kind: postprocessing`` blueprint type with its own ``stages`` syntax for this.
   That mechanism has been removed; a document with ``kind: postprocessing`` is no longer processed and will not run anything.
   Postprocessing is now expressed as an ordinary :ref:`subject analysis <subject-analysis>` (see above), using the ``analyses``/``needs`` dependency spec and, where the workflow should keep itself up to date, ``refreshable: true``.

As a concrete example, PESummary can be run as postprocessing for a set of ``bilby`` analyses:

.. code-block:: yaml

		kind: analysis
		name: combined summary pages for bilby
		pipeline: pesummary
		analyses:
		  - pipeline: bilby
		refreshable: true

This blueprint runs ``pesummary`` once all matching ``bilby`` analyses on the subject are available, and re-runs automatically as further matching analyses complete because of ``refreshable: true``.

Multi-stage postprocessing (a summary step which itself depends on another postprocessing step) is expressed by chaining analyses with ``needs``, exactly as for any other analysis dependency:

.. code-block:: yaml

		kind: analysis
		name: simple PE summary
		pipeline: pesummary
		analyses:
		  - pipeline: bilby
		  - pipeline: rift
		refreshable: true
		---
		kind: analysis
		name: less simple PE summary
		pipeline: pesummary
		needs:
		  - simple PE summary
		refreshable: true

Here ``less simple PE summary`` requires ``simple PE summary`` to complete before it is started.


