Asimov configuration options
============================

Each asimov project has a configuration file, ``.asimov/asimov.conf``, in the standard ``ini`` format.
``asimov init`` creates it with sensible defaults (and auto-detects your scheduler); this page is a
reference for the sections you're most likely to want to change by hand.

``[general]``
--------------

General project settings.

``webroot``
   The directory (relative to the project root) that HTML reports are written to. Defaults to ``pages/``.

``rundir_default``
   The default parent directory for analysis run directories, set by ``asimov init --working``. Defaults to ``working``.

``git_default``
   The default parent directory that subjects' git repositories are cloned into, set by ``asimov init --checkouts``. Defaults to ``checkouts``.

``[ledger]``
-------------

Selects and configures the ledger backend. See :doc:`ledger` for the full comparison between backends.

``engine``
   ``yamlfile`` (the default), ``tinydb``, or ``mongodb``.

``location``
   Path to the ledger file/database, relative to the project root. Defaults to ``.asimov/ledger.yml`` for
   the ``yamlfile`` engine.

``[storage]``
--------------

``directory``
   The location of the project's results store, set by ``asimov init --results``. See
   :doc:`user-guide/projects` for how to relocate it after project creation.

``[scheduler]``
-----------------

``type``
   Which scheduler backend to use: ``htcondor`` or ``slurm``. Auto-detected by ``asimov init``; see
   :doc:`scheduler-integration` for the full configuration reference for both, including the
   scheduler-specific ``[condor]`` and ``[slurm]`` sections.

``max_queued``
   The maximum number of analyses from this project which may be running (or processing) at once.
   ``asimov manage submit`` leaves any further ready analyses to a later pass. HTCondor schedds only
   cope with a limited number of DAGs, so set this well below that limit. Unset or ``0`` means no limit.

``max_submit_per_pass``
   The maximum number of analyses a single ``asimov manage submit`` (or ``asimov monitor --chain``) will
   submit. May be overridden with ``asimov manage submit --max-submit N``. Unset or ``0`` means no limit.
   ``asimov monitor --chain`` may run submit more than once in a pass; the limit is shared by all of the runs.

``submit_interval``
   Seconds to wait between consecutive submissions. Defaults to ``0``.

For example, to keep at most 200 analyses in the queue::

   [scheduler]
   max_queued = 200
   max_submit_per_pass = 20
   submit_interval = 2

Analyses which are deferred stay ``ready``, and are picked up by the next pass. If the scheduler rejects
a submission because it is busy, the pass stops and the analysis is left ready rather than being marked
``stuck``. Submissions are never retried within a pass, because a request which timed out may still have
been accepted, and retrying it would queue a duplicate DAG. The number of active analyses is counted from the ledger, so a finished analysis only frees
its slot once ``asimov monitor`` has recorded that it finished.

``[general]``: event repositories
-----------------------------------

``event_git``
   Whether a git repository is created and updated for every event. Defaults to ``false``. Files are
   still written into each event's directory, but nothing is initialised, committed or pulled. Set this
   to ``true`` if you keep your event files under version control; creating and updating a repository
   for every event is slow on a large project (on the order of 0.1 s per event the first time, then
   about 25 ms per event on each ``manage build``). Repositories which are given an explicit URL are
   still cloned.

   Projects made with asimov 0.8 or earlier created these repositories without being asked. If you rely
   on them, add ``event_git = true`` to the ``[general]`` section of ``.asimov/asimov.conf``.

``[condor]`` / ``[slurm]``
----------------------------

Scheduler-specific settings (accounting user, partition, job-status cache time, monitor cron frequency).
See :doc:`clusters` and :doc:`scheduler-integration` for the full set of options.

``[templating]``
------------------

``directory``
   The directory (relative to the project root) that pipeline configuration templates are read from.
   See :doc:`config` for how templating works.

``[pipelines]``
-----------------

``environment``
   The default software environment (e.g. a conda environment path) used when submitting pipeline jobs,
   where a pipeline doesn't specify its own.

``[gracedb]``
--------------

``url``
   The GraceDB API endpoint used by the optional ``asimov-gracedb`` plugin. See :doc:`gracedb`.

``[mattermost]``
------------------

Configuration for optional Mattermost notifications.

``[theme]``
------------

``name``
   The HTML report theme to use. See :doc:`user-guide/reporting`.
