The ledger vocabulary
=====================

Every pipeline which asimov runs reads its settings from the same ledger.
That only works if each quantity has **one name** which every pipeline
agrees on: if one plugin reads ``likelihood: minimum frequency`` and
another reads ``myplugin: f_min``, a user has to specify the same number
twice, and the two analyses can silently disagree.

Asimov therefore ships a machine-readable *vocabulary* describing every
standard ledger key: what it means, its type and units, whether it is given
per detector, which parts of asimov read it, and which spellings are
deprecated. The vocabulary lives in ``asimov/vocabulary.yaml`` and is
available from Python as :mod:`asimov.vocabulary` and on the command line as
``asimov vocabulary``.

The rule
--------

A term belongs in the core vocabulary if it has **the same meaning for every
pipeline which reads it**. Sampling rate, minimum frequency, PSD files,
waveform approximant and accounting group all qualify, even if today only
one pipeline reads them.

A quantity which only makes sense to one pipeline (a BayesWave chain count,
a RIFT grid setting) belongs to that pipeline. New pipeline-specific terms
should be registered by the plugin (see below) rather than added to core.

Before you add a key to a plugin, ask: *if bilby, RIFT, or another pipeline
ran the same analysis, would it need this number?* If the answer is yes,
use (or propose) a core term.

Using the vocabulary from the command line
------------------------------------------

The ``asimov vocabulary`` commands work outside an asimov project, so they
can be used while developing a plugin.

.. code-block:: console

   $ asimov vocabulary show "likelihood.minimum frequency"
   path: likelihood.minimum frequency
   description: The minimum frequency of the likelihood integral for each detector. ...
   type: float
   per ifo: true
   units: Hz

   $ asimov vocabulary check my-blueprint.yaml --pipeline mypipeline
   my-blueprint.yaml: scheduler.cpus: [unknown] 'cpus' is not in the asimov ledger vocabulary. Did you mean 'scheduler.request cpus'?
   my-blueprint.yaml: mypipeline.data.psd_files: [duplicate] 'mypipeline.data.psd_files' duplicates the standard term 'psds' ...

``asimov vocabulary check`` reports:

``unknown``
  A key which is not in the vocabulary. A suggestion is given where one of
  the vocabulary's synonyms or a close spelling matches.
``duplicate``
  A key inside a pipeline's own namespace (for example ``mypipeline:``)
  which means the same thing as a standard term.
``alias``
  An accepted but non-canonical spelling (for example ``window-length``).
``deprecated``
  A term which has moved (for example ``quality: minimum frequency``).
``foreign``
  A term owned by a different pipeline from the one the file is for.
``type``
  A value of the wrong type: a section (such as ``likelihood``) given a
  scalar, a per-detector value given a scalar, or a leaf of the wrong type
  (e.g. ``scheduler: request cpus: four``).

``check`` accepts blueprints and whole project ledgers (``.asimov/ledger.yml``
for projects using the ``yamlfile`` ledger engine); events and analyses
nested in a ledger are checked too.

It exits with status 1 on ``unknown``, ``duplicate`` or ``type`` findings,
or on any finding with ``--strict``, so it can be used in a plugin's CI.
``--json`` gives machine-readable output.

``asimov vocabulary list`` prints the whole tree, ``asimov vocabulary export
--format json`` dumps it (including installed plugins' terms) for use by
other tools, and ``asimov vocabulary lint`` reports plugin-registered terms
which clash with or duplicate core terms.

``likelihood.components``
--------------------------

Some pipelines (for example BayesWave) can fit different combinations of
components of the data model rather than always assuming a single
compact-binary signal on top of a fixed, Gaussian noise PSD. These are
described generically, so that any pipeline capable of it can read them:

.. code-block:: yaml

   likelihood:
     components:
       signal: wavelets
       glitch: wavelets
       noise:
         psd: fit
         lines: true

A pipeline which cannot fit a requested combination of components should
raise an error at build time rather than silently ignoring it.

Standard assets
---------------

The vocabulary also names the standard entries in the dictionary returned by
:meth:`asimov.pipeline.Pipeline.collect_assets`. Downstream analyses find
their inputs by these names (for example, :meth:`asimov.analysis.Analysis._collect_psds`
looks for a ``psds`` asset on the analyses listed in ``needs``), so a
pipeline which produces PSDs must return them as ``psds``, not
``psd_files``.

Registering pipeline-specific terms
-----------------------------------

A plugin can extend the vocabulary through the ``asimov.vocabulary`` entry
point. The entry point's name should be the pipeline name, and it should
resolve to a dictionary in the same format as ``vocabulary.yaml``, a path to
a YAML file in that format, or a callable returning either.

.. code-block:: toml

   [project.entry-points."asimov.vocabulary"]
   mypipeline = "asimov_mypipeline:vocabulary"

.. code-block:: python

   # asimov_mypipeline/__init__.py
   import importlib.resources

   def vocabulary():
       return importlib.resources.files(__name__).joinpath("vocabulary.yaml")

.. code-block:: yaml

   # asimov_mypipeline/vocabulary.yaml
   terms:
     mypipeline:
       description: Settings which only mypipeline understands.
       children:
         chains:
           type: integer
           description: The number of parallel-tempered chains.
     sampler:
       children:
         temperature ladder:
           type: list
           description: The temperature ladder for parallel tempering.

Terms registered this way are marked as owned by the plugin. A plugin may add
children to an existing core section, but it cannot redefine an existing
term: attempts to do so are ignored and reported by ``asimov vocabulary
lint``.

Keys under a pipeline's own namespace which the plugin has *not* registered
are not reported as unknown, but any of them which match a standard term are
reported as duplicates.

Term fields
-----------

Each entry in ``vocabulary.yaml`` may have the following fields:

``description`` (required)
  What the value means.
``type``
  One of ``section``, ``string``, ``float``, ``integer``, ``boolean``,
  ``list``, ``mapping`` or ``any``.
``per ifo``
  ``true`` if the value is a mapping from detector abbreviation to a value.
``units``
  The physical units of the value.
``open``
  ``true`` if the section accepts arbitrary child keys.
``aliases``
  Alternative spellings which are accepted.
``synonyms``
  Names people commonly use for this term. These are not accepted, but are
  used to suggest the right term.
``deprecated``
  ``{replaced by: <path>, since: <version>}``.
``owner``
  The pipeline which owns a pipeline-specific term.
``used by``
  The asimov functions which read the term.
``items``
  ``document`` if the term is a list whose entries are themselves ledger
  documents (``events``, ``analyses``, ``productions``, ...). Mapping
  entries, including the stored ``{name: {...}}`` form, are checked against
  the whole vocabulary.
``children``
  Nested terms.

Python API
----------

.. automodule:: asimov.vocabulary
   :members: Vocabulary, Term, Asset, Finding, get_vocabulary
