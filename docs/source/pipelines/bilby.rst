.. _bilby-pipelines:

Bilby Pipeline
===============

.. note::
   Starting with asimov 0.7, bilby support is provided via the bilby_pipe plugin.
   Install with: ``pip install asimov[gw]`` or ``pip install bilby_pipe[asimov]``

The Bilby pipeline interface allows for bilby-specific metadata and configuration options.

Installation
------------

To use bilby with asimov 0.7+::

    pip install asimov[gw]

Or install bilby_pipe directly::

    pip install bilby_pipe[asimov]

The plugin is automatically discovered through Python entry points once bilby_pipe is installed.

Review Status
-------------

.. note::
   The bilby_pipe plugin integration is fully reviewed and suitable for use with all collaboration analyses.

Migration from asimov <0.7
--------------------------

If upgrading from asimov <0.7:

1. Install bilby_pipe: ``pip install asimov[gw]``
2. No changes needed to ledger files
3. All features work as before

Usage
-----

Once installed, use bilby in your ledger as before:

.. code-block:: yaml

   - Prod0:
       pipeline: bilby
       approximant: IMRPhenomXPHM
       status: ready

Configuration options and examples remain unchanged from previous versions.
See the :ref:`ligo-cookbook-bilby` for detailed examples.

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

The bilby pipeline interface looks for the sections and values listed below in addition to the information which is required for analysing *all* gravitational wave events such as the locations of calibration envelopes and data.

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

Additional Resources
--------------------

For full bilby_pipe documentation, including advanced configuration options and troubleshooting, see the `bilby_pipe documentation <https://lscsoft.docs.ligo.org/bilby_pipe/>`_.
