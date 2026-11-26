When something goes wrong
=========================

Analyses fail: a file is missing, a computer misbehaves, or a blueprint asks for the wrong thing.
In this tutorial you'll break a workflow in a few different ways, find out what happened, and put it right.

.. rst-class:: tutorial-intro

:What you'll learn: How to find out why an analysis failed, run it again, replace one which has the wrong settings, update a subject safely, and retry failures automatically.
:Time required: About 20 minutes.
:Prerequisites: The project and programs you made in :ref:`Getting started<Getting Started>`.

Analyses don't change
---------------------

One idea explains much of what follows: **an analysis is designed to be immutable**.
Once you've added it to a project, its settings stay as they are.

This is what lets you say, later, exactly how a result was produced.
If you could edit an analysis after it had run, the record in the ledger would no longer describe the result sitting in its directory.

So there are two kinds of repair:

* If the problem is **outside the analysis**, such as a missing file, a bug in a program, or a fault on a computer, fix it and **run the same analysis again**.
* If the **analysis itself** is wrong, because its blueprint asks for the wrong thing, **add a new analysis**. The old one remains as part of the record.

.. rst-class:: procedural-step

Make something go wrong
-----------------------

You've been asked to analyse a second spring, whose measurements a colleague will put in a directory called ``measurements``.
Work in your ``asimov-tutorial`` directory, with the virtual environment active and the ``scripts`` directory on your ``PATH``.

This program fetches the measurements:

.. code-block:: python
   :caption: scripts/load_data.py

   #!/usr/bin/env python3
   """Fetch the measurements of a spring from the measurements directory."""
   import shutil
   import sys
   from pathlib import Path

   spring, output = sys.argv[1:]

   project = Path(__file__).resolve().parent.parent
   shutil.copy(project / "measurements" / f"{spring}.txt", output)

Make it executable:

.. code-block:: bash

   $ chmod +x scripts/load_data.py

Save a blueprint for the new spring, and one for its analyses:

.. code-block:: yaml
   :caption: spring-2.yaml

   kind: subject
   name: spring-2
   spring:
     material: steel

.. code-block:: yaml
   :caption: spring-2-analyses.yaml

   kind: analysis
   name: load-data
   command: [load_data.py, spring-2, "{outputs.data}"]
   outputs:
     data: data.txt
   ---
   kind: analysis
   name: fit-constant
   command: [fit.py, constant, "{inputs.data}"]
   outputs:
     fit: fit.txt
   needs:
     - load-data
   ---
   kind: analysis
   name: fit-line
   command: [fit.py, line, "{inputs.data}", "{outputs.fit}"]
   outputs:
     fit: fit.txt
   needs:
     - load-data

Before you apply a blueprint you can ask what it would do, without changing anything:

.. code-block:: bash

   $ asimov apply -f spring-2.yaml
   $ asimov apply -f spring-2-analyses.yaml -e spring-2 --dry-run

.. code-block:: text

   Dry run: nothing was written.
     + analysis spring-2/load-data (added)
     + analysis spring-2/fit-constant (added)
     + analysis spring-2/fit-line (added)

That's what you expected, so apply it and run the workflow.
Your colleague hasn't delivered the measurements yet, so this won't go well:

.. tutorial-test: may-fail

.. code-block:: bash

   $ asimov apply -f spring-2-analyses.yaml -e spring-2
   $ asimov monitor --chain --until-idle --interval 2

.. code-block:: text

   ● load-data is stuck; automatic rescue was not possible

.. rst-class:: procedural-step

Find out what happened
----------------------

Start with the status of the project:

.. code-block:: bash

   $ asimov report status

.. code-block:: text

   spring-2
   - load-data command stuck
   - fit-constant command ready
   - fit-line command ready

``load-data`` is ``stuck``: asimov couldn't finish it, and won't try again unless you ask.
The two fits are still ``ready``, waiting for the data.

Each analysis has a run directory, under ``working``, containing what its program printed.
The ``.err`` file holds the error messages:

.. tutorial-test: may-fail

.. code-block:: bash

   $ cat working/spring-2/load-data/load-data.err

.. code-block:: text

   FileNotFoundError: [Errno 2] No such file or directory:

The rest of that message names the file which is missing.
Two other places are worth knowing about:

* ``command.sh``, in the same directory, is the exact command asimov ran. You can run it yourself to reproduce a problem.
* ``logs/asimov.log`` records what asimov itself did, including any problem it had in building or submitting an analysis.

.. rst-class:: procedural-step

Fix it, and run it again
------------------------

The blueprint was right; the file just wasn't there.
Your colleague now delivers it:

.. code-block:: bash

   $ mkdir -p measurements
   $ make_data.py measurements/spring-2.txt

Ask asimov to make the analysis ready to run again.
With ``--dry-run`` it only says what it would do:

.. code-block:: bash

   $ asimov analysis rerun spring-2 load-data --dry-run

Without it, asimov asks you to confirm. The ``--yes`` option answers in advance:

.. code-block:: bash

   $ asimov analysis rerun spring-2 load-data --yes

.. tip::
   Add ``--downstream`` to run again everything which depends on the analysis too.
   You'd want that if it had finished, and others had already used its results.

Run the workflow:

.. tutorial-test: may-fail

.. code-block:: bash

   $ asimov monitor --chain --until-idle --interval 2

.. code-block:: text

   ● fit-constant is stuck; automatic rescue was not possible

The data arrived, and ``fit-line`` ran, but now ``fit-constant`` is stuck.

.. rst-class:: procedural-step

Replace a wrong analysis
------------------------

Look at the error:

.. tutorial-test: may-fail

.. code-block:: bash

   $ cat working/spring-2/fit-constant/fit-constant.err

.. code-block:: text

   ValueError: not enough values to unpack (expected 3, got 2)

This time the blueprint is wrong: the command for ``fit-constant`` doesn't say where to write the result.
Running it again would fail in the same way.

Save a corrected blueprint, with the same name:

.. code-block:: yaml
   :caption: fit-constant.yaml

   kind: analysis
   name: fit-constant
   command: [fit.py, constant, "{inputs.data}", "{outputs.fit}"]
   outputs:
     fit: fit.txt
   needs:
     - load-data

If you try to apply it, asimov refuses, because the analysis already exists:

.. tutorial-test: may-fail

.. code-block:: bash

   $ asimov apply -f fit-constant.yaml -e spring-2

.. code-block:: text

   ● Could not apply fit-constant to spring-2 as an analysis already exists with this name

You'll also see a Python error message after that line; the line itself is what matters.
The ``--update`` option doesn't change this: it updates subjects and project settings, but **never an existing analysis**.

Add the correction as a new analysis.
You could change the ``name`` yourself, or let ``--iterate`` pick the next free one:

.. code-block:: bash

   $ asimov apply -f fit-constant.yaml -e spring-2 --iterate

.. code-block:: text

   ● Successfully applied fit-constant-2 to spring-2

The old analysis is no use any more, so mark it ``cancelled``, and run the new one:

.. code-block:: bash

   $ asimov production set spring-2 fit-constant --status cancelled
   $ asimov monitor --chain --until-idle --interval 2
   $ asimov report status

.. code-block:: text

   spring-2
   - load-data command complete
   - fit-constant command cancelled
   - fit-line command complete
   - fit-constant-2 command complete

.. note::
   Analyses refer to each other by name.
   If something had needed ``fit-constant``, it would need replacing too, with a new analysis which needs ``fit-constant-2``.

.. rst-class:: procedural-step

Update a subject
----------------

Subjects are different: you often learn more about one, and need to correct it.
Suppose the spring turns out to be made of brass.
Change ``spring-2.yaml``:

.. code-block:: yaml
   :caption: spring-2.yaml

   kind: subject
   name: spring-2
   spring:
     material: brass

Preview the change, then make it with ``--update``:

.. code-block:: bash

   $ asimov apply -f spring-2.yaml --update --dry-run

.. code-block:: text

   spring.material: 'steel' -> 'brass'

.. code-block:: bash

   $ asimov apply -f spring-2.yaml --update
   $ asimov production show spring-2 fit-line

.. code-block:: text

   spring:
     material: steel

The subject has changed, but ``fit-line`` still says ``steel``, because that's what was true when it was run.
Analyses you add from now on will say ``brass``.

If some analyses haven't started yet, and *should* use the new settings, use ``--update-unstarted`` in place of ``--update``.
Analyses which are waiting to run then pick up the change; those which have started or finished keep what they had.
Choose when you make the change: once an analysis has been through a plain ``--update``, it keeps its old settings.

.. warning::
   Project-wide defaults, set with ``kind: configuration`` blueprints, don't yet follow this rule.
   Changing one can also change what existing analyses show, even those which have finished.
   This is `a known bug <https://github.com/etive-io/asimov/issues/341>`_.

.. rst-class:: procedural-step

Retry automatically
-------------------

Some failures go away by themselves, for example when a job lands on a faulty computer.
Rather than rerunning these by hand, you can give an analysis a *retry policy*.

This program imitates such a failure, by failing the first time it's run:

.. code-block:: python
   :caption: scripts/unreliable.py

   #!/usr/bin/env python3
   """Fail the first time, like a job which landed on a faulty computer."""
   import sys
   from pathlib import Path

   output = Path(sys.argv[1])
   marker = Path("tried-before")

   if not marker.exists():
       marker.touch()
       sys.exit("Something went wrong. It may work next time.")

   output.write_text("It worked.\n")

.. code-block:: yaml
   :caption: unreliable.yaml

   kind: analysis
   name: unreliable
   command: [unreliable.py, "{outputs.result}"]
   outputs:
     result: result.txt
   retry:
     attempts: 3
     delay: 2

``attempts`` is the most times the analysis may be run, and ``delay`` is how many seconds to wait before trying again.
Run it:

.. code-block:: bash

   $ chmod +x scripts/unreliable.py
   $ asimov apply -f unreliable.yaml -e spring-2
   $ asimov monitor --chain --until-idle --interval 2
   $ cat working/spring-2/unreliable/result.txt

.. code-block:: text

   It worked.

A program which runs and fails is, by default, tried at most twice, since a third attempt is unlikely to help.
The :ref:`retry policy reference<retry-policy>` explains how to change that, and how to let a workflow continue past an analysis which never succeeds.

.. rst-class:: procedural-step

Check the record
----------------

Everything you did to the project has been recorded, including the analyses you ran again:

.. code-block:: bash

   $ asimov audit show

On a computing cluster
----------------------

The same steps apply when your jobs run on a cluster, with a few differences:

* Logs are still in each analysis's run directory, though pipelines may keep them in subdirectories of it.
* Asimov also marks an analysis ``stuck`` if the scheduler puts its job on hold. The scheduler's own tools will say why.
* An analysis which is running can't be run again until you've stopped it: ``asimov production set <subject> <analysis> --status stop``.
* Some pipelines write a configuration file when an analysis is built, and running it again reuses that file.

What's next?
------------

* :doc:`The monitor reference <../monitor-state-machine>` describes every state an analysis can be in, and what asimov does in each.
* :doc:`The blueprint guide <../blueprints>` explains which settings take priority.
