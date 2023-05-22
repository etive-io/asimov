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


``sampler``
~~~~~~~~~~~

These settings specifically affect the sampling process within RIFT.

``cip jobs``
  This alters the number of jobs to be used in the CIP stage of sampling.
  If not provided it defaults to 3.

``likelihood``
~~~~~~~~~~~~~~

These settings affect the likelihood function and the waveform generator.

``lmax``
  The maximum order of harmonic to use from the waveform.
  Defaults to 2 for non-higher mode waveforms, and 4 if ``HM`` is contained within the name of the waveform.
