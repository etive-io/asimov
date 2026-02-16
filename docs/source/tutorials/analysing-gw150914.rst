Analysing GW150914 with asimov
===============================

This tutorial will show you how to analyse data from GW150914, the first gravitational wave to be detected, using asimov and some of the analysis pipelines it's designed to work with.

.. note::
   This tutorial was prepared using ``asimov 0.5.8`` and assumes that you already have asimov installed in a conda environment, and have access to a computing environment which runs the ``htcondor`` scheduler.

   We're working to make these analyses work on a wider range of computing infrastructure, but the standard analyses which are performed by gravitational wave researchers are generally very computationally intensive. As new developments come along we'll try to keep asimov and these tutorials up-to-date to make analysis more accessible.

Prerequisites
-------------

In order to use asimov to analyse GW150914 we'll need to ensure that we have the analysis software installed. We'll make use of two "pipelines" in this tutorial: ``bayeswave``, which will estimate the amount of noise present in the gravitational wave strain data, and ``bilby`` which will analyse the signal in the data in order to determine the properties of the astrophysical system which generated in. We'll also need a third pipeline called `asimov-gwdata <https://asimov.docs.ligo.org/pipelines/gwdata/>`_; this doesn't actually perform any analysis, but it allows asimov to add a step into its workflow to fetch various bits of data we'll need.

We can install these pipelines into our conda environment with this command:

.. code-block:: bash

   $ conda install conda-forge::bilby conda-forge::bayeswave conda-forge::asimov-gwdata

From here, setting everything up should be quite straight forward!

Creating an asimov project
--------------------------

The first thing we need to do is to set up an asimov project to run the analysis in.

Make a new directory first, for example

.. code-block:: bash

   $ mkdir gw150914-analysis
   $ cd gw150914-analysis

and then run ``asimov init`` in that directory to initialise the project. You'll also need to give it a name which asimov will use when making reports about the progress of analyses in the project.

.. code-block:: bash

   $ asimov init "GW150914 Analysis Tutorial"

The directory will now be set up as a project, and asimov will make some additional directories for storing data and metadata.

We ship our pipelines with a fairly minimal set of default settings, in order to make it explicit what the analyses are actually doing; however we provide a "blueprint" for asimov which contains the normal settings which are used in most LVK analyses.

Asimov uses blueprint files to work out how to construct analyses, and we can set defaults which are applied right across all analyses in the project, settings which are event-specific, and settings which are analysis-specific all via different kinds of blueprint.

We'll add the project-wide defaults first; these come in two files. One of these specifies defaults for things like resource allocations for pipelines (`you can look at it here <https://git.ligo.org/asimov/data/-/blob/main/defaults/production-pe.yaml?ref_type=heads>`_), while the other contains the default prior probability distributions to be used in parameter estimation, `and you can find it here <https://git.ligo.org/asimov/data/-/blob/main/defaults/production-pe-priors.yaml?ref_type=heads>`_.

We add these to asimov with two commands.

.. code-block:: bash

   $ asimov apply -f https://git.ligo.org/asimov/data/-/raw/main/defaults/production-pe.yaml?
   $ asimov apply -f https://git.ligo.org/asimov/data/-/raw/main/defaults/production-pe-priors.yaml

We've now set everything up to get our analyses started.

Telling asimov about GW150914
-----------------------------

We need to first give asimov information about GW150914. The easiest way to do this is to write a blueprint with all of its details, such as the time when the event was detected. Fortunately a complete set of blueprints for events in GWTC-3 is available, and we can find the one for GW150914 `here <https://git.ligo.org/asimov/data/-/blob/main/events/gwtc-2-1/GW150914_095045.yaml?ref_type=heads>`_.

We can then add this event to asimov by running

.. code-block:: bash

   $ asimov apply -f https://git.ligo.org/asimov/data/-/raw/main/events/gwtc-2-1/GW150914_095045.yaml

We're now ready to add the analyses we'll need.

Setting up a workflow
---------------------

The workflow for a normal gravitational wave analysis involves three steps:

1. Gather data products (we use ``asimov-gwdata`` for this)
2. Estimate the noise PSD (using ``bayeswave``)
3. Perform parameter estimation (using ``bilby``)

We can, again, construct this all using blueprints.

I've written an examples set of blueprints below, which you should save into a file called ``workflow.yaml``.

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

Note that this file contains three blueprints, which are separated with a line containing three hyphens.

These three blueprints contain everything asimov needs to construct the workflow I described earlier. The ``needs`` section in each one allows asimov to understand which steps require other steps to finish before they're started so for example the Bayeswave step requires the ``get-data`` step to complete before it runs.

We can now tell asimov about this workflow by running

.. code-block:: bash

   $ asimov apply -f workflow.yaml -e GW150914_095045

where we've added the ``-e GW150914_095045`` argument so that asimov knows which event to apply the workflow to. (GW150914_095045 is the "full name" of the event, and it's how the blueprint from the previous step names the event.)

Setting things running
----------------------

We're now ready to set things running! There are a couple of steps to this (though as we'll see at the end these can all be automated).

First we need to get asimov to build the first stage of the pipeline. Running

.. code-block:: bash

   $ asimov manage build

will cause asimov to work out which stages of the workflow are ready to run, and produce the appropriate data required to submit these to the scheduler on our computing facility. In this case only the first stage, the ``get-data`` step, can run just now, so asimov will prepare it.

To submit the job to the scheduler we need to run

.. code-block:: bash

   $ asimov manage submit

and then we just need to wait for the scheduler to finish running the job.

We can check on its progress by running

.. code-block:: bash

   $ asimov monitor

You probably don't want to check in on these jobs frequently by hand, so asimov can automate the process of checking the status of an analysis, and automatically build and run new steps in the workflow when all their prerequisites are met. To set this up you just need to run

.. code-block:: bash

   $ asimov start

and then once everything's done you can get asimov to stop monitoring things automatically by running

.. code-block:: bash

   $ asimov stop

And that's it! You can sit back and wait (normally around a day) for your analysis to complete. Asimov will also produce webpages using the PESummary tool to allow you to explore your results. These are stored in the ``pages`` directory of the project by default.
