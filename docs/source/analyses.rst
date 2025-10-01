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

Event analyses
  These analyses can access the results of all of the simple analyses which have been 
  performed on a single event, or a subset of them.
  An example of an event analysis is the production of mixed posterior samples from multiple
  PE analyses.
  
Project analyses
  These are the most general type of analysis, and have access to the results of all analyses
  on all events, including event and simple analyses.
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

It's common to have workflows where one process produces a result which then needs to have some additional processing required which may not fit neatly into the notion of an analysis.
For example, in gravitational wave transient analyses it is common to perform parameter estimation in an ``Analysis``, but then want to run a script which will plot the outputs after the analysis is complete.
Indeed, there are tools which are designed to do this for a wide range of pipelines, in order to produce results in a common format.

In asimov these jobs are called "Postprocessing pipelines", and they share much of the same functionality as a full analysis.
Where an analysis is applied to a single event, and provides the settings which are required for a single analysis, in general postprocessing analyses are designed to be applied identically to any Analysis when it completes, if it satisfies the Pipeline's criteria.

As a concrete example, let's look at the blueprint for a postprocessing analysis.

.. code-block:: yaml

		kind: postprocessing
		name: combined summary pages for bilby
		analyses:
		- pipeline:bilby
		stages:
		- name: combined pages
		  pipeline: pesummary

This blueprint describes postprocessing using a pipeline called ``pesummary`` which applies to all events (aka subjects) in the project, and all analyses which have "bilby" as their pipeline.

In contrast to a normal Analysis, it is possible to define multiple stages to a Postprocessing workflow; for example, this blueprint creates a workflow with two stages:

.. code-block:: yaml

		kind: postprocessing
		name: standard pe postprocessing
		analyses:
		- pipeline:bilby
		- pipeline:rift
		stages:
		- name: simple PE summary
		  pipeline: pesummary
		- name: less simple PE summary
		  pipeline: pesummary
		  needs:
		  - simple PE summary

This workflow has two stages, with ``less simple PE summary`` requiring ``simple PE summary`` to complete before it is started.


