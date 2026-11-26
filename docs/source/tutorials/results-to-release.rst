From results to release
=======================

A result isn't ready to share just because the job finished.
Someone needs to check it, and whoever receives it should be able to find out how it was made.
In this tutorial you'll review the spring fits, release the ones which pass, and package the release with a record of its history.

.. rst-class:: tutorial-intro

:What you'll learn: How to record reviews, build a release from approved results only, keep the files safely, and export a record of how they were made.
:Time required: About 20 minutes.
:Prerequisites: The project and programs you made in :ref:`Getting started<Getting Started>`.

Work in your ``asimov-tutorial`` directory, with the virtual environment active and the ``scripts`` directory on your ``PATH``.

.. rst-class:: procedural-step

Review the results
------------------

Look at what the two fits found:

.. code-block:: bash

   $ cat working/spring-1/fit-line/fit.txt
   $ cat working/spring-1/fit-constant/fit.txt

.. code-block:: text

   line 0.286
   constant 2.918

The straight line describes the data far better.
Record that judgement with ``asimov review add``, giving the subject, the analysis, a verdict, and your reason:

.. code-block:: bash

   $ asimov review add spring-1 fit-line approved --message "Describes the data well"
   $ asimov review add spring-1 fit-constant rejected --message "A spring is not a constant"

The verdict is one of ``approved``, ``preferred``, ``rejected`` or ``deprecated``.
To see where everything stands:

.. code-block:: bash

   $ asimov review status spring-1

.. code-block:: text

   fit-constant
   rejected
   fit-line
   approved

Reviews are added to an analysis, and never replace one another: the most recent verdict is the one which counts, and the earlier ones remain as its history.
The web report, from ``asimov report html``, shows them too.

.. note::
   In a project of your own you can approve your own work.
   A shared project can insist that someone else does it: see :doc:`the project registry <../registry>`.

.. rst-class:: procedural-step

Release only what was approved
------------------------------

Your release will be a single table of the fits which passed review.
This program makes it:

.. code-block:: python
   :caption: scripts/collect.py

   #!/usr/bin/env python3
   """Gather fits into one table."""
   import sys
   from pathlib import Path

   output, *fits = sys.argv[1:]

   Path(output).write_text("".join(Path(fit).read_text() for fit in fits))

Rather than naming the analyses it uses, the blueprint asks for every analysis which has been approved:

.. code-block:: yaml
   :caption: release.yaml

   kind: analysis
   name: release
   command: [collect.py, "{outputs.table}", "{inputs.fit}"]
   outputs:
     table: release.txt
   needs:
     - review: approved

Apply it and run it:

.. code-block:: bash

   $ chmod +x scripts/collect.py
   $ asimov apply -f release.yaml -e spring-1
   $ asimov monitor --chain --until-idle --interval 2
   $ cat working/spring-1/release/release.txt

.. code-block:: text

   line 0.286

Only the approved fit is included.

.. note::
   Review something before you apply an analysis like this.
   While nothing matches, asimov can't build it, and reports an error each time it tries.

.. rst-class:: procedural-step

When a review changes
---------------------

A colleague argues that the constant model belongs in the release, as a comparison:

.. code-block:: bash

   $ asimov review add spring-1 fit-constant approved --message "Keep it for comparison"

The release you've already made doesn't change: it records what was approved when it ran.
Rather than running it again, which would overwrite a table you may already have shared, make a second release from the same blueprint:

.. code-block:: bash

   $ asimov apply -f release.yaml -e spring-1 --iterate
   $ asimov monitor --chain --until-idle --interval 2
   $ cat working/spring-1/release-2/release.txt

.. code-block:: text

   constant 2.918
   line 0.286

Now say which release people should use:

.. code-block:: bash

   $ asimov review add spring-1 release-2 preferred --message "Use this one"
   $ asimov review add spring-1 release deprecated --message "Replaced by release-2"

.. rst-class:: procedural-step

Keep the files
--------------

Run directories are working space, and things in them can be overwritten or cleaned away.
Asimov has a *results store* for files you want to keep, which notes a checksum of each one so that you can tell later whether it has changed.

For a ``command`` analysis you add the files yourself, with the ``locutus`` program, from inside the store's directory.
Keep four things: the result, the exact command which made it, and the two files describing the software it ran with.

.. code-block:: bash

   $ cd results
   $ locutus store spring-1 release-2 ../working/spring-1/release-2/release.txt
   $ locutus store spring-1 release-2 ../working/spring-1/release-2/command.sh
   $ locutus store spring-1 release-2 ../.asimov/environments/spring-1/release-2/environment.json
   $ locutus store spring-1 release-2 ../.asimov/environments/spring-1/release-2/environment-pip.txt
   $ cd ..

Check what's there:

.. code-block:: bash

   $ asimov production results spring-1 release-2

.. code-block:: text

   release.txt

.. rst-class:: procedural-step

Package the record
------------------

``asimov package`` gathers the history of an analysis into an `RO-Crate <https://www.researchobject.org/ro-crate/>`_, a standard way of describing research data:

.. code-block:: bash

   $ asimov package spring-1 release-2 --output release-2.crate
   $ ls release-2.crate

.. code-block:: text

   audit.json
   config.json
   environment
   provenance.json
   ro-crate-metadata.json

``config.json``
   The analysis's settings, including its reviews.
``environment``
   The software it ran with. It's included because you added those two files to the results store.
``provenance.json``
   The settings, the run, the software involved and the stored files, in the W3C PROV format.
``audit.json``
   Who changed the analysis and its subject, and when.
``ro-crate-metadata.json``
   The description which ties these together. It lists the files in the results store, with their checksums.

.. warning::
   The crate describes your results, but doesn't contain them: send the files from the results store along with it.

   It also doesn't yet list which analyses went into the release.
   ``command.sh`` names the files which did, which is one reason to keep it.

.. rst-class:: procedural-step

Check the history
-----------------

Finally, asimov can tell you who did what, and when.
To see when the release was added:

.. code-block:: bash

   $ asimov audit show --target spring-1/release-2

.. code-block:: text

   apply analysis (added) spring-1/release-2

Reviews are recorded as changes to the subject.
Your two most recent changes were the last two reviews; ask for the full records to see which analyses they changed, and how:

.. code-block:: bash

   $ asimov audit show --target spring-1 --limit 2 --format json

.. code-block:: text

   "analyses.release-2.meta.review": [
   "analyses.release.meta.review": [

Leave out ``--limit`` to see the whole history of the subject, which includes the changes asimov made while running your analyses.

What's next?
------------

* :ref:`Provenance and RO-Crate<provenance>` describes the record in detail.
* :doc:`The review guide <../user-guide/review>` covers reviews further, and :ref:`subject analyses<subject-analysis>` can keep a combination of approved results up to date.
* :doc:`The audit trail <../audit>` explains what's recorded, and how to search it.
