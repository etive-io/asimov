Working with open data
======================

We designed asimov to make it easier than ever to run your own analyses on LIGO data.

This page will provide a quick overview of how you can set up an analysis similar to the one used in a recent LIGO-Virgo-KAGRA (LVK) publication.

.. note:: We don't guarantee that you'll get *precisely* the same results as those which were published. We're working on including various post-processing steps in the asimov workflow which were used for this publication, but they're not quite ready yet. However, the analysis should work in a similar fashion.

Getting started
---------------

The process which we've outlined here should work on a fairly modern Linux-based computer, or a Windows computer which is running Windows Subsystem for Linux.
We've not tested it yet on MacOS computers.

Getting the analysis environment
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

LIGO analyses require a complicated software stack.
Fortunately it's fairly easy to install this using the ``conda`` tool.

Full instructions on using IGWN environments with conda are `available here<https://computing.docs.ligo.org/conda/usage/>`_, but normally the following steps will work.

First you'll need to install conda if you haven't already got it.

.. code-block:: console

		$ curl -L -O https://github.com/conda-forge/miniforge/releases/latest/download/Mambaforge-$(uname)-$(uname -m).sh
		$ bash Mambaforge-$(uname)-$(uname -m).sh

You'll be asked some questions about the installation as this runs.

Next you need to add ``conda-forge`` as a source of packages.

.. code-block:: console

		$ conda config --add channels conda-forge
		$ conda config --set channel_priority strict

We can now create our own environment, which we'll populate with the IGWN software.

.. code-block:: console

		$ curl -L -O https://computing.docs.ligo.org/conda/environments/linux-64/igwn-py39-testing.yaml
		$ conda env create --file igwn-py39-testing.yaml

We need to *activate* this, which will change things so that we're using versions of software inside this conda environment.

.. code-block:: console

		$ conda activate igwn-py39-testing

To give us access to open data we need to install an extra package as well

.. code-block:: console

		$ conda install -c conda-forge asimov-gwdata
		
But now we should have access to all the software that we need to proceed!


Getting htcondor
~~~~~~~~~~~~~~~~

When the results are prepared for LVK publications we make use of a large network of computing facilities which are coordinated using a tool called `htcondor <https://htcondor.readthedocs.io/en/latest/>`_ which distributes analyses around different computers.
Unless you happen to have a computing cluster which uses this technology available, you'll need to install a mini version of ``htcondor`` which can run on a single machine.
The instructions we outline here are derived from the ``htcondor`` documentation which you can find `here <https://htcondor-vault.readthedocs.io/en/latest/getting-htcondor/install-linux-as-root.html>`_, and assume you can run the ``sudo`` command on your machine to gain Administrator control.
It's still possible to get things going without this, but you'll instead need to follow the instructions `here <https://htcondor-vault.readthedocs.io/en/latest/getting-htcondor/install-linux-as-user.html>`_.

You can install the ``minicondor`` software by running

.. code-block:: console

		$ sudo curl -fsSL https://get.htcondor.org | /bin/bash -s -- --no-dry-run

If everything's worked you can run

.. code-block:: console

		$ condor_status

Which should give you a list of processors available on your machine, which looks something like this:

::

   Name                 OpSys      Arch   State     Activity     LoadAv Mem   Actv

   slot1@azaphrael.org  LINUX      X86_64 Unclaimed Benchmarking  0.000 2011  0+00
   slot2@azaphrael.org  LINUX      X86_64 Unclaimed Idle          0.000 2011  0+00
   slot3@azaphrael.org  LINUX      X86_64 Unclaimed Idle          0.000 2011  0+00
   slot4@azaphrael.org  LINUX      X86_64 Unclaimed Idle          0.000 2011  0+00

   Total Owner Claimed Unclaimed Matched Preempting Backfill  Drain

   X86_64/LINUX    4     0       0        4        0          0        0      0
   Total    4     0       0        4        0          0        0      0

.. note:: If you've previously installed ``minicondor`` might just need to start it by running ``$ sudo condor_master``

Creating a new project
----------------------

The first step we need to take is to create an asimov project.
This is a special directory structure which will keep all of the components of our analysis organised.

First choose somewhere to keep your project, and make a new directory to keep it in, for example

.. code-block:: console

   $ mkdir gwosc-analysis

Then you'll need to change into that directory by running

.. code-block:: console

   $ cd gwosc-analysis

We can then turn this directory into an asimov project by running

.. code-block:: console

		$ asimov init "GWOSC Project"

Where "GWOSC Project" is the name for your project, and can be anything you like.

You'll see that the directory has been populated with various files and directories:

.. code-block:: console

		$ ls

		asimov.log  checkouts  logs  results  working

Right now we don't need to worry about what these are for, but they're described elsewhere in the asimov documentation.


Setting up settings
-------------------

There are lots of settings which need to be established for an analysis to run.
In order to keep things as consistent as possible in major analyses we try to ensure these are the same between all our analyses, and then we only change the settings which absolutely need to be changed on an event-by-event basis.

We'll set things up now using the settings for some recent LVK publications.
Asimov uses YAML files to configure everything, and we *apply* these to the project.
You'll need to copy the following yaml data into a file called, for example, ``configuration.yaml`` which you can save inside the ``gwosc-analysis`` directory.

.. code-block:: yaml

		kind: configuration
		data:
		  channels:
		    H1: H1:GWOSC-16KHZ_R1_STRAIN
		    L1: L1:GWOSC-16KHZ_R1_STRAIN
		    V1: V1:GWOSC-16KHZ_R1_STRAIN
		  frame types:
		    H1: H1_GWOSC_16KHZ_R1
		    L1: L1_GWOSC_16KHZ_R1
		    V1: V1_GWOSC_16KHZ_R1
		likelihood:
		  roll off time: 1.0

		pipelines:
		  bilby:
		    quality:
		      state vector:
			L1: L1:DCS-CALIB_STATE_VECTOR_C01
			H1: H1:DCS-CALIB_STATE_VECTOR_C01
			V1: V1:DQ_ANALYSIS_STATE_VECTOR
		    sampler:
		      sampler: dynesty
		    scheduler:
		      accounting group: ligo.dev.o4.cbc.pe.bilby
		      request cpus: 4
		  bayeswave:
		    quality:
		      state vector:
			L1: L1:DCS-CALIB_STATE_VECTOR_C01
			H1: H1:DCS-CALIB_STATE_VECTOR_C01
			V1: V1:DQ_ANALYSIS_STATE_VECTOR
		    scheduler:
		      accounting group: ligo.dev.o4.cbc.pe.bilby
		      request memory: 1024
		      request post memory: 16384
		    likelihood:
		      iterations: 100000
		      chains: 8
		      threads: 4
		postprocessing:
		  pesummary:
		    accounting group: ligo.dev.o4.cbc.pe.bilby
		    cosmology: Planck15_lal
		    evolve spins: forwards
		    multiprocess: 4
		    redshift: exact
		    regenerate posteriors:
		    - redshift
		    - mass_1_source
		    - mass_2_source
		    - chirp_mass_source
		    - total_mass_source
		    - final_mass_source
		    - final_mass_source_non_evolved
		    - radiated_energy
		    skymap samples: 2000

Once you've saved the file you need to "apply" it to the project by running

.. code-block:: console

		$ asimov apply -f configuration.yaml
		    
We try not to ship "default" settings with asimov where possible, so that it's clearer what's actually being done as the analysis is built.

Adding an event
---------------

It feels like we've spent a lot of time getting things set up, but now we're ready to actually start looking at gravitational waves.

For this guide we'll look at GW150914, which was the first gravitational wave to be detected.

The asimov team maintain a set of YAML files for all of the published events `in a special repository <https://git.ligo.org/asimov/data/-/tree/main/events>`_.
For this event I've copied it onto this page, but you dont need to save this into a file; the command after the YAML file will download it directly from our repository and add it to your project.

.. code-block:: yaml

		data:
		  segment length: 4
		event time: 1126259462.391
		gid: G190047
		interferometers:
		- H1
		- L1
		kind: event
		likelihood:
		  psd length: 4
		  reference frequency: 20
		  sample rate: 2048
		  segment start: 1126259460.391
		  start frequency: 13.333333333333334
		  window length: 4
		name: GW150914_095045
		priors:
		  amplitude order: 1
		  chirp mass:
		    maximum: 41.97447913941358
		    minimum: 21.418182160215295
		  luminosity distance:
		    maximum: 10000
		    minimum: 10
		  mass 1:
		    maximum: 1000
		    minimum: 1
		  mass ratio:
		    maximum: 1.0
		    minimum: 0.05
		quality:
		  minimum frequency:
		    H1: 20
		    L1: 20

To add this event directly from the repository we can just running

.. code-block:: console

		$ asimov apply -f https://git.ligo.org/asimov/data/-/raw/gwosc/events/gwtc-2-1/GW150914_095045.yaml

.. note:: While we normally call this event GW150914, its full name is GW150914_095045, and we'll need to use that later when adding analyses.

Getting data and adding analyses
--------------------------------

We're almost there!
Now we need to fetch the detector data, and add some analyses.
Fortunately this is all automated, and we just need to copy some information into a yaml file and apply it to the project.

We'll create three analysis steps; the first one fetches the frame files, the second one performs some analysis to work out how much noise is in our data, and the third performs the analysis on the signal.
All three steps need to run to complete the analysis.

You'll need to copy the text from this code block into a file, which you can call analyses.yaml:

.. code-block:: yaml

		kind: analysis
		name: get-data
		pipeline: gwdata
		download:
		  - frames
		---
		kind: analysis
		name: psd-generation
		pipeline: bayeswave
		comment: Bayeswave on-source PSD estimation job
		needs:
		    - get-data
		---
		kind: analysis
		name: data-analysis
		pipeline: bilby
		waveform:
		  approximant: IMRPhenomXPHM
		comment: Bilby parameter estimation job
		needs:
		    - psd-generation

We can then apply this to our project, and the correct event.

.. code-block:: console

		$ asimov apply -f analyses.yaml -e GW150914_095045

Now everything is set to get started.

Starting the analyses
---------------------

Asimov now needs to generate the pipeline, and submit the relevant jobs to be processed.
You can make this happen by running

.. code-block:: console

		$ asimov manage build submit

Running these analyses might take quite a long time (potentially several days).
We can get asimov to monitor them for us by running

.. code-block:: console

		$ asimov start

The results
-----------

Eventually the results for the analysis will be generated by asimov and placed in the `results` directory.
You'll be able to explore them using the "summary pages" which will be generated and placed in the `pages` directory of your project.

