Analysing GW150914 with asimov
===============================

This tutorial shows you how to analyse data from GW150914, the first gravitational wave to be detected, using asimov and some of the analysis pipelines it is designed to work with.

.. rst-class:: tutorial-intro

:What you'll learn: How to go from an empty directory to a running parameter estimation workflow: creating a project, adding an event, describing the analyses to run, and letting asimov submit and monitor them.
:Time required: About 30 minutes to set up, then usually around a day for the analysis itself to run.
:Prerequisites: ``conda``, and access to a computing environment which runs the ``htcondor`` scheduler and whose jobs can download data from the internet.

.. note::
   The standard analyses performed by gravitational-wave researchers are very computationally intensive, so this tutorial needs a cluster. We are working to make them run on a wider range of computing infrastructure, and will keep this tutorial up to date as that happens.

   The commands here are checked against the current ``asimov`` command-line interface every time the documentation is built.

.. note::
   This tutorial uses the public data from the `Gravitational Wave Open Science Center <https://gwosc.org/>`_ (GWOSC).
   The settings were written for the LVK's computing clusters, and include its accounting groups, which you may need to change on other clusters.

.. tip::
   New to asimov? :ref:`Getting started<Getting Started>` introduces its main ideas in about 10 minutes, on your own computer.

.. rst-class:: procedural-step

Install the analysis software
-----------------------------

This tutorial uses four "pipelines".

* ``bayeswave`` estimates the amount of noise present in the gravitational wave strain data.
* ``bilby`` analyses the signal in the data to determine the properties of the astrophysical system which produced it.
* ``PESummary`` then takes the results of the ``bilby`` analyses and performs post-processing to calculate various derived quantities, and also produces web pages which allow the results to be consulted easily.
* `asimov-gwdata <https://asimov.docs.ligo.org/pipelines/gwdata/>`_ doesn't analyse anything itself, but adds a step to the workflow which fetches the data the others need.

Start by creating a new conda environment, and installing asimov and these pipelines into it.
BayesWave comes from conda-forge, and the rest is installed with ``pip``:

.. code-block:: bash

   $ conda create --name gw150914 -c conda-forge python=3.12 bayeswave bayeswaveutils
   $ conda activate gw150914
   $ pip install "asimov>=0.9.0a1" bilby_pipe asimov-bayeswave asimov-pesummary "asimov-gwdata @ git+https://github.com/etive-io/asimov-gwdata"

This tutorial needs asimov 0.9 or newer, which is currently a pre-release, so the version number in that command matters.
``asimov-gwdata`` is installed from GitHub for now, because its latest release, 0.7.1, `fails after downloading public data <https://github.com/etive-io/asimov-gwdata/issues/26>`_.

.. tip::
   ``asimov`` uses git to track your project, so make sure git knows who you are:
   ``git config --global user.name "Your Name"`` and ``git config --global user.email "you@example.com"``.

.. rst-class:: procedural-step

Create a project
----------------

Asimov keeps everything about an analysis in a *project*.
Make a directory for it, and run ``asimov init`` inside it.
You also give the project a name, which asimov uses in the reports it makes about the progress of your analyses.

.. code-block:: bash

   $ mkdir gw150914-analysis
   $ cd gw150914-analysis
   $ asimov init "GW150914 Analysis Tutorial"

The directory is now set up as a project. Asimov creates a few directories of its own:

.. code-block:: text

   gw150914-analysis/
   ├── .asimov/       the project's configuration and its ledger database
   ├── checkouts/     a git repository for each event
   ├── logs/          logs from asimov and from your jobs
   ├── results/       where results are collected
   └── working/       the run directories for each analysis

The *ledger* is the database in which asimov records the project's settings, its events, and every analysis and its status.
You don't edit it by hand: you change it by applying blueprints with ``asimov apply``, as in the next few steps.
Run the rest of the commands in this tutorial from the project's main directory, ``gw150914-analysis``.
If you need the directories to be somewhere else, see the :ref:`project guide<project-guide>`.

.. rst-class:: procedural-step

Add the project-wide defaults
-----------------------------

Pipelines ship with a fairly minimal set of default settings, so that it is clear what an analysis is actually doing. A "blueprint" which contains the settings normally used for LVK analyses is kept in the asimov data repository.

Asimov uses blueprint files to work out how to construct analyses. There are blueprints for settings which apply across the whole project, for settings which belong to one event, and for individual analyses; you will use all three kinds in this tutorial.

The project-wide defaults come in two files. One sets defaults for things like the resources pipelines request, and which data channels to read; the version for public data is on the ``gwosc`` branch of the repository (`production-pe.yaml <https://git.ligo.org/asimov/data/-/blob/gwosc/defaults/production-pe.yaml>`_). The other holds the default prior distributions for parameter estimation (`production-pe-priors.yaml <https://git.ligo.org/asimov/data/-/blob/main/defaults/production-pe-priors.yaml?ref_type=heads>`_). Add both with ``asimov apply``:

.. code-block:: bash

   $ asimov apply -f https://git.ligo.org/asimov/data/-/raw/gwosc/defaults/production-pe.yaml
   $ asimov apply -f https://git.ligo.org/asimov/data/-/raw/main/defaults/production-pe-priors.yaml

These settings apply to everything in the project, so you don't have to repeat them for each analysis, and analyses of many events stay consistent with each other, which matters when you're assembling something like a catalogue.
You can still override any of them for a single event or analysis: for example, to widen the luminosity distance prior for an event which you expect to lie outside the default range.

.. rst-class:: procedural-step

Add GW150914
------------

Next, tell asimov about the event itself. The easiest way is a blueprint which contains its details, such as the time at which it was detected. The asimov data repository has blueprints for the events in the LVK's catalogues, and `the one for GW150914, from GWTC-2.1 and set up for public data, is here <https://git.ligo.org/asimov/data/-/blob/gwosc/events/gwtc-2-1/GW150914_095045.yaml>`_. Apply it:

.. code-block:: bash

   $ asimov apply -f https://git.ligo.org/asimov/data/-/raw/gwosc/events/gwtc-2-1/GW150914_095045.yaml

Check that asimov now knows about it:

.. code-block:: bash

   $ asimov report status

.. code-block:: text

   GW150914_095045

The event is listed with no analyses, because you haven't added any yet.
To set up an event by hand, or fetch its details from somewhere else, see the :ref:`event guide<event-guide>`.

.. rst-class:: procedural-step

Describe the workflow
---------------------

The workflow for a normal gravitational-wave analysis has four stages:

1. Gather the data products, using ``asimov-gwdata``.
2. Estimate the noise power spectral density (PSD), using ``bayeswave``.
3. Perform parameter estimation, using ``bilby``.
4. Summarise the results, using ``PESummary``.

Each stage is an *analysis*, described by a blueprint which names the pipeline to use and any settings particular to that analysis. Save the following into a file called ``workflow.yaml``:

.. code-block:: yaml

   kind: analysis
   name: get-data
   pipeline: gwdata
   file length: 4096
   download:
     - frames
   scheduler:
     accounting group: ligo.dev.o4.cbc.pe.bilby
     request memory: 1024
     request post memory: 16384
     request disk: 2048MB
   ---
   kind: analysis
   name: generate-psd
   pipeline: bayeswave
   comment: Bayeswave on-source PSD estimation process
   needs:
     - get-data
   ---
   kind: analysis
   name: bilby-IMRPhenomXPHM
   pipeline: bilby
   waveform:
     approximant: IMRPhenomXPHM
   comment: PE job using IMRPhenomXPHM and bilby
   needs:
     - generate-psd
   ---
   kind: analysis
   name: summary-pages
   pipeline: pesummary
   comment: Summary pages for the bilby results
   analyses:
     - pipeline: bilby
   refreshable: true

This file holds four blueprints, separated by lines containing three hyphens. The first, ``get-data``, downloads about 1 GB of public strain data from GWOSC. The ``needs`` section tells asimov which stages must finish before an analysis starts: the Bayeswave stage needs ``get-data`` to complete first, and ``bilby`` needs the PSD from ``generate-psd``.

The last blueprint is a :ref:`subject analysis<subject-analysis>`, which works on the results of other analyses of the same event:

* ``analyses`` says which results to use, here those of every ``bilby`` analysis. It waits for them to finish.
* ``refreshable: true`` tells asimov to run it again, updating the pages, if there are new results to include later.

Its other settings, such as the cosmology to assume, come from the project-wide defaults which you added earlier.

Apply the workflow to the event with:

.. code-block:: bash

   $ asimov apply -f workflow.yaml -e GW150914_095045

The ``-e GW150914_095045`` argument tells asimov which event to apply the workflow to. ``GW150914_095045`` is the event's full name, which is how the event blueprint from the previous step names it.

Now look at the project again:

.. code-block:: bash

   $ asimov report status

.. code-block:: text

   GW150914_095045
        Analyses
        - get-data gwdata ready
        - generate-psd bayeswave ready
        - bilby-IMRPhenomXPHM bilby ready
        - summary-pages pesummary ready
        Analyses waiting:
   get-data
   summary-pages

All four analyses are ``ready``, which means that they haven't been run yet.
The list at the end shows those which aren't held back by ``needs``.
Of these, only ``get-data`` can start now: ``summary-pages`` is listed too, but asimov won't submit it until the ``bilby`` analysis has finished.
The :ref:`analysis guide<analysis-guide>` explains more about setting up analyses.

.. rst-class:: procedural-step

Build and submit the first stage
--------------------------------

You are now ready to set things running, which takes two commands. First, ask asimov to *build* the first stage of the workflow:

.. code-block:: bash

   $ asimov manage build

.. code-block:: text

   ● Working on GW150914_095045
        Working on production get-data
   Production config get-data created.
        Working on production summary-pages
   Production config summary-pages created.

For each analysis in that list, asimov writes a configuration file by combining the settings in the ledger with the pipeline's template.
It keeps these files in a git repository for the event, so the one for the first stage is ``checkouts/GW150914_095045/analyses/get-data.ini``.
Open it if you want to see exactly what the pipeline is being asked to do.

Now *submit* the analysis:

.. code-block:: bash

   $ asimov manage submit

.. code-block:: text

   ● Submitted GW150914_095045/get-data
   ● summary-pages is waiting on source analyses to finish

Asimov creates the files which the scheduler needs in the analysis's run directory, ``working/GW150914_095045/get-data``, hands the job to the scheduler, and records the job's ID in the ledger so that it can check on it later.
The other three analyses are not submitted yet, because they are still waiting for earlier stages.

.. tip::
   You can run both steps at once with ``asimov manage build submit``.

.. rst-class:: procedural-step

Monitor your analysis
---------------------

To check on progress once, run

.. code-block:: bash

   $ asimov monitor

.. code-block:: text

   GW150914_095045
        - get-data[gwdata]
          ● get-data is running (condor id: 84047997)

For each analysis which has been submitted, asimov asks the scheduler about its job:

* If the job is still running, asimov says so.
* If the job has finished and produced its results, asimov records that, and starts any post-processing which the pipeline needs.
* If the job has disappeared without producing its results, perhaps because the cluster was shut down for maintenance, asimov tries to rescue it.
* If it can't be rescued, or the scheduler has put it on hold, asimov marks the analysis as ``stuck``, unless you've set a :ref:`retry policy<retry-policy>`.

On its own, ``asimov monitor`` doesn't build or submit the next stage.
You probably don't want to check on these jobs by hand in any case, and asimov can do it for you. Turn this on with

.. code-block:: bash

   $ asimov start

.. code-block:: text

   ● Asimov is running (84048002)

This submits a small job to the scheduler which runs ``asimov monitor --chain`` every 15 minutes.
The ``--chain`` option builds and submits anything which is ready, so ``generate-psd`` starts once ``get-data`` has finished, ``bilby`` once the PSDs are ready, and ``summary-pages`` once ``bilby`` has finished, without any help from you.

Once everything is done, turn the monitoring off again with

.. code-block:: bash

   $ asimov stop

This only stops the routine checks. It doesn't stop any analyses, and you can run ``asimov start`` again later.

You can also write an HTML report of the project, at any time, with ``asimov report html``. See the :ref:`reporting guide<reporting-guide>`.

.. rst-class:: procedural-step

Look at your results
--------------------

Now you can sit back and wait, normally around a day, for the parameter estimation to finish. The ``summary-pages`` analysis then runs, and writes web pages which let you explore the results.
Open this file, in your project directory, in a web browser:

.. code-block:: text

   pages/GW150914_095045/summary-pages/pesummary/home.html

The posterior samples are also collected into a single file, ``samples/posterior_samples.h5``, in the same ``pesummary`` directory.

If an analysis gets stuck
-------------------------

``asimov report status`` shows which analyses are ``stuck``.
To find out why, read the log files in the analysis's run directory, such as ``working/GW150914_095045/get-data``, and asimov's own log in the ``logs`` directory.

Once you've fixed the cause, make the analysis ready to run again, for example:

.. code-block:: bash

   $ asimov analysis rerun GW150914_095045 get-data

Asimov asks you to confirm, and the analysis is submitted again at the next check if ``asimov start`` is running.

Next steps
----------

* Run more events: apply another event's blueprint, then apply ``workflow.yaml`` to it with ``-e``.
* Analyse something which isn't in a catalogue: :doc:`your-own-event`.
* Try different settings: copy the ``bilby`` blueprint into a new file, change it (for example the waveform ``approximant``), give it a new ``name``, and apply it. Asimov won't accept a second analysis with the same name for an event. Once it finishes, ``summary-pages`` is updated to include it.
* Try many variations at once: a blueprint with a ``strategy`` expands into one analysis for each combination of settings. See :ref:`strategies<strategies>`.
* Reuse published results in a new analysis: :doc:`remixing-analyses`.
* Drive the same project from Python: :doc:`python-api-tutorial`.
* Add support for another pipeline: :doc:`adding-a-pipeline`.
