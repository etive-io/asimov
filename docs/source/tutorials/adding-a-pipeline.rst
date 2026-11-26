Adding a pipeline to asimov
===========================

A *pipeline* tells asimov how to run a particular kind of analysis: what to execute, what it produces, and how to tell whether it worked.
Asimov's pipelines are plugins, so you can add your own without changing asimov itself.

In this tutorial you'll turn the spring-fitting program from :ref:`Getting started<Getting Started>` into a pipeline called ``springfit``.

.. rst-class:: tutorial-intro

:What you'll learn: How to package a program as an asimov pipeline, give it settings and defaults, and check that its results are what you expect.
:Time required: About 20 minutes.
:Prerequisites: The project and programs you made in :ref:`Getting started<Getting Started>`, and some familiarity with Python classes and packages.

Do you need a plugin?
---------------------

Often you don't.
A blueprint with a ``command`` runs any program, as you saw in Getting started, and for a one-off analysis that's all you need.
It's worth writing a plugin when you find yourself repeating the same command in many blueprints, or when you want asimov to know more about your program than its command line:

* blueprints become shorter, because the command is written once, in the pipeline;
* settings can have defaults, and be checked;
* asimov can apply a stricter test of success than "the output files exist";
* other people can install it and use it in their own projects.

.. rst-class:: procedural-step

Create the package
------------------

A plugin is an ordinary Python package.
In your ``asimov-tutorial`` directory, with the virtual environment active and the ``scripts`` directory on your ``PATH``, make a directory for it:

.. code-block:: bash

   $ mkdir -p asimov-spring/asimov_spring

.. rst-class:: procedural-step

Write the pipeline
------------------

The simplest way to write a pipeline is to build on the one which runs commands, :ref:`CommandPipeline<command-pipeline>`.
It already knows how to submit a command to the scheduler, wait for it, and collect its outputs, so you only need to describe what's special about yours:

.. code-block:: python
   :caption: asimov-spring/asimov_spring/__init__.py

   """Run the spring fit from asimov."""
   from asimov.pipelines.command import CommandError, CommandPipeline

   MODELS = ("constant", "line")


   class SpringFit(CommandPipeline):
       """Fit a model to the measurements of a spring."""

       name = "springfit"

       # This class decides what is run, not the blueprint.
       arbitrary_command = False

       def model(self):
           settings = self.production.meta.get("springfit", {})
           model = settings.get("model", "line")
           if model not in MODELS:
               raise CommandError(
                   f"springfit: model must be one of {', '.join(MODELS)}, not '{model}'"
               )
           return model

       def command_template(self):
           return ["fit.py", self.model(), "{inputs.data}", "{outputs.fit}"]

       def output_specs(self):
           return {"fit": {"path": "fit.txt"}}

       def command_succeeded(self):
           with open(self.output_path("fit")) as handle:
               words = handle.read().split()
           return len(words) == 2 and words[0] == self.model()


   # The settings which the pipeline adds to asimov's vocabulary.
   vocabulary = {
       "terms": {
           "springfit": {
               "description": "Settings for the springfit pipeline.",
               "children": {
                   "model": {
                       "type": "string",
                       "description": "The model to fit: constant or line.",
                   },
               },
           },
       },
   }

Here is what each part does:

``name``
   The name of the pipeline. In lower case, it must be exactly the name you register in the next step, or asimov won't be able to load analyses which use it.
``arbitrary_command``
   A project can restrict which commands its blueprints may run. Setting this to ``False`` says that the command is fixed by this class, so those restrictions don't apply.
``model``
   A method of our own, which reads a setting from the analysis and checks it. ``self.production.meta`` holds all of the analysis's settings. It's good practice to keep settings which only your pipeline understands under its own name, here ``springfit``.
``command_template``
   The command to run, with the same ``{inputs.…}`` and ``{outputs.…}`` placeholders you'd use in a blueprint.
``output_specs``
   The files the command writes.
``command_succeeded``
   An extra check, made once the outputs exist. Here, the result must be for the model which was asked for.
``vocabulary``
   A description of the settings your pipeline adds. You'll use it in a moment.

.. rst-class:: procedural-step

Register it with asimov
-----------------------

Asimov finds pipelines using Python *entry points*, which a package declares in its ``pyproject.toml``:

.. code-block:: toml
   :caption: asimov-spring/pyproject.toml

   [build-system]
   requires = ["setuptools"]
   build-backend = "setuptools.build_meta"

   [project]
   name = "asimov-spring"
   version = "0.1.0"
   dependencies = ["asimov>=0.9.0a1"]

   [project.entry-points."asimov.pipelines"]
   springfit = "asimov_spring:SpringFit"

   [project.entry-points."asimov.vocabulary"]
   springfit = "asimov_spring:vocabulary"

The first entry point says that the pipeline called ``springfit`` is the class ``SpringFit`` in the module ``asimov_spring``, and the second tells asimov where to find its vocabulary.

Install the package into the same environment as asimov.
The ``-e`` option means that changes you make to the code take effect without installing it again:

.. code-block:: bash

   $ pip install -e ./asimov-spring

.. rst-class:: procedural-step

Use your pipeline
-----------------

An analysis now only needs to name the pipeline, and say what it needs.
Save these blueprints as ``springfit.yaml``:

.. code-block:: yaml
   :caption: springfit.yaml

   kind: analysis
   name: springfit-line
   pipeline: springfit
   needs:
     - make-data
   ---
   kind: analysis
   name: springfit-constant
   pipeline: springfit
   springfit:
     model: constant
   needs:
     - make-data

The first analysis uses the default model, and the second chooses its own.

The outputs of your pipeline can be used by any other analysis.
To compare the two fits, save this blueprint, an ordinary ``command`` analysis, as ``compare.yaml``:

.. code-block:: yaml
   :caption: compare.yaml

   kind: analysis
   name: springfit-compare
   command: [compare.py, "{outputs.summary}", "{inputs.fit}"]
   outputs:
     summary: summary.txt
   needs:
     - springfit-line
     - springfit-constant

Apply them, and run the workflow:

.. code-block:: bash

   $ asimov apply -f springfit.yaml -e spring-1
   $ asimov apply -f compare.yaml -e spring-1
   $ asimov monitor --chain --until-idle --interval 2

.. note::
   With asimov 0.9.0a1 you'll see ``Failed to build`` errors about a missing ``springfit.ini`` template.
   The analyses still run, and later versions don't report the errors.

Only the new analyses are run.
Look at the comparison, and at the command which your pipeline constructed:

.. code-block:: bash

   $ cat working/spring-1/springfit-compare/summary.txt

.. code-block:: text

   line: scatter 0.286
   constant: scatter 2.918

.. code-block:: bash

   $ cat working/spring-1/springfit-constant/command.sh

.. tip::
   Asimov accepts a blueprint with a value your pipeline rejects, such as an unknown model, and only fails when it tries to submit the analysis.
   If asimov says it's unable to submit an analysis, look for the reason in its log, ``logs/asimov.log``.

.. rst-class:: procedural-step

Check your blueprints
---------------------

Asimov keeps a *vocabulary* of the settings which can appear in blueprints, and can use it to find mistakes such as misspelled names.
Because your package describes its settings, they're checked too:

.. code-block:: bash

   $ asimov vocabulary check springfit.yaml

.. code-block:: text

   springfit.yaml: OK

If you had written ``modle`` instead of ``model``, this would tell you.
Without that check, a misspelled setting is ignored, and the pipeline quietly uses its default.

.. rst-class:: procedural-step

Set a default for the project
-----------------------------

Anyone using your pipeline can change its defaults for their whole project, with a configuration blueprint.
Save this one as ``defaults.yaml``:

.. code-block:: yaml
   :caption: defaults.yaml

   kind: configuration
   pipelines:
     springfit:
       springfit:
         model: constant

The first ``springfit`` says which pipeline the defaults are for, and the second is your pipeline's own settings.
Apply it:

.. code-block:: bash

   $ asimov apply -f defaults.yaml

Analyses of this pipeline which you add from now on will fit a constant, unless their blueprint chooses a model.

When you need more control
--------------------------

``CommandPipeline`` suits a program which is run once, with its settings on the command line.
Many analysis codes need more than that: they read a configuration file, or they build their own workflow of many jobs.
For those, subclass :class:`asimov.pipeline.Pipeline` and implement the steps yourself:

``config_template``
   A template for the program's configuration file. ``asimov manage build`` fills it in from the analysis's settings, using the `Liquid <https://shopify.github.io/liquid/>`_ templating language, for example ``trigtime={{ production.meta['event time'] }}``.
``build_dag`` and ``submit_dag``
   Create the workflow and hand it to the scheduler. Submit through ``self.scheduler``, so that your pipeline works with whichever scheduler the project uses.
``detect_completion``
   Decide whether the analysis has finished successfully.
``collect_assets``
   Report the results, so that other analyses can use them.

:doc:`The pipeline developer guide <../pipelines-dev>` describes all of these.
For complete examples, see the plugins for `BayesWave <https://github.com/etive-io/asimov-bayeswave>`_ and `PESummary <https://github.com/etive-io/asimov-pesummary>`_.

What's next?
------------

* :ref:`The command pipeline<command-pipeline>` describes the placeholders, and the other methods a subclass can change.
* :doc:`The vocabulary guide <../vocabulary>` explains how to choose names for settings.
* Add tests, publish your package, and other people can add your pipeline to their projects with ``pip``.
