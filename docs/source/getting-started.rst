Getting started with asimov
===========================

Quick Start
-----------

You can get started with an analysis-ready gravitational wave project in just a few quick steps.
You'll need to have asimov installed first; you can find information about doing this in the :ref:`installation-guide`.

1. **Create a new asimov project**
   Asimov projects are used to keep all of the data required to construct analyses, and all of the results they produce, together in one organised place.
   Any directory can be turned into an asimov project, but it's always best to start in a new, empty directory for simplicity.

   .. code-block:: console

		   $ mkdir new-project
		   $ cd new-project 
		   $ asimov init "my first project"

		   ● New project created successfully!

   You'll see that asimov creates some new directories and data files in this directory, which are used for storing results, ongoing analyses, and analysis configurations.
		   
2. **Download analysis defaults**
   When the project is created asimov doesn't know anything about how to construct a gravitational wave analysis, but we can fetch a sensible set of defaults which have been used in previous analyses.

   Asimov has a single command called ``asimov apply`` which can be used to fetch settings files and add them to the "ledger".
   The ledger is the database which asimov maintains for a project to keep track of settings and the status of all the analyses it knows about.

   First let's fetch the default settings for the analysis pipelines.
   We'll use the settings which are curated for "production" parameter estimation by the LIGO Compact Binaries group.

   .. code-block:: console
   
		   $ asimov apply -f https://git.ligo.org/asimov/data/-/raw/main/defaults/production-pe.yaml

		   ● Successfully applied a configuration update
		   
   The analyses which we'll use in this quick start guide are all Bayesian analyses, or analyses which are built on Bayesian principles.
   This means that we also need to have a set of default priors which can be applied to all events.
   Again we can download a set of these which are curated for production analyses.

   .. code-block:: console

		   $ asimov apply -f https://git.ligo.org/asimov/data/-/raw/main/defaults/production-pe-priors.yaml

		   ● Successfully applied a configuration update

   We can always over-write the default priors with values which are specific to an individual event or even an individual analysis, but these project-wide defaults
   are useful so that we don't need to re-specify quantities which will be the same in most or even all of the analyses (for example, we might normally want the luminosity distance prior to be the same for all analyses except in a small number of cases where we expect an event to lie outwith those default ranges).
   These project-wide defaults also help to maintain consistency across a large number of analyses, which can be helpful when assembling something like a catalogue publication.

3. **Adding an event**
   Events are the primary subjects for analysis in asimov.
   A good example of an event is a compact binary coalescence signal, such as GW150914, which was the first gravitational wave to be detected, in 2015.
   For the purposes of this guide we'll use the same set of priors and additional information which were used to analyse this event in the GWTC-2.1 gravitational wave catalogue, however you can also set the entire event up manually by following the instructions in the :ref:`event guide<event-guide>`.

   We can download the curated GWTC-2.1 settings by running

   .. code-block:: console

		   $ asimov apply -f https://git.ligo.org/asimov/data/-/raw/main/events/gwtc-2-1/GW150914_095045.yaml

		   ● Successfully applied GW150914_095045

   This will add ``GW150914_095045`` to the project's ledger.
   You can see that it's in the ledger by running

   .. code-block:: console

		   $ asimov report status

		   GW150914_095045

   In the next step we'll add some analyses to the event, but initially there are none, as reported here.

4. **Adding some analyses**
   Now that we've told asimov about the event we want to analyse, we need to tell it *how* to analyse it.
   The specification for an individual, self-contained analysis will specify the pipeline which should be used for the analysis, and any other settings which are specific to this analysis.
   For this guide we'll set up two analyses which were used in the production of the GWTC-2.1 catalogue paper, but not change any of the settings beyond this.
   The two pipelines we'll use are ``bayeswave``, to produce the on-source PSD estimates, and ``bilby`` to perform the parameter estimation.

   The ``bilby`` job requires an analysis product from the ``bayeswave`` job (namely, the PSDs), and so asimov won't allow it to start until after the ``bayeswave`` job has completed.

   We can add these analyses by downloading the curated settings.

   .. code-block:: console

		   $ asimov apply -f https://git.ligo.org/asimov/data/-/raw/main/analyses/production-default.yaml -e GW150914_095045

		   ● Successfully applied Prod0 to GW150914_095045
		   ● Successfully applied Prod1 to GW150914_095045
		   
   Again, it is also possible to set up an analysis from scratch, or to alter the settings for a given analysis before it's started.
   Details on how you can do this can be found in the :ref:`analysis guide<analysis-guide>`.

   If we now look at the project again we can see that two new analyses are listed for GW150914:

   .. code-block:: console

		   $ asimov report status

		   GW150914_095045
		   Analyses
		   - Prod0 bayeswave ready
		   - Prod1 bilby ready
		   Analyses waiting:
		   Prod0

   Notice how the ``bilby`` analysis is listed as "waiting", as it requires the ``bayeswave`` job to complete before it can be allowed to run.
		    
5. **Building the pipeline and submitting to the cluster**
   The final steps in getting your analysis are, you'll probably be pleased to learn, almost entirely automatic.
   There are two steps which ``asimov`` needs to complete to do this (though as we'll see later they can be combined into a single step).

   First is the ``build`` step, which creates the configuration file for the pipeline, and then creates the files necessary for submitting the analyses onto a computing cluster.

   .. code-block:: console

		   $ asimov manage build
		   
		   ● Working on GW150914_095045
		      Working on production Prod0
		   Production config Prod0 created.

   If the pipeline which you're building uses a configuration file to describe its settings, this step will produce that configuration file, and will save it in the event repository.
   You can find the event (git) repositories in the ``checkouts`` directory of the current project, but their location can be changed.
   Details on doing that are in the :ref:`projects guide<project-guide>`.
   Configuration files are produced by taking the settings stored in asimov's project ledger, and combining them with a template configuration file for the pipeline.
   This step also creates all of the files which are required to submit the analysis to an ``htcondor``-based computing scheduler.
   You can find these files inside the ``working`` directory of the current project.
   The exact files produced will vary depending on the pipeline which you're creating.
   
   The final step to get everything running is the ``submit`` step, which communicates with the scheduling system and submits the pipeline to it.
   You can run this with the ``asimov manage submit`` command.
   
   .. code-block:: console

		   $ asimov manage submit 

		   ● Submitted GW150914_095045/Prod0

   Once the job has been submitted asimov will record the ID number for the job, and record it in the project ledger so that it can check on its status.

6. **Monitoring your analyses**
   Once the job is running you'll want to check on it to see if it's finished (or if something's gone wrong).
   The simplest way to do this is with the ``asimov monitor`` command.
   You'll need to run this in the main project directory, and not in one of its subdirectories.

   .. code-block:: console

		   $ asimov monitor

		   GW150914_095045
		   - Prod0[bayeswave]
		     ● Prod0 is running (condor id: 84047997)
		   - Prod1[bilby]
		     ● ready

   When you run this, asimov will do a few different things.
   First, it checks with the compute scheduler if the job is still running.
   If it is, then it will report that to you, and continue checking any other analyses it knows about.
   Otherwise it will try and work out why it's no longer running.
   If it's because the job has finished it will find the results files, and start running any post-processing which the pipeline requires.
   If something's gone wrong, asimov will first try to rescue the analysis (this can be helpful if the cluster was shut down for maintenance, for example, and the job got lost).
   If it can't rescue the analysis, asimov will mark the job as "stuck", and will tell you that it can no longer complete the analysis without further intervention.

   It can be useful to automate this process so that it runs regularly.
   The ``asimov start`` command can be used to set up a process which will keep running ``asimov monitor`` and a few other commands every 15 minutes.

   .. code-block:: console

		   $ asimov start

		   ● Asimov is running (84048002)

   In addition to monitoring jobs, this will also automatically build and submit any jobs which are ready to start.
   For example, in this project we have a bilby job which is waiting for the completion of a bayeswave job in order to start.
   ``asimov start`` will automatically build and submit this bilby analysis once the bayeswave job is complete.

   Eventually, once all of the analyses have completed you can run ``asimov stop`` to end the automatic monitoring.
   ``asimov stop`` does not stop analyses from running, and only stops their routine monitoring via asimov, so can always be safely restarted by running ``asimov start`` later.

And that's it! We now have a working analysis on GW150914.
chances are if you're looking at asimov you'll want to do something a little more complicated, so let's look at some next steps.
   
What's next?
------------

+ **Adding more events**
  If you want to add new events, or download event information from GraceDB you should read the :ref:`event guide<event-guide>`.

+ **Adding more analyses**
  You can also add additional analyses, and change the settings used; you can find more information in the :ref:`analysis guide<analysis-guide>`.

+ **Creating overview pages**
  Chances are you don't want to spend all of your time checking the status of jobs on the terminal.
  Asimov can produce clear and tidy web page reports showing the status of all of the analyses it's running which are regularly updated.
  You can find more information about setting this up in the :ref:`reporting guide<reporting-guide>`.

+ **Advanced project configuration**
  For most analyses the default project setup should be sufficient, but if you need to run an extremely large set of analyses, and are sharing the job with lots of other people, it might be convenient to be able to change things.
  You can find more details about doing that in the :ref:`project guide<project-guide>`.
