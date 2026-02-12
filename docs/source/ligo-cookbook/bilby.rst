Bilby Analyses
==============

.. important::
   These examples require bilby_pipe to be installed::

       pip install asimov[gw]

   Starting with asimov 0.7, bilby support is provided via the bilby_pipe plugin package.

This section of the cookbook provides several examples which you can adapt for setting up analyses using the `bilby` pipeline.

Because asimov is configured to always expect that noise estimation is handled by a different pipeline, `bayeswave`, it's probably sensible to have a look at its section in the cookbook first.
For the analyses on this page we've always called the PSD job ``psd-generation`` to be consistent with the recipe in the Bayeswave page, but if you've called it something else you'll need to update it in the dependencies.

Getting started
---------------

In order to set-up a Bilby job you'll need to set up some defaults which will apply to every Bilby analysis in your asimov project, unless you specifically set things differently in one of the analyses.
These defaults set up things like the configuration for the scheduling system on the compute cluster.

You can see example defaults for all pipelines used by LIGO analyses :ref:`here <ligo_defaults>`, but below are the set for Bilby on their own:

.. literalinclude:: defaults/bilby.yaml
   :name: bilby.yaml
   :language: yaml

If you save this file as ``bilby.yaml`` you can then apply these defaults to your own project by running

.. code-block:: console

	       asimov apply -f bilby.yaml

You should only need to do this once, and if you've already set them through e.g. one of the files containing all the LIGO settings you don't need to worry about this stage.


Standard binary black hole analysis
-----------------------------------

The following yaml file will allow you to analyse an event using the normal setup required to analyse a binary black hole signal, and using the IMRPhenomXPHM waveform model.

.. code-block:: yaml

		kind: analysis
		name: Prod1
		pipeline: bilby
		waveform:
  		  approximant: IMRPhenomXPHM
		comment: Bilby BBH parameter estimation job
		needs:
		- psd-generation

Standard binary neutron star analysis
--------------------------------------

The following yaml file will allow you to analyse an event using the most straight-forward setup for analysing a binary neutron star signal.
Note however that this is not the fastest way to perform this sort of analysis, and more efficient methods are covered below under :ref:`ROQ methods<bilby roq>`.

.. code-block:: yaml


		kind: analysis
		pipeline: bilby
		name: bilby-bns
		needs:
		  - psd-generation
		approximant:  IMRPhenomPv2_NRTidalv2
		comment:  IMRPhenomPv2_NRTidalv2 analysis
		likelihood:
		  frequency domain source model: lal_binary_neutron_star
		sampler:
		  sampler: dynesty
		  
You can see that compared to a BBH analysis we need to specify some additional information about the type of likelihood function and waveform generator we want to use.

.. _bilby roq:
ROQ methods
-----------

We can achieve considerable speed improvements by employing reduced order quadrature bases in our analysis, especially when using binary neutron star waveforms.
Some additional care must be taken with these, especially when choosing the prior range, as these are not valid throughout parameter space.

The YAML file below sets up a 256-second long ROQ analysis, which would be suitable for a BNS signal such as GW170817.
However, you should double-check that the prior this sets isn't *wider* than what you desire; if it is you should adjust it accordingly, provided your desired prior is within the boundaries defined below.

Because the datafiles for these runs are stored on the LIGO computing clusters you'll need to update the filepaths to the locations where you've downloaded a copy of the bases to.

.. code-block:: yaml

		kind: analysis
		pipeline: bilby
		name: bilby-roq
		needs:
		  - Bayeswave
		approximant:  IMRPhenomPv2_NRTidalv2
		comment: IMRPhenomPv2_NRTidalv2 256s ROQ job
		likelihood:
		  marginalization:
		    phase: True
		  frequency domain source model: lal_binary_neutron_star_roq
		  calibration:
		    sample: True
		  type: ROQGravitationalWaveTransient
		  roq:
		    folder:  None
		    linear matrix: /home/roq/IMRPhenomPv2_NRTidalv2/bns/basis_256s.hdf5
		    quadratic matrix: /home/roq/IMRPhenomPv2_NRTidalv2/bns/basis_256s.hdf5
		    scale: 1.0
		sampler:
		  sampler: dynesty
		priors:
		  default: BNSPriorDict
		  chirp mass:
		    minimum: 0.92
		    maximum: 1.70
		  spin 1:
		    maximum: 0.4
		  spin 2:
		    maximum: 0.4
