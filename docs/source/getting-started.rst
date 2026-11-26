.. _Getting Started:

Getting started with asimov
===========================

This guide takes you from nothing to a finished workflow on your own computer.
You'll fit two models to some simulated measurements of a stretched spring, and work out which one describes them better.
The science is deliberately simple, so that you can concentrate on how asimov works.

.. rst-class:: tutorial-intro

:What you'll learn: How to create a project, describe a workflow of dependent analyses, let asimov run it, and look at what happened.
:Time required: About 10 minutes.
:Prerequisites: A Linux computer (Windows Subsystem for Linux is fine) with Python 3.10 or newer. You don't need a computing cluster.

.. note::
   If you've come here to analyse gravitational wave data, this guide is still a good introduction to asimov.
   When you've finished it, continue with :doc:`tutorials/analysing-gw150914`.

.. rst-class:: procedural-step

Install asimov
--------------

Make a directory to work in, and install asimov into a new virtual environment inside it:

.. code-block:: bash

   $ mkdir asimov-tutorial
   $ cd asimov-tutorial
   $ python3 -m venv environment
   $ source environment/bin/activate
   $ pip install "asimov>=0.9.0a1"

This guide needs asimov 0.9 or newer, which is currently a pre-release, so the version number in that command matters.
For other ways to install asimov see the :ref:`installation guide<installation-guide>`.

.. rst-class:: procedural-step

Create a project
----------------

Asimov keeps everything about a piece of work in a *project*: its settings, the analyses it contains, and their results.
Turn your directory into a project with ``asimov init``, giving it a name:

.. code-block:: bash

   $ asimov init "My first project"

Asimov adds a few directories of its own.
The most important is ``.asimov``, which holds the project's configuration and its *ledger*: the database in which asimov records every analysis and its status.
You won't need to edit either of them by hand.

Asimov normally sends jobs to a cluster scheduler (HTCondor, unless you say otherwise).
Tell this project to run them as ordinary processes on your computer instead:

.. code-block:: bash

   $ asimov configuration update scheduler/type local

.. rst-class:: procedural-step

Add a subject
-------------

Every analysis in this guide studies one *subject*, the thing you want to find something out about.
In gravitational wave astronomy a subject is usually an event, such as a black hole merger; here it's a spring.

You tell asimov about new things using *blueprints*, which are short YAML files.
Save this one as ``subject.yaml``:

.. code-block:: yaml
   :caption: subject.yaml

   kind: subject
   name: spring-1

and add it to the project's ledger with ``asimov apply``:

.. code-block:: bash

   $ asimov apply -f subject.yaml

.. rst-class:: procedural-step

Write the programs
------------------

Asimov doesn't do any analysis itself: it runs your programs, in the right order, and keeps track of them.
Here you need three small ones, which use only Python's standard library.
Make a directory for them:

.. code-block:: bash

   $ mkdir scripts

The first simulates the measurements, the extension of the spring under twenty different loads, with some random noise added:

.. code-block:: python
   :caption: scripts/make_data.py

   #!/usr/bin/env python3
   """Simulate noisy measurements of a spring: load and extension."""
   import random
   import sys

   output = sys.argv[1]

   random.seed(1)
   with open(output, "w") as handle:
       for load in range(1, 21):
           extension = 2.0 + 0.5 * load + random.gauss(0, 0.3)
           handle.write(f"{load} {extension:.3f}\n")

The second fits a model to the measurements, either a constant or a straight line, and records the typical distance between the data and the model:

.. code-block:: python
   :caption: scripts/fit.py

   #!/usr/bin/env python3
   """Fit a model to the data, and record how far the data lie from it."""
   import statistics
   import sys

   model, data, output = sys.argv[1:]

   with open(data) as handle:
       loads, extensions = zip(*(map(float, line.split()) for line in handle))

   if model == "constant":
       predicted = [statistics.mean(extensions)] * len(extensions)
   else:
       slope, intercept = statistics.linear_regression(loads, extensions)
       predicted = [slope * load + intercept for load in loads]

   scatter = statistics.pstdev([e - p for e, p in zip(extensions, predicted)])

   with open(output, "w") as handle:
       handle.write(f"{model} {scatter:.3f}\n")

The third compares any number of fits, and lists the best one first:

.. code-block:: python
   :caption: scripts/compare.py

   #!/usr/bin/env python3
   """List the fitted models, best first."""
   import sys

   output, *fits = sys.argv[1:]

   results = []
   for fit in fits:
       with open(fit) as handle:
           results.append(handle.read().split())

   with open(output, "w") as handle:
       for model, scatter in sorted(results, key=lambda result: float(result[1])):
           handle.write(f"{model}: scatter {scatter}\n")

Make the programs executable, and add their directory to your ``PATH`` so that they can be found by name:

.. code-block:: bash

   $ chmod +x scripts/*.py
   $ export PATH="$PWD/scripts:$PATH"

.. note::
   If you open a new terminal part-way through, go back to the ``asimov-tutorial`` directory, activate the environment, and run the ``export`` command again.

.. rst-class:: procedural-step

Describe the workflow
---------------------

Next, tell asimov how the programs fit together.
Each run of a program is an *analysis*, described by its own blueprint.
Save the following into a file called ``workflow.yaml``:

.. code-block:: yaml
   :caption: workflow.yaml

   kind: analysis
   name: make-data
   command: [make_data.py, "{outputs.data}"]
   outputs:
     data: data.txt
   ---
   kind: analysis
   name: fit-constant
   command: [fit.py, constant, "{inputs.data}", "{outputs.fit}"]
   outputs:
     fit: fit.txt
   needs:
     - make-data
   ---
   kind: analysis
   name: fit-line
   command: [fit.py, line, "{inputs.data}", "{outputs.fit}"]
   outputs:
     fit: fit.txt
   needs:
     - make-data
   ---
   kind: analysis
   name: compare
   command: [compare.py, "{outputs.summary}", "{inputs.fit}"]
   outputs:
     summary: summary.txt
   needs:
     - fit-constant
     - fit-line

This file holds four blueprints, separated by lines containing three hyphens.
In each of them:

* ``command`` is the program to run and its arguments, written as a list.
* ``outputs`` names the files the program will write. An analysis has only succeeded if they all exist when it finishes.
* ``needs`` lists the analyses which must finish before this one can start.

The words in curly brackets are filled in by asimov.
``{outputs.data}`` is the path where this analysis should write its ``data`` output, and ``{inputs.data}`` is the path to the ``data`` output of an analysis it needs.
The ``compare`` analysis needs two analyses which each have a ``fit`` output, so ``{inputs.fit}`` becomes both paths.

Apply the workflow to your spring.
The ``-e`` option says which subject the analyses belong to:

.. code-block:: bash

   $ asimov apply -f workflow.yaml -e spring-1

.. tip::
   Asimov can run any program in this way. For everything the ``command`` blueprint can do, see :ref:`the command pipeline<command-pipeline>`.

Now ask asimov what it knows about:

.. code-block:: bash

   $ asimov report status

.. code-block:: text

   spring-1
        Analyses
        - make-data command ready
        - fit-constant command ready
        - fit-line command ready
        - compare command ready
        Analyses waiting:
   make-data

All four analyses are ``ready``, which means that they haven't been run yet.
The list at the end shows which of them can start now: only ``make-data``, because the others are still waiting for the analyses they need.

.. rst-class:: procedural-step

Run the workflow
----------------

One command runs the whole workflow:

.. code-block:: bash

   $ asimov monitor --chain --until-idle --interval 2

Asimov repeats a cycle until there's nothing left to do:

#. **Build** each analysis whose needs have been met, by working out the exact command to run.
#. **Submit** it to the scheduler, which here means starting it on your computer.
#. **Monitor** the running analyses, and check whether each has produced its outputs.

``--chain`` asks for all three of these, ``--until-idle`` keeps going until nothing is running and nothing else can start, and ``--interval 2`` waits two seconds between cycles.
It takes a few seconds, and ends with

.. code-block:: text

   ● Idle after 4 passes: everything finished

Notice that ``fit-constant`` and ``fit-line`` were submitted together, as neither depends on the other, while ``compare`` waited for both of them.

.. note::
   With the local scheduler, asimov only keeps track of jobs which were started by the command that's currently running.
   Use the command above, rather than building, submitting and monitoring in separate steps.

.. rst-class:: procedural-step

Look at the results
-------------------

Each analysis ran in its own directory inside ``working``, which holds the exact command that was run (``command.sh``), what the program printed, and the files it made.
Read the result of the comparison:

.. code-block:: bash

   $ cat working/spring-1/compare/summary.txt

.. code-block:: text

   line: scatter 0.286
   constant: scatter 2.918

The data lie far closer to a straight line than to a constant, as you'd expect for a spring.

Asimov can also write a web page which summarises the whole project:

.. code-block:: bash

   $ asimov report html

Open ``pages/index.html`` in a web browser to see it.

Finally, asimov records who changed the project, and when:

.. code-block:: bash

   $ asimov audit show

When an analysis fails
----------------------

If a program exits with an error, or doesn't produce its outputs, asimov marks the analysis as ``stuck``.
Analyses which don't depend on it still run; those which do will wait.

To get a stuck analysis going again:

#. Find it with ``asimov report status``.
#. Read its error log, for example ``working/spring-1/fit-constant/fit-constant.err``.
#. Fix the problem.
#. Make the analysis ready to run again (asimov will ask you to confirm):

   .. code-block:: bash

      $ asimov analysis rerun spring-1 fit-constant

#. Run ``asimov monitor --chain --until-idle --interval 2`` again. Analyses which have already finished aren't repeated.

Asimov can also retry failed analyses for you: see :ref:`retry policies<retry-policy>`.

What's next?
------------

* **Analyse real data.** :doc:`tutorials/analysing-gw150914` uses the same ideas to analyse the first gravitational wave to be detected, on a computing cluster.
* **Write more complex workflows.** The :ref:`analysis guide<analysis-guide>` explains more about analyses, and :ref:`subject analyses<subject-analysis>` can combine results, updating themselves as new ones arrive.
* **Try many variations at once.** A blueprint with a ``strategy`` expands into one analysis for each combination of settings: see :ref:`strategies<strategies>`.
* **Share progress.** The :ref:`reporting guide<reporting-guide>` explains the web report.
* **Configure your project.** The :ref:`project guide<project-guide>` covers the project's layout and settings.
