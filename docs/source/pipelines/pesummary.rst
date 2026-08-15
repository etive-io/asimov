.. _pesummary-pipelines:

PESummary postprocessing
========================

PESummary is used by some analysis pipelines for postprocessing gravitational wave parameter estimation samples.

PESummary support is not part of asimov core. It's provided by the optional
``asimov-pesummary`` plugin, which you'll need to install separately:

::
   $ pip install asimov-pesummary

Once the plugin is installed, ``pipeline: pesummary`` in a blueprint will resolve to it, and
pipelines which support PESummary post-processing (such as ``bilby`` and ``rift``) will
automatically run it when asimov detects that the main analysis job is completed, so no
additional configuration is usually required just to run this step.

The PESummary package implements a large amount of post-processing functionality, not all of
which is implemented in the plugin at present; see the ``asimov-pesummary`` documentation for
what's currently configurable.
