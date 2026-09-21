.. _bilby-pipelines:

Bilby pipelines
===============

The Bilby interface allows for some bilby-specific metadata.

Current status
--------------

.. warning::

   The bilby pipeline implementation was removed from asimov core in the 0.7 release
   (``asimov/pipelines/bilby.py`` was deleted), and no public plugin package currently replaces it.
   ``pipeline: bilby`` will not resolve to a working pipeline in current versions of asimov.

   The rest of this page is kept as a reference for the ledger options bilby analyses used, in case
   support is reinstated as a plugin; it does not describe a currently-working integration.

Examples
--------

Bilby with IMRPhenomXPHM
~~~~~~~~~~~~~~~~~~~~~~~~

This was the default analysis setup for the O3 catalog runs which were used in the GWTC-2.1 and GWTC-3 catalog papers.

.. code-block:: yaml

   - Prod0:
       pipeline: bilby
       approximant: IMRPhenomXPHM
       status: ready

   
Ledger Options
--------------

The bilby pipeline interface looks for the the sections and values listed below in addition to the information which is required for analysing *all* gravitational wave events such as the locations of calibration envelopes and data.

``likelihood``
~~~~~~~~~~~~~~

These settings affect the behaviour of the bilby likelihood module.

``marginalization``
	This section takes a list of types of marginalization to apply to the analysis (see below for an example of the syntax).
	
	``distance``
		Activates distance marginalization.
	``phase``
		Activates phase marginalization.
	``time``
		Activates time marginalization
		
``roq``
	This section allows ROQs to be defined for the likelihood function.

	``folder``
		The location of the ROQs.
		Defaults to None.
	``scale factor``
		The scale factor of the ROQs.
		Defaults to 1.
		
``kwargs``
	Additional keyword arguments to pass to the likelihood function in the form of a YAML or JSON format dictionary.
	Defaults to None.

``sampling``
~~~~~~~~~~~~~

The sampling section of the ledger can be used to specify both the bilby sampler which should be used, and the settings for that sampler.

``sampler``
	The name of the sampler which should be used. 
	Defaults to `dynesty`.
	A full list of supported values can be found in the `bilby` documentation, but include `dynesty`, `emcee`, and `nessai`.
	
``seed``
	The random seed to be used for sampling.
	Defaults to `None`.
	
``parallel jobs``
	The number of parallel jobs to be used for sampling.
	Defaults to `4`.

``sampler kwargs``
	Sampler-specific keyword arguments.
	These should be provided as a dictionary in either YAML or JSON dictionary (assosciative array) format.
	Defaults to `"{'nlive': 2000, 'sample': 'rwalk', 'walks': 100, 'nact': 50, 'check_point_delta_t':1800, 'check_point_plot':True}"`

