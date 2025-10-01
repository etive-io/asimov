.. _rift-pipelines:

RIFT pipelines
==============

The RIFT interface allows the creation and control of RIFT analyses.
A number of metadata are required to configure RIFT which are not required for other pipelines.

Review Status
-------------

.. warning::
   
   **v0.4.0**
     The current integration with RIFT is experimental, and is not reviewed.
     It *must not* be used for collaboration parameter estimation analyses.
     A reviewed version is expected to be available in the v0.5 series of releases.


Examples
--------

RIFT with SEOBNRv4PHM
~~~~~~~~~~~~~~~~~~~~~

This was the default analysis setup for the O3 catalog runs which were used in the GWTC-2.1 and GWTC-3 catalog papers.

.. code-block:: yaml

   - Prod0:
       pipeline: rift
       approximant: SEOBNRv4PHM
       status: ready

RIFT with manual bootstrapping
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
       
.. code-block:: yaml

		- Prod8:
		    pipeline: rift
		    approximant: SEOBNRv4PHM
		    bootstrap: manual
		    status: ready
       

Ledger Options
--------------

The RIFT pipeline interface looks for the the sections and values listed below in addition to the information which is required for analysing *all* gravitational wave events such as the locations of calibration envelopes and data.


``bootstrap``
~~~~~~~~~~~~~

.. note::
   Full support for RIFT bootstrapping using asimov is still experimental, and care should be taken when using it.

RIFT allows a previous analysis to be used to "bootstrap" a new analysis, and this can be specified via the ``bootstrap`` configuration on the entry in the ledger.

The value ``manual`` can be passed to this parameter to provide a pre-generated bootstrapping grid to the analysis.
This should be placed in the event repository in the same directory as the analysis configuration file, with the name ``ANALYSIS_NAME_bootstrap.xml.gz``.
For example, for an analysis called ``Prod8`` the ledger entry for the analysis might look like this:

.. code-block:: yaml

		- Prod8:
		    pipeline: rift
		    approximant: SEOBNRv4PHM
		    bootstrap: manual
		    status: ready

and the boostrap grid should be named ``Prod8_bootstrap.xml.gz``.

You should combine this with a ``needs`` instruction, so that the RIFT job isn't run until the bootstrapping job has completed.


The settings below are all of the RIFT-specific settings which can be specified in blueprints provided for RIFT analyses, which can be specified in addition to the general set for all gravitational wave pipelines.

``sampler``
~~~~~~~~~~~

These settings specifically affect the sampling process within RIFT.
Within the sampler settings there is a further sub-division for each stage of the analysis.

CIP
"""

``explode jobs``
  This alters the number of jobs to be used in the CIP stage of sampling.
  The higher this number the lower the likely runtime.
  If not provided it defaults to 3.

``fitting method``
  Determines the fitting method used in the CIP stage.
  Can be either ``rf`` or ``gp``.
  If not provided it defaults to ``rf``.

``explode jobs auto``
  TODO: Check what this does.

``sampling method``
  Determines the sampling method to be used in the CIP stage.
  This can be ``default``, ``GMM``, or ``adaptive_cartesian_gpu``, and the latter does not require the use of GPUs during the CIP stage.
  Default is ``default``

``waveform``
~~~~~~~~~~~~

``maximum mode``
  The maximum mode order to be used from the waveform model.
  Note that if the ``likelihood>start frequency`` has not been set then it will be set as ``(2 / Lmax) * f_min``,
  where ``Lmax`` is the maximum node set in this setting, and ``f_min`` is the value set in ``quality>minimum frequency``
  Default is 2.
  TODO: Double check this!

``reference frequency``
  The reference frequency for the waveform.
  Quantities such as spin will be calculated at this frequency in the analysis.

  
``likelihood``
~~~~~~~~~~~~~~

These settings affect the likelihood function, and are further subdivided.

``marginalization``
"""""""""""""""""""

``distance``
  If set to true, enables distance marginalization in the analysis.
  Default is False

``distance lookup``
  If set provides a lookup table to the distance marginalization process.
  If not set this is calculated during the analysis.
  By default this is not set.

``maximum distance``
  This setting is required for distance marginalization, provided in megaparsecs.
  This is the maximum distance to be considered in the analysis.
  Defaults to 10000 Mpc

``assume``
""""""""""

Arguments in this section force the behaviour of the analysis in certain ways by making assumptions about the behaviour of the system under analysis.
Each assumption should be provided as an item in the ``assume`` list, for example

.. code-block:: yaml

   likelihood:
     assume:
       - no spin
       - matter

would set-up an analysis where both components were assumed to have matter effects but no spin.
	 
``no spin``
  If provided, this forces the analysis to ignore spin, and assume both components of the binary are non-spinning.

``precessing``
  If provided, this forces the analysis to assume that both components may be spinning and may have non-aligned spins producing precession.

``nonprecessing``
  If provided, this forces the analysis to assume that both components' spins are aligned, and the system is not precessing.

``matter``
  If provided, this forces the analysis to assume that both components may have matter effects (e.g. a binary neutron star system).

``matter secondary``
  If provided, this forces the analysis to assume that only the secondary component will have matter effects (e.g. a black hole / neutron star system).
