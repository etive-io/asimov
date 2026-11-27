Scaling up
==========

Asimov is most useful when there are too many analyses to look after by hand.
In this tutorial you'll survey a set of springs: add them all at once, fit two models to each, combine the results, and tidy up afterwards.

.. rst-class:: tutorial-intro

:What you'll learn: How to add many subjects at once, make many analyses from one blueprint, limit how fast they're submitted, combine results from different subjects, and release data you no longer need.
:Time required: About 20 minutes.
:Prerequisites: :ref:`Getting started<Getting Started>` and :doc:`adding-a-pipeline`, whose project, programs and ``springfit`` pipeline you'll use.

Work in your ``asimov-tutorial`` directory, with the virtual environment active and the ``scripts`` directory on your ``PATH``.

.. rst-class:: procedural-step

Write blueprints with a program
-------------------------------

You have three new springs, and each needs a subject and an analysis which collects its measurements.
Writing those blueprints out by hand would soon become tedious, but blueprints are only YAML, so a program can write them.

First, a program to simulate the measurements of a spring which stretches by a given amount for each unit of load:

.. code-block:: python
   :caption: scripts/simulate.py

   #!/usr/bin/env python3
   """Simulate noisy measurements of a spring."""
   import random
   import sys

   output, stretch = sys.argv[1], float(sys.argv[2])

   random.seed(stretch)
   with open(output, "w") as handle:
       for load in range(1, 21):
           extension = 2.0 + stretch * load + random.gauss(0, 0.3)
           handle.write(f"{load} {extension:.3f}\n")

Then a program which writes the blueprints for all of the springs:

.. code-block:: python
   :caption: scripts/make_survey.py

   #!/usr/bin/env python3
   """Write the blueprints for every spring in the survey."""

   SPRINGS = {"spring-a": 0.4, "spring-b": 0.5, "spring-c": 0.7}

   documents = []
   for name, stretch in SPRINGS.items():
       documents.append(f"""\
   kind: subject
   name: {name}
   """)
       documents.append(f"""\
   kind: analysis
   event: {name}
   name: make-data
   command: [simulate.py, "{{outputs.data}}", "{stretch}"]
   outputs:
     data:
       path: data.txt
       retention: until_consumed
   """)

   print("---\n".join(documents))

Each analysis says which subject it belongs to with ``event``, so one file can describe all of them.
The ``retention`` setting says that the data may be thrown away once everything which needs it has finished; you'll come back to that.

Run the program, and ask asimov what applying its blueprints would do:

.. code-block:: bash

   $ chmod +x scripts/simulate.py scripts/make_survey.py
   $ make_survey.py > survey.yaml
   $ asimov apply -f survey.yaml --dry-run

.. code-block:: text

   + event spring-a (added)
   + analysis spring-a/make-data (added)

It looks right, so apply it:

.. code-block:: bash

   $ asimov apply -f survey.yaml

.. rst-class:: procedural-step

Make many analyses from one blueprint
-------------------------------------

You want to fit both models to every spring.
A blueprint with a *strategy* describes several analyses at once: one for each value in a list.
Save this as ``fits.yaml``:

.. code-block:: yaml
   :caption: fits.yaml

   kind: analysis
   name: survey-{springfit.model}
   pipeline: springfit
   campaign: survey
   needs:
     - make-data
   strategy:
     springfit.model:
       - constant
       - line

The ``strategy`` names a setting, and the values it should take.
``{springfit.model}`` in the name is replaced by each value, so that every analysis has a different name.
``campaign`` is a label of your own, which you'll use to find these analyses again.

Apply it to each of the springs:

.. code-block:: bash

   $ for spring in spring-a spring-b spring-c; do asimov apply -f fits.yaml -e $spring; done

.. code-block:: text

   ● Successfully applied survey-constant to spring-a
   ● Successfully applied survey-line to spring-a

A strategy can list more than one setting, and then makes an analysis for every combination of their values.
In gravitational wave astronomy this is a common way to analyse an event with several waveform models and samplers.

.. rst-class:: procedural-step

Run them a few at a time
------------------------

A large set of analyses can overwhelm a scheduler, or the people who share it.
You can limit how many asimov submits in each cycle:

.. code-block:: bash

   $ asimov configuration update scheduler/max_submit_per_pass 2
   $ asimov monitor --chain --until-idle --interval 2

.. code-block:: text

   submission limit reached

Asimov defers whatever doesn't fit, and picks it up in a later cycle.
The limit is a project setting, so it applies from now on, until you change it.
You can also limit the number of jobs which are waiting or running at once: see :doc:`the configuration guide <../configuration>`.

.. rst-class:: procedural-step

Keep track
----------

``asimov analysis list`` shows every analysis in the project, and counts them by status:

.. code-block:: bash

   $ asimov analysis list

.. code-block:: text

   spring-a/make-data  complete
   spring-a/survey-constant  complete
   spring-a/survey-line  complete

For a large project the web report, from ``asimov report html``, is easier to search.

.. rst-class:: procedural-step

Combine the results
-------------------

Now collect the straight-line fits from every spring into one table.
This analysis belongs to no particular spring, so give it a subject of its own.

.. code-block:: python
   :caption: scripts/summarise.py

   #!/usr/bin/env python3
   """Tabulate the fits of many springs."""
   import sys
   from pathlib import Path

   output, *fits = sys.argv[1:]

   rows = []
   for fit in map(Path, fits):
       spring = fit.parent.parent.name  # .../working/<spring>/<analysis>/fit.txt
       model, scatter = fit.read_text().split()
       rows.append(f"{spring} {model} {scatter}\n")

   with open(output, "w") as handle:
       handle.writelines(sorted(rows))

.. code-block:: yaml
   :caption: summary.yaml

   kind: subject
   name: survey
   ---
   kind: analysis
   event: survey
   name: summary
   command: [summarise.py, "{outputs.table}", "{inputs.fit}"]
   outputs:
     table: summary.txt
   needs:
     - - subject: "*"
       - campaign: survey
       - springfit.model: line

So far ``needs`` has named other analyses of the same subject.
This one *selects* analyses instead: from every subject (``"*"``), those which are part of the survey **and** fit a straight line.
The two dashes begin a group of conditions which must all be true.

.. code-block:: bash

   $ chmod +x scripts/summarise.py
   $ asimov apply -f summary.yaml
   $ asimov monitor --chain --until-idle --interval 2
   $ cat working/survey/summary/summary.txt

.. code-block:: text

   spring-a line
   spring-b line
   spring-c line

.. rst-class:: procedural-step

Add to the survey
-----------------

A fourth spring turns up.
Add it, and its analyses, in the same way:

.. code-block:: yaml
   :caption: spring-d.yaml

   kind: subject
   name: spring-d
   ---
   kind: analysis
   event: spring-d
   name: make-data
   command: [simulate.py, "{outputs.data}", "0.9"]
   outputs:
     data:
       path: data.txt
       retention: until_consumed

.. code-block:: bash

   $ asimov apply -f spring-d.yaml
   $ asimov apply -f fits.yaml -e spring-d
   $ asimov monitor --chain --until-idle --interval 2

The summary has already finished, so it doesn't include the new spring.
Its blueprint doesn't need to change, because the selection now matches one more analysis; run it again:

.. code-block:: bash

   $ asimov analysis rerun survey summary --yes
   $ asimov monitor --chain --until-idle --interval 2
   $ cat working/survey/summary/summary.txt

.. code-block:: text

   spring-a line
   spring-b line
   spring-c line
   spring-d line

.. rst-class:: procedural-step

Tidy up
-------

The measurements have served their purpose.
See how much space the analyses are using, and what asimov could release:

.. code-block:: bash

   $ asimov analysis du
   $ asimov analysis prune --dry-run

Release it:

.. code-block:: bash

   $ asimov analysis prune --yes
   $ ls working/spring-a/make-data

Asimov only releases outputs which are marked ``until_consumed``, and only once every analysis which needs them has finished.
It records what it removed.

.. warning::
   Released data are gone.
   To run again anything which used them, use ``asimov analysis rerun`` with ``--regenerate``, which also reruns whatever made them.

What's next?
------------

* :doc:`results-to-release` shows how to check results, and share them with a record of how they were made.
* :ref:`Strategies<strategies>` can also be written as plugins, which make whole sets of subjects and analyses, with dependencies between them, from a single blueprint.
* :ref:`Subject analyses<subject-analysis>` combine the results of one subject, and can update themselves as new results arrive.
* The reference guides describe :ref:`retention<retention>` and :doc:`submission limits <../configuration>` in full.
