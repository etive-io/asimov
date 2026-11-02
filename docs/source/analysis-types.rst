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

.. _analysis-type-hooks:

The hooks
---------

A type changes what asimov does by overriding **hooks**: methods of :class:`asimov.analysis.SimpleAnalysis` which do nothing, or the ordinary thing, until they are overridden.
These are the whole of what a type may rely on.
Everything else in an analysis (its other methods, its private attributes, how it is stored) is internal and may change without notice.
Keep what a type needs in ``meta``, which is what is stored.

Building (called as the analysis is built, once each and in this order, after its metadata is assembled and its pipeline made):

``set_defaults()``
   Add the metadata which this kind of analysis has when it is not given. Only add what is missing: what is there was given. (The class attribute ``meta_defaults`` is the simplest way to have a default.)
``migrate()``
   Move metadata from where it used to be to where it is now. It runs on every build, so it has to cope with what is already migrated.
``after_build()``
   Work out anything else from the finished metadata. It must not raise for what is in a ledger, which is built on every load: record a problem, and report it when the analysis is used.

Applying and asking:

``validate()``
   Return the problems (as sentences) which a person applying the analysis should fix. It is called when a blueprint is applied, before anything is stored, and an analysis with any is refused, and the others in the blueprint go on. It is never called when a ledger is loaded.
``match_attribute(attribute, match)``
   Test an attribute which is the type's own in a filter, such as a ``needs:`` entry or a selection: ``needs: [{round: "<3"}]``. Return a ``bool``, or ``None`` to leave it to asimov, which looks in the metadata as it always did. :func:`asimov.analysis_types.compare` does comparison operators (``<``, ``<=``, ``>``, ``>=``, ``==``, ``!=``), as numbers where they are numbers.
``rundir_name()``
   The path of the run directory under the working directory of the subject, for an analysis which has none yet (``round-3/fit``, say). It is worked out the first time it is needed and then kept, so changing it moves only the analyses made after.
``card_details()``
   ``(label, value)`` pairs to show on the analysis in the report, in the *Details* of its window.

The ledger vocabulary
---------------------

A type brings the terms which it uses to the :doc:`vocabulary <vocabulary>`, so that ``asimov vocabulary check`` knows them, with ``vocabulary`` on its class, in the same format as a plugin's vocabulary.
They are not owned by a pipeline, because a type can be used with any pipeline.

An example
----------

``toy-step`` (``asimov.pipelines.testing.types``, only there when testing) is the type of one stream in one round of an iterative fit, and uses each hook once:

.. code-block:: python

    class ToyStep(SimpleAnalysis):
        vocabulary = {"terms": {"round": {"type": "integer", "description": "..."},
                                "stream": {"type": "string", "description": "..."}}}

        @property
        def round(self):
            return int(self.meta["round"])          # a typed view of what is stored

        def validate(self):
            return [] if self.round >= 1 else ["'round' must be at least 1"]

        def match_attribute(self, attribute, match):
            if attribute == ["round"]:
                return compare(self.round, match)    # round: "<3"
            return None

        def rundir_name(self):
            return os.path.join(f"round-{self.round}", self.name)

        def card_details(self):
            return [("Round", self.round), ("Stream", self.meta["stream"])]

The gravitational-wave type is made of the same hooks: its defaults, its migration of the deprecated ``quality`` keys, and its PSD resolution are its ``set_defaults``, ``migrate`` and ``after_build``.

``Production.from_dict`` (and so everything which builds an analysis) chooses the type; asking a class directly (``SimpleAnalysis.from_dict``) builds that class.
Constructing ``Production(...)`` directly, as the REST API does, builds a gravitational-wave analysis.
