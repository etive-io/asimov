BayesWave pipelines
===================

The BayesWave interface allows asimov to configure and monitor analyses using BayesWave.
BayesWave is frequently used as the first analysis of an event in order to generate the on-source PSD estimates for subsequent analyses.

Review Status
-------------

.. note::
   The current integration with BayesWave is fully reviewed and is suitable for use with all collaboration analyses.

Examples
--------

BayesWave on-source PSD Generation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This was the default analysis setup for the O3 catalog runs which were used in the GWTC-2.1 and GWTC-3 catalog papers.

.. code-block:: yaml

   - Prod0:
       pipeline: bayeswave
       status: ready


Ledger Options
--------------

The Bayeswave pipeline interface looks for the the sections and values listed below in addition to the information which is required for analysing *all* gravitational wave events such as the locations of calibration envelopes and data.


``quality``
~~~~~~~~~~~

These settings specifically relate to data quality related settings.

``segment start``
  The start time of the segment.
  If not specified, the start time of the segment is determined by subtracting the ``quality>segment length`` setting from the ``event time``, and adding 2 (that is, the event time is placed two seconds from the end of the segment.

``supress``
  Optional. A mapping of interferometer names to one or more frequency bands that should be suppressed in the PSD before it is passed to downstream analyses.
  Suppression sets the PSD value to 1.0 in the specified band, effectively notching that frequency range out of the analysis.

  A single notch is specified as a mapping with ``lower`` and ``upper`` keys:

  .. code-block:: yaml

     quality:
       supress:
         H1:
           lower: 59.0
           upper: 61.0
         L1:
           lower: 59.0
           upper: 61.0

  Multiple notches per interferometer can be specified as a list:

  .. code-block:: yaml

     quality:
       supress:
         H1:
           - lower: 59.0
             upper: 61.0
           - lower: 119.0
             upper: 121.0

  The single-mapping form is retained for backwards compatibility; both forms may be freely mixed across interferometers.


``sampler``
~~~~~~~~~~~

These settings relate specifically to the sampling process used in Bayeswave.

``iterations``
  The number of iterations to be carried out.

``scheduler``
~~~~~~~~~~~~~~

These settings relate specifically to the accounting and scheduling of the job.

``memory``
  The amount of memory to request.

``post memory``
  The amount of memory to request for post-processing.

``accounting group``
  The group to use for accounting.
