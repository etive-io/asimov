Bayeswave Analyses
==================

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

Suppressing frequency bands in the PSD
---------------------------------------

Sometimes a specific frequency band needs to be excluded from the PSD before it is used by downstream analyses — for example to remove power from a known spectral line.
This is done with the ``supress`` key under ``quality``.

Single notch
~~~~~~~~~~~~

To suppress a single band in one or more interferometers, provide a mapping with ``lower`` and ``upper`` frequency limits (in Hz):

.. code-block:: yaml

        kind: analysis
        name: psd-generation
        pipeline: bayeswave
        comment: Bayeswave on-source PSD estimation job
        quality:
          supress:
            H1:
              lower: 59.0
              upper: 61.0
            L1:
              lower: 59.0
              upper: 61.0

Multiple notches
~~~~~~~~~~~~~~~~

To suppress more than one band per interferometer, provide a list of ``lower``/``upper`` pairs:

.. code-block:: yaml

        kind: analysis
        name: psd-generation
        pipeline: bayeswave
        comment: Bayeswave on-source PSD estimation job
        quality:
          supress:
            H1:
              - lower: 59.0
                upper: 61.0
              - lower: 119.0
                upper: 121.0
            L1:
              - lower: 59.0
                upper: 61.0
              - lower: 119.0
                upper: 121.0

All notches for a given interferometer are applied in a single pass before the PSD is committed to the repository, so multi-notch jobs produce the same number of git commits as single-notch ones.
The single-mapping form (without a list) is still accepted for backwards compatibility.
