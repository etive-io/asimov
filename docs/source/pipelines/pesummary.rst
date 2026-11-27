.. _pesummary-pipelines:

PESummary postprocessing
========================

`PESummary <https://lscsoft.docs.ligo.org/pesummary/>`_ post-processes the posterior samples from gravitational wave parameter estimation: it calculates derived quantities, combines the samples into a single file, and makes web pages which let you explore the results.

PESummary support is not part of asimov core. It's provided by the optional
``asimov-pesummary`` plugin, which you'll need to install separately:

.. code-block:: console

   $ pip install asimov-pesummary

PESummary doesn't run automatically when a parameter estimation analysis finishes.
To get summary pages you add it to your workflow with a blueprint, like any other analysis.

Settings
--------

The plugin reads its settings from ``postprocessing.pesummary``.
These must be in the project **before** you apply a ``pesummary`` analysis, and ``multiprocess``, the number of CPUs to use, is required.
The LVK's production defaults (see :doc:`the GW150914 tutorial <../tutorials/analysing-gw150914>`) include them; otherwise, apply your own:

.. code-block:: yaml

   kind: configuration
   postprocessing:
     pesummary:
       multiprocess: 4
       accounting group: ligo.dev.o4.cbc.pe.bilby   # needed on LVK clusters
       cosmology: Planck15_lal
       redshift: exact
       skymap samples: 2000
       calculate:
         - precessing snr

See the ``asimov-pesummary`` documentation for the other settings.

.. warning::
   The ``evolve spins: forwards`` setting currently has no effect, because of
   `a bug in the plugin <https://github.com/etive-io/asimov-pesummary/issues/13>`_.

Adding summary pages
--------------------

Use a :ref:`subject analysis <subject-analysis>`, which works on the results of other analyses of the same event:

.. code-block:: yaml

   kind: analysis
   name: summary-pages
   pipeline: pesummary
   analyses:
     - pipeline: bilby
   refreshable: true

``analyses`` selects the results to include, here those of every ``bilby`` analysis of the event, and asimov waits for them to finish before submitting this one.
With ``refreshable: true``, asimov runs it again when there are new results to include.

Apply it to an event in the usual way:

.. code-block:: console

   $ asimov apply -f summary.yaml -e GW150914_095045

Each analysis being summarised needs a waveform ``approximant``, a ``reference frequency``, and a likelihood ``minimum frequency``.
The usual gravitational wave event and analysis blueprints provide these.

Results
-------

Relative to the project directory, the pages for the example above are at ``pages/GW150914_095045/summary-pages/pesummary/home.html``, and the combined samples file is ``samples/posterior_samples.h5`` in the same ``pesummary`` directory.
