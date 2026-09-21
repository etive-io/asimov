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
