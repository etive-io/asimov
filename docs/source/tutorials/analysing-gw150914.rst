Analysing GW150914 with asimov
===============================

This tutorial shows you how to analyse data from GW150914, the first gravitational wave to be detected, using asimov and some of the analysis pipelines it is designed to work with.

.. rst-class:: tutorial-intro

:What you'll learn: How to go from an empty directory to a running parameter estimation workflow: creating a project, adding an event, describing the analyses to run, and letting asimov submit and monitor them.
:Time required: About 30 minutes to set up, then usually around a day for the analysis itself to run.
:Prerequisites: A conda environment with asimov installed (see :doc:`../installation`), and access to a computing environment which runs the ``htcondor`` scheduler.

.. note::
   The standard analyses performed by gravitational-wave researchers are very computationally intensive, so this tutorial needs a cluster. We are working to make them run on a wider range of computing infrastructure, and will keep this tutorial up to date as that happens.

   The commands here are checked against the current ``asimov`` command-line interface every time the documentation is built.

.. rst-class:: procedural-step

Install the analysis software
-----------------------------

This tutorial uses three "pipelines". ``bayeswave`` estimates the amount of noise present in the gravitational wave strain data, and ``bilby`` analyses the signal in the data to determine the properties of the astrophysical system which produced it. A third, `asimov-gwdata <https://asimov.docs.ligo.org/pipelines/gwdata/>`_, doesn't analyse anything itself, but adds a step to the workflow which fetches the data the other two need.

Install them into the conda environment where asimov is installed:

.. code-block:: bash

   $ conda install conda-forge::bilby conda-forge::bayeswave conda-forge::asimov-gwdata

.. tip::
   ``asimov`` uses git to track your project, so make sure git knows who you are:
   ``git config --global user.name "Your Name"`` and ``git config --global user.email "you@example.com"``.

.. rst-class:: procedural-step

Create a project
----------------

Asimov keeps everything about an analysis in a *project*. Make a directory for it, and run ``asimov init`` inside it. You also give the project a name, which asimov uses in the reports it makes about the progress of your analyses.

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

.. rst-class:: procedural-step

Add the project-wide defaults
-----------------------------

Pipelines ship with a fairly minimal set of default settings, so that it is clear what an analysis is actually doing. A "blueprint" which contains the settings normally used for LVK analyses is kept in the asimov data repository.

Asimov uses blueprint files to work out how to construct analyses. There are blueprints for settings which apply across the whole project, for settings which belong to one event, and for individual analyses; you will use all three kinds in this tutorial.

The project-wide defaults come in two files. One sets defaults for things like the resources pipelines request (`production-pe.yaml <https://git.ligo.org/asimov/data/-/blob/main/defaults/production-pe.yaml?ref_type=heads>`_), and the other holds the default prior distributions for parameter estimation (`production-pe-priors.yaml <https://git.ligo.org/asimov/data/-/blob/main/defaults/production-pe-priors.yaml?ref_type=heads>`_). Add both with ``asimov apply``:

.. code-block:: bash

   $ asimov apply -f https://git.ligo.org/asimov/data/-/raw/main/defaults/production-pe.yaml
   $ asimov apply -f https://git.ligo.org/asimov/data/-/raw/main/defaults/production-pe-priors.yaml

.. rst-class:: procedural-step

Add GW150914
------------

Next, tell asimov about the event itself. The easiest way is a blueprint which contains its details, such as the time at which it was detected. A complete set of blueprints for the events in GWTC-3 is available, and `the one for GW150914 is here <https://git.ligo.org/asimov/data/-/blob/main/events/gwtc-2-1/GW150914_095045.yaml?ref_type=heads>`_. Apply it:

.. code-block:: bash

   $ asimov apply -f https://git.ligo.org/asimov/data/-/raw/main/events/gwtc-2-1/GW150914_095045.yaml

.. rst-class:: procedural-step

Describe the workflow
---------------------

The workflow for a normal gravitational-wave analysis has three stages:

1. Gather the data products, using ``asimov-gwdata``.
2. Estimate the noise power spectral density (PSD), using ``bayeswave``.
3. Perform parameter estimation, using ``bilby``.

Each stage is described by a blueprint. Save the following into a file called ``workflow.yaml``:

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
   ---
   kind: analysis
   name: generate-psd
   pipeline: bayeswave
   comment: Bayeswave on-source PSD estimation process
   needs:
     - get-data
   ---
   kind: analysis
   name: bilby-IMRPhenomXPHM-cosmo
   pipeline: bilby
   waveform:
     approximant: IMRPhenomXPHM
   comment: PE job using IMRPhenomXPHM and bilby
   needs:
     - generate-psd

This file holds three blueprints, separated by a line containing three hyphens. The ``needs`` section of each one tells asimov which stages must finish before it starts: the Bayeswave stage needs ``get-data`` to complete first, and ``bilby`` needs the PSD from ``generate-psd``.

Apply the workflow to the event with:

.. code-block:: bash

   $ asimov apply -f workflow.yaml -e GW150914_095045

The ``-e GW150914_095045`` argument tells asimov which event to apply the workflow to. ``GW150914_095045`` is the event's full name, which is how the event blueprint from the previous step names it.

.. tip::
   To see where the project stands at any point, run ``asimov report status``. It lists the event's analyses and what each one is waiting for.

.. rst-class:: procedural-step

Build and submit the first stage
--------------------------------

You are now ready to set things running. First, ask asimov to build the first stage of the workflow:

.. code-block:: bash

   $ asimov manage build

Asimov works out which stages are ready to run, and produces the files needed to submit them to the scheduler. Only ``get-data`` has no unmet dependencies, so that is the stage it prepares. Now submit it:

.. code-block:: bash

   $ asimov manage submit

The scheduler will run the job. ``generate-psd`` and the ``bilby`` analysis are not submitted yet, because they are still waiting for the stages they need.

.. rst-class:: procedural-step

Monitor your analysis
---------------------

To check on progress once, run

.. code-block:: bash

   $ asimov monitor

You probably don't want to check on these jobs by hand. Asimov can do it for you: it will check the status of every analysis, and build and submit each new stage as soon as the ones it needs have finished. Turn this on with

.. code-block:: bash

   $ asimov start

and, once everything is done, turn it off again with

.. code-block:: bash

   $ asimov stop

You can also write an HTML report of the project, at any time, with ``asimov report html``. See :doc:`../user-guide/reporting`.

.. rst-class:: procedural-step

Look at your results
--------------------

Now you can sit back and wait, normally around a day, for the analysis to finish. When it does, asimov produces web pages using the PESummary tool, which let you explore the results. By default they are stored in the ``pages`` directory of the project.

Next steps
----------

* Run more events: apply another event's blueprint, then apply ``workflow.yaml`` to it with ``-e``.
* Change the analysis: edit ``workflow.yaml``, for example the waveform ``approximant``, and apply it again.
* Reuse published results in a new analysis: :doc:`remixing-analyses`.
* Drive the same project from Python: :doc:`python-api-tutorial`.
* Add support for another pipeline: :doc:`adding-a-pipeline`.
