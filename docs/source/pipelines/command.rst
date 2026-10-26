.. _command-pipeline:

The command pipeline
====================

Not every step of an analysis needs a pipeline interface. Fetching a dataset, converting a
file, or running one script on what another analysis produced are all commands, and asimov can
run a command directly, with the same ``needs``, scheduler, monitoring and status as any other
analysis.

An analysis with a ``command`` and no ``pipeline`` uses the built-in ``command`` pipeline;
``pipeline: command`` says the same thing explicitly::

   kind: analysis
   name: fit-r003
   command: [gwaith_fit_sine, --data-file, "{inputs.input_data}", --output, "{outputs.signal}"]
   outputs:
     signal: round_003_signal.hdf
   needs:
     - prep-r002

It is also what ``pipelines: command:`` (defaults) and ``needs: [{pipeline: command}]`` refer to.

``command``
   The executable and its arguments, as a list of words. A string is split like a shell would,
   but is **never run by a shell**: no word is expanded, so nothing needs quoting against
   spaces, ``;`` or ``$`` in a path.

``outputs``
   What the command writes, as ``name: path`` (relative to the run directory) or
   ``name: {path: ...}``. An analysis is complete when it exits successfully and everything
   declared exists. With no outputs, it is complete when it exits successfully.

``scheduler``
   The resources the job asks for (``request memory``, ``request cpus``, ``request disk``,
   ``request gpus``, ``accounting group``), as for other analyses. It is submitted to the
   project's scheduler, so it runs as a process with ``type = local`` and as a job under
   HTCondor or Slurm.

Placeholders
------------

``{inputs.NAME}``
   The asset ``NAME`` of the analyses this one ``needs``. Assets are what a pipeline's
   ``collect_assets()`` returns, so they are the outputs of other command analyses, and what
   ``asimov-gwdata`` calls ``frames``, ``psds``, ``xml psds`` or ``calibration``. An asset may be a
   path, a list of paths, or a mapping from a label (say, an interferometer) to either.

``{inputs.NAME.LABEL}``
   One label of a mapping, for instance ``{inputs.psds.H1}``.

``{outputs.NAME}``
   Where the command should write the output ``NAME``.

A word which is only a placeholder becomes as many words as there are paths. Inside a longer
word (``--psd={inputs.psds.H1}``) it must be a single path. The executable cannot be a
placeholder. An input that no analysis provides stops the build with an error which says what
the analysis needs, and ``validate_needs`` warns about it first.

Datasets
--------

A dataset which is not event metadata is an analysis which produces it::

   kind: analysis
   name: bulk-data
   command: [cp, /archive/round3/data.hdf, data.hdf]
   outputs:
     data: data.hdf

and what uses it says ``needs: [bulk-data]`` and ``{inputs.data}``. Data and calibration which
are fetched by an ``asimov-gwdata`` analysis are used in exactly the same way.

The project must allow it
-------------------------

The command comes from the ledger, so anyone who can write a blueprint can run it as the
account which submits jobs. The pipeline is therefore **off unless the project enables it**::

   [pipelines.command]
   enabled = true
   allowed_executables = gwaith_*, python

``asimov init`` enables it in the configuration of a new project, since the person who can write
its blueprints can already run anything from a shell. A shared instance leaves it off, or lists
what may run: ``allowed_executables`` are patterns for the first word of the command exactly as
written, so ``python`` allows ``python`` on the ``PATH`` and not ``/tmp/other/python``. The check
is made when the analysis is built and again when it is submitted, whichever way it was spelled.

Subclasses
----------

A tool with known inputs, outputs and options can subclass
``asimov.pipelines.command.CommandPipeline`` and override ``command_template``, ``output_specs``,
``input_names`` and (for a stricter check than the existence of the outputs) ``command_succeeded``.
Set ``arbitrary_command = False`` when the class fixes the executable, so the project's
``[pipelines.command]`` section is not consulted.

A project which uses command analyses records the ``command-pipeline`` feature in its ledger, and
asimov warns once when it is first used. A version of asimov without it cannot construct these
analyses.
