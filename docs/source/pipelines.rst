==================
Pipeline interface
==================

In order to interact with the various pipelines asimov needs some additional glue code.

An interface for any pipeline can be constructed, provided that pipeline can be submitted to a condor scheduler using a DAG file.

The ``asimov.pipeline`` module defines the factory classes for these interfaces, and individual interfaces can be found in the ``asimov.pipelines`` module.

Supported Pipelines
-------------------

As of asimov 0.7, no analysis pipelines are bundled with asimov core; ``asimov/pipelines/`` only ships
the internal testing pipelines used by asimov's own test suite. Pipeline support is instead provided by
plugin packages, registered via the ``asimov.pipelines`` entry-point group. The following pipelines are
available as optional plugin packages (see each page for the ``pip install`` command):

+ :ref:`LALInference<lalinference-pipelines>`
+ :ref:`BayesWave<bayeswave-pipelines>`
+ :ref:`PESummary<pesummary-pipelines>`

Bilby and RIFT support were removed from asimov core in the 0.7 release, and no public plugin package
currently replaces them (see :ref:`Bilby<bilby-pipelines>` and :ref:`RIFT<rift-pipelines>` for details).

Adding new pipelines
--------------------

New pipelines can be added to asimov by overloading the various methods in the ``asimov.pipeline.Pipeline`` class.
Details for how you can develop new pipeline interfaces can be found in the :ref:`pipelines development guide<pipeline-dev>`.
