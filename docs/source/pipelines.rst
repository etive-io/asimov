==================
Pipeline interface
==================

In order to interact with the various pipelines asimov needs some additional glue code.

An interface for any pipeline can be constructed, provided that pipeline can be submitted to a condor scheduler using a DAG file.

The ``asimov.pipeline`` module defines the factory classes for these interfaces, and individual interfaces can be found in the ``asimov.pipelines`` module.

Supported Pipelines
-------------------

The following pipelines currently have support bundled with asimov:

+ :ref:`LALInference<lalinference-pipelines>`
+ :ref:`BayesWave<bayeswave-pipelines>`
+ :ref:`Bilby<bilby-pipelines>`
+ :ref:`RIFT<rift-pipelines>`

Adding new pipelines
--------------------

New pipelines can be added to asimov by overloading the various methods in the ``asimov.pipeline.Pipeline`` class.
Details for how you can develop new pipeline interfaces can be found in the :ref:`pipelines development guide<pipeline-dev>`.
