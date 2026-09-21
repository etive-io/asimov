Monitoring Analyses
===================

``asimov monitor`` checks the status of running jobs on the scheduler, updates the ledger to reflect
completions/failures, and triggers post-completion processing. It works with either scheduler backend
(HTCondor or Slurm, per ``[scheduler] type`` — see :doc:`/scheduler-integration`).

.. code-block:: console

   $ asimov monitor              # check every event
   $ asimov monitor GW150914     # check a single event
   $ asimov monitor --dry-run    # report what would happen, without changing the ledger
   $ asimov monitor --update     # pull each event's git repository before checking

See :doc:`/monitor-state-machine` for how each analysis status is handled internally, and
:doc:`/monitor-api` for a Python API you can call ``run_monitor()`` from directly (HTCondor-only
at present).

Refreshable analyses
---------------------

A :doc:`subject analysis <../analyses>` marked ``refreshable: true`` is automatically re-run by the
monitor whenever the set of analyses it depends on changes — for example, a PESummary job can pick up
and re-summarise a new bilby run without you needing to re-apply anything.

Running the monitor continuously
-----------------------------------

Rather than invoking ``asimov monitor`` by hand, you can run it as a recurring job:

.. code-block:: console

   $ asimov start   # set up a recurring monitor job (an HTCondor cron job, or a system cron
                     # entry for Slurm projects)
   $ asimov stop     # remove it

Both commands accept ``--dry-run``/``-n`` to show what would be configured without changing anything,
and an experimental ``--use-scheduler-api`` flag to drive the scheduler through its API rather than the
command-line tools.
