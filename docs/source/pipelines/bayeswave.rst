.. _bayeswave-pipelines:

BayesWave Pipeline
==================

.. note::
   Starting with asimov 0.7, BayesWave support is provided via the asimov-bayeswave plugin.
   Install with: ``pip install asimov[gw]`` or ``pip install asimov-bayeswave``

The BayesWave pipeline interface allows asimov to configure and monitor analyses using BayesWave.
BayesWave is frequently used as the first analysis of an event in order to generate the on-source PSD estimates for subsequent analyses.

Installation
------------

To use BayesWave with asimov 0.7+::

    pip install asimov[gw]

Or install asimov-bayeswave directly::

    pip install asimov-bayeswave

The plugin is automatically discovered through Python entry points once asimov-bayeswave is installed.

Review Status
-------------

.. note::
   The asimov-bayeswave plugin integration is fully reviewed and suitable for use with all collaboration analyses.

Migration from asimov <0.7
--------------------------

If upgrading from asimov <0.7:

1. Install asimov-bayeswave: ``pip install asimov[gw]``
2. No changes needed to ledger files
3. All features work as before

Usage
-----

Once installed, use BayesWave in your ledger as before:

.. code-block:: yaml

   - Prod0:
       pipeline: bayeswave
       status: ready

Configuration options and examples remain unchanged from previous versions.
See the :ref:`ligo-cookbook-bayeswave` for detailed examples.

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

The BayesWave pipeline interface looks for the sections and values listed below in addition to the information which is required for analysing *all* gravitational wave events such as the locations of calibration envelopes and data.


``quality``
~~~~~~~~~~~

These settings specifically relate to data quality related settings.

``segment start``
  The start time of the segment.
  If not specified, the start time of the segment is determined by subtracting the ``quality>segment length`` setting from the ``event time``, and adding 2 (that is, the event time is placed two seconds from the end of the segment.


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

Additional Resources
--------------------

For full asimov-bayeswave documentation, including advanced configuration options and troubleshooting, see the `asimov-bayeswave documentation <https://asimov-bayeswave.readthedocs.io/>`_.
