.. _analysis-types:

Analysis types
==============

An analysis has a *type*, which is the class asimov builds it from.
Until analysis types, every analysis of a subject was a gravitational-wave one, whatever its domain: it had a likelihood, a waveform and data in its metadata, and asimov looked for PSDs for it.
A plugin can now provide a type for its own domain, in the way it provides a pipeline.

Choosing a type
---------------

The type of an analysis is, in this order:

1. its ``type:``, in the analysis or the blueprint, which lets a type be used with any pipeline;
2. the ``analysis_type`` of the class of its pipeline, which is looked up before the analysis is built;
3. ``gravitational-wave-transient``, which is what every analysis was before.

A pipeline which declares nothing, and an analysis which says nothing, are unchanged.

.. code-block:: yaml

    kind: analysis
    name: fit-r003
    command: [fit, --out, "{outputs.result}"]
    type: fit-component     # a type which a plugin provides, used with the command pipeline
    round: 3

asimov provides two types:

``simple``
   A generic analysis, with nothing of any domain: no gravitational-wave metadata and no PSDs.
   The :ref:`command pipeline <command-pipeline>` declares this type, so a command analysis is a generic one.
``gravitational-wave-transient``
   What every analysis was, and still is by default.

A type which is not installed is an error, naming the types which are, when the analysis is applied.
When a project is loaded, an analysis whose type (or pipeline) is not installed is left out, with a warning which says which plugin is missing, so that one missing plugin does not make a whole subject unreadable.

``type:`` is kept in the metadata of the analysis, so it loads as the same type, and only if the blueprint gave it.
The first time one is applied the project records that it uses analysis types, and says so: a version of asimov without them loads such an analysis as a gravitational-wave one, with ``type`` as one more key of metadata, which is harmless to read but gives it the gravitational-wave defaults.

Providing a type
----------------

A type is a class, registered by name in the ``asimov.analysis_types`` entry-point group:

.. code-block:: toml

    [project.entry-points."asimov.analysis_types"]
    fit-component = "my_package.types:FitComponent"

.. code-block:: python

    from asimov.analysis import SimpleAnalysis

    class FitComponent(SimpleAnalysis):
        @property
        def round(self):
            return int(self.meta["round"])

Subclass :class:`asimov.analysis.SimpleAnalysis`, which has what every analysis of a subject needs, or :class:`asimov.analysis.GravitationalWaveTransient` for something which builds on the gravitational-wave one.
What the type keeps is in ``meta``, which is what is stored, so a type needs no migration and a typed attribute is a view of the metadata.
A pipeline which wants its analyses to be of a type sets ``analysis_type`` on its class:

.. code-block:: python

    class FitPipeline(Pipeline):
        analysis_type = "fit-component"

Types are found once, the first time one is asked for. A type plugin which fails to load is reported and left out.

``Production.from_dict`` (and so everything which builds an analysis) chooses the type; asking a class directly (``SimpleAnalysis.from_dict``) builds that class.
Constructing ``Production(...)`` directly, as the REST API does, builds a gravitational-wave analysis.
