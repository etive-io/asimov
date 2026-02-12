Bayeswave Analyses
==================

.. important::
   These examples require asimov-bayeswave to be installed::

       pip install asimov[gw]

   Starting with asimov 0.7, BayesWave support is provided via the asimov-bayeswave plugin package.

`Bayeswave <https://docs.ligo.org/lscsoft/bayeswave/>`_ is a tool developed by the LIGO Scientific Collaboration to distinguish gravitational wave signals from background noise.
In many gravitational wave analysis workflows we start by running bayeswave to remove the signal from the data, leaving only the background noise.
This allows us to produce a robust estimate of the amount of noise in the data.

For compact binary parameter estimation we specifically want to use Bayeswave to produce estimates of the "on-source power spectral density" of the noise, or the "PSD".
In many examples of an analysis workflow in asimov you'll spot a Bayeswave job right at the beginning so that this input can be generated.


Getting started
---------------

In order to set-up a Bayeswave job you'll need to set up some defaults which will apply to every Bayeswave analysis in your asimov project, unless you specifically set things differently in one of the analyses.
These defaults set up things like the configuration for the scheduling system on the compute cluster.

You can see example defaults for all pipelines used by LIGO analyses :ref:`here <ligo_defaults>`, but below are the set for Bayeswave:

.. literalinclude:: defaults/bayeswave.yaml
   :name: bayeswave.yaml
   :language: yaml

If you save this file as ``bayeswave.yaml`` you can then apply these defaults to your own project by running

.. code-block:: console

	       asimov apply -f bayeswave.yaml

You should only need to do this once, and if you've already set them through e.g. one of the files containing all the LIGO settings you don't need to worry about this stage.

Bayeswave on-source PSD
-----------------------

The following YAML file will produce a Bayeswave job which will generate an on-source PSD for each interferometer in the analysed event.

.. code-block:: yaml

		kind: analysis
		name: psd-generation
		pipeline: bayeswave
		comment: Bayeswave on-source PSD estimation job

If you save this file as ``psd-generation.yaml`` you can then add this analysis to an event in the project by running

.. code-block:: console

	       asimov apply -f psd-generation.yaml -e <REPLACE WITH EVENT>

where you should replace ``<REPLACE WITH EVENT>`` with the name of the event you want to add it to.
		
The job this creates will be called ``psd-generation``, so you'll need to specify this as a requirement in jobs which need the PSDs it produces as a dependency using the syntax

.. code-block:: yaml

		 needs:
		   - psd-generation

in their YAML file.
