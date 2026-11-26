.. _python-api-tutorial:

Using the Python API
====================

This tutorial drives the same GW150914 workflow as :doc:`analysing-gw150914`
— ``gwdata`` fetches data products, ``bayeswave`` estimates the noise PSD,
``bilby`` performs parameter estimation, and ``PESummary`` summarises the
results — but from Python instead of the command line. It reuses exactly the same blueprints and real pipelines as
that tutorial; nothing here is a toy or CI-only substitute. Driving asimov
from Python is useful for notebooks, for scripting the same workflow across
many events, and for custom automation that the CLI doesn't cover directly.

By the end you will know how to:

* Create and load a project from Python
* Apply blueprints programmatically with :func:`~asimov.cli.application.apply_page`
* Inspect analysis status from Python
* Build, submit and monitor analyses from a script, and scale a workflow across several events

Prerequisites
-------------

The same software and computing environment as :doc:`analysing-gw150914`:
follow its first step to install everything.

It's worth reading that tutorial first — this one assumes the same setup and
doesn't re-explain what each pipeline does.

Step 1 — Create a project
--------------------------

.. code-block:: python

   from asimov.project import Project

   project = Project(
       name="API Tutorial",
       location="/tmp/api-tutorial"
   )
   print(project)
   # <Project 'API Tutorial' at /tmp/api-tutorial>

This creates the same directory structure as ``asimov init``:

.. code-block:: text

   /tmp/api-tutorial/
   ├── .asimov/
   │   ├── asimov.conf
   │   └── ledger.db
   ├── working/
   ├── checkouts/
   ├── results/
   └── logs/

.. note::
   If the directory already contains a project, ``Project()`` raises ``RuntimeError``.
   Load existing projects with :meth:`~asimov.project.Project.load` instead.

Step 2 — Apply the project defaults and the event
---------------------------------------------------

All mutating operations must happen inside a ``with project:`` block, which
``chdir``\ s into the project directory and saves the ledger atomically when
the block exits without error.

The Python equivalent of ``asimov apply -f <file>`` is
:func:`~asimov.cli.application.apply_page`. It accepts a local path or a URL
and handles event, analysis, and configuration blueprints the same way the
CLI does — it *is* what the CLI calls. We use it here to apply the same
project-wide defaults and the same GW150914 event blueprint as
:doc:`analysing-gw150914`:

.. code-block:: python

   from asimov.cli.application import apply_page

   with project:
       apply_page(
           "https://git.ligo.org/asimov/data/-/raw/gwosc/defaults/production-pe.yaml",
           ledger=project.ledger,
       )
       apply_page(
           "https://git.ligo.org/asimov/data/-/raw/main/defaults/production-pe-priors.yaml",
           ledger=project.ledger,
       )
       apply_page(
           "https://git.ligo.org/asimov/data/-/raw/gwosc/events/gwtc-2-1/GW150914_095045.yaml",
           ledger=project.ledger,
       )

   for event in project.get_event():
       print(event.name)
   # GW150914_095045

.. note::
   Pass ``ledger=project.ledger`` explicitly, not a separately-obtained
   ledger (e.g. from :func:`~asimov.cli.application.get_ledger`). ``with
   project:`` only saves ``project.ledger`` on exit — mutating any other
   ledger object inside the block is silently lost when the block ends.

Step 3 — Apply the analysis workflow
--------------------------------------

Write the same four-stage workflow blueprint as :doc:`analysing-gw150914`
(``get-data`` → ``generate-psd`` → ``bilby-IMRPhenomXPHM`` →
``summary-pages``) and apply it with
:func:`~asimov.cli.application.apply_page`, passing ``event=`` the way you'd
pass ``-e`` on the command line:

.. code-block:: python

   import os

   workflow = """\
   kind: analysis
   name: get-data
   pipeline: gwdata
   file length: 4096
   download:
     - frames
   scheduler:
     accounting group: ligo.dev.o4.cbc.pe.bilby
     request memory: 1024
     request post memory: 16384
     request disk: 2048MB
   ---
   kind: analysis
   name: generate-psd
   pipeline: bayeswave
   comment: Bayeswave on-source PSD estimation process
   needs:
     - get-data
   ---
   kind: analysis
   name: bilby-IMRPhenomXPHM
   pipeline: bilby
   waveform:
     approximant: IMRPhenomXPHM
   comment: PE job using IMRPhenomXPHM and bilby
   needs:
     - generate-psd
   ---
   kind: analysis
   name: summary-pages
   pipeline: pesummary
   comment: Summary pages for the bilby results
   analyses:
     - pipeline: bilby
   refreshable: true
   """

   workflow_file = os.path.join(project.location, "workflow.yaml")
   with open(workflow_file, "w") as f:
       f.write(workflow)

   with project:
       apply_page(workflow_file, event="GW150914_095045", ledger=project.ledger)

Step 4 — Inspect the project
------------------------------

Load the project back (or keep the existing object) and inspect the event
and its analyses:

.. code-block:: python

   project = Project.load("/tmp/api-tutorial")

   for event in project.get_event():
       print(f"\n{event.name}")
       for prod in event.productions:
           # prod.pipeline is the instantiated Pipeline object, not a string —
           # asimov itself uses .name.lower() when it needs the identifier back
           # (see Production.to_dict()).
           pipeline_name = prod.pipeline.name.lower()
           print(f"  {prod.name:25s}  pipeline={pipeline_name:10s}  status={prod.status}")

Typical output::

   GW150914_095045
     get-data                   pipeline=gwdata      status=ready
     generate-psd               pipeline=bayeswave   status=ready
     bilby-IMRPhenomXPHM        pipeline=bilby       status=ready
     summary-pages              pipeline=pesummary   status=ready

All four start as ``ready`` — asimov's dependency system decides *when* an
analysis is actually eligible to be submitted based on its ``needs`` (or, for
``summary-pages``, its ``analyses``), it doesn't pre-block the stored status.

Step 5 — Build, submit and monitor
-----------------------------------

The Python equivalents of ``asimov manage build`` and ``asimov manage submit``
are :func:`~asimov.cli.manage.build_analyses` and
:func:`~asimov.cli.manage.submit_analyses`. Call them inside ``with project:``
blocks to start whatever is ready:

.. code-block:: python

   from asimov.cli.manage import build_analyses, submit_analyses

   with project:
       build_analyses()

   with project:
       submit_analyses()

To check on the jobs which have been submitted, use
:func:`~asimov.monitor_api.run_monitor`:

.. code-block:: python

   from asimov.monitor_api import run_monitor

   with project:
       results = run_monitor(verbose=True)

``run_monitor()`` only monitors: it doesn't build or submit the analyses which
become ready as others finish. Run the three calls again to move the workflow
on, or let asimov do it for you by running ``asimov start`` in the project
directory:

.. code-block:: console

   $ cd /tmp/api-tutorial
   $ asimov start

.. note::
   Submitting and monitoring need the same real HTCondor scheduler access as
   the command line. As with :doc:`analysing-gw150914`, expect the ``bilby``
   parameter-estimation stage to take on the order of a day; you don't need to
   keep a script running for that.

Step 6 — Scaling to multiple events
--------------------------------------

This is where scripting the API pays off over typing individual CLI
commands: apply the same workflow blueprint to every event already known to
the project with a single loop, instead of running ``asimov apply`` once per
event by hand.

.. code-block:: python

   with project:
       for event in project.get_event():
           apply_page(workflow_file, event=event.name, ledger=project.ledger)

Add more events first (with more ``apply_page`` calls against event
blueprints, exactly as in Step 2) and this loop picks all of them up
automatically — a natural way to run the same analysis across a batch of
events, or to build tooling on top of asimov rather than driving it by hand.

The loop is safe to run even when some events (like ``GW150914_095045``
from Step 3) already have this workflow applied: ``apply_page`` refuses to
create a second production with the same name for an event it's already
attached to. You'll see a red status line reporting the skip for those
events rather than a duplicate or corrupted analysis — it does not raise an
exception, so a script can loop over every known event unconditionally
without checking first.

See :doc:`/pipelines/bilby` for a full reference of bilby blueprint settings.

See also
--------

* :doc:`analysing-gw150914` — the CLI walkthrough this tutorial mirrors
* :doc:`/python-api` — Python API reference
* :doc:`/blueprints` — Full blueprint YAML format
* :doc:`/pipelines/bilby` — Bilby pipeline settings
* :doc:`/monitor-api` — ``run_monitor()`` API reference
