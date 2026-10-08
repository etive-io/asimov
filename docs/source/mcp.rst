MCP server
==========

``asimov mcp-server`` lets an AI agent, or any other client which speaks the
`Model Context Protocol <https://modelcontextprotocol.io>`_, inspect a project and
apply blueprints to it. It needs the ``mcp`` package:

.. code-block:: console

    $ pip install 'asimov[mcp]'

Add it to an MCP client (for example Claude Code) as a command which runs in the
project's directory:

.. code-block:: console

    $ claude mcp add asimov -- asimov mcp-server --project /path/to/project

Use ``--read-only`` to offer only the tools which read the project, and
``--acting-for NAME`` to say which person the client acts for (the default is the
local user).

Tools
-----

Everything is described in terms of *subjects* (what analyses are of: for
gravitational-wave work, events).

``list_subjects``, ``get_subject``
    The project's subjects, and one subject's settings and analyses.
``list_analyses``, ``get_analysis``
    Analyses across the project (filter by subject, status or pipeline) and
    everything the ledger holds about one.
``get_analysis_logs``, ``get_analysis_telemetry``
    The end of an analysis's log files, and the telemetry events it recorded.
``get_review_status``, ``list_labels``
    An analysis's review status and messages, and the labels on analyses.
``set_review_status``, ``add_comment``
    Give an analysis a review status (with a message if wanted), or add a
    comment. A comment is a review message without a status, as ``asimov review add``
    makes: it shows in ``get_review_status`` and does not change the status.
``add_label``, ``remove_label``
    Set a label on an analysis, and remove one. A label set this way is *manual*:
    it stays until it is removed, and labellers (see :doc:`labeller-plugins`) never
    change it, even if they set a label with the same name.
``trigger_build``, ``trigger_submit``
    Build the configuration for ready analyses, and submit them to the scheduler.
    Both return at once with a *job* (see below). ``trigger_submit`` takes the
    ``dryrun`` and ``max_submit`` options of ``asimov manage submit``.
``get_job``, ``list_jobs``
    How a job is getting on, what it did, and the end of what it printed; and the
    recent jobs. These only read the job's record, so they are quick however busy
    the scheduler is, and are available with ``--read-only``.
``preview_blueprint``
    What applying a blueprint would do, and what would be refused. Changes
    nothing (see :doc:`blueprints`).
``apply_blueprint``
    Apply a blueprint. Returns what was changed and what was refused.

Each of these changes is recorded in the :doc:`audit log <audit>` (kinds ``review``
and ``label``), in the same transaction as the change. ``--read-only`` leaves out
every tool which changes anything. Only ``remove_label`` removes anything: it is
marked as destructive so that clients can ask first.

Lists are paged (``limit`` and ``offset``), and log and telemetry results are
capped, so a large project cannot flood the client. There is no tool which deletes
an analysis, a subject or a record.

Build and submit jobs
---------------------

Submitting talks to the scheduler, which can be slow, and submissions are paced
(``submit_interval``), so a tool call which waited for it could hang the client,
and a client which retried could submit twice. ``trigger_build`` and
``trigger_submit`` therefore start a separate worker process
(``python -m asimov.jobs run``), which does what ``asimov manage build`` or
``asimov manage submit`` does, and return straight away with the job's id.

A job is a file in the project, ``.asimov/jobs/<id>.json``, with its status
(``queued``, ``running``, ``succeeded`` or ``failed``), who it runs as, when it
started and finished, what it did (for submit, how many analyses it submitted)
and why it failed, if it did. What it printed is in ``<id>.log``.

* **One at a time.** Only one job runs in a project at once: a second
  ``trigger_*`` while one runs is refused, and the error names the running job.
* **Scheduler limits still apply.** The ``[scheduler]`` settings ``max_queued``,
  ``max_submit_per_pass`` and ``submit_interval`` work in the worker as they do
  on the command line. By default they set no limit, so
  ``trigger_submit`` without a ``subject`` submits every ready analysis in the
  project: set ``max_submit_per_pass`` if you give an agent this tool.
* **Time limit.** A worker is stopped after an hour, and the job is marked as
  failed.
* **Dead workers.** If a worker is killed, or the machine restarts, the job is
  marked as failed the next time it is read, and the project can run jobs again.
* **Audited.** Starting a job is recorded in the :doc:`audit log <audit>` (kind
  ``job``), under the agent and the person it acts for. The worker runs as them
  too.

Who did it
----------

Each call runs as an *agent* :doc:`principal <principals>` named after the MCP client,
acting for the person who started the server. Applying a blueprint through the
server is recorded in the :doc:`audit log <audit>` under both names, so
``asimov audit show --principal NAME`` finds what an agent did on someone's behalf.

Threat model
------------

The server reads and writes the project directly, as the command line does, and
speaks only over standard input and output to the process which started it. There
is no network listener and no authentication: **whoever can run the server can do
everything it offers, as the user who runs it.** It adds no privileges, and it does
not decide whether a client should be trusted. Use ``--read-only`` for clients you
want to look but not touch, and use ``preview_blueprint`` before ``apply_blueprint``.

Logs, review messages and settings can contain text written by other people or
jobs. The server marks such text with ``<untrusted-data>`` tags and says in its
instructions that it is data, not instructions. That reduces the chance that a model
follows an instruction hidden in a log, but it cannot prevent it, so do not give an
agent applying rights over a project whose logs you do not trust.

An MCP server cannot ask questions, so a blueprint which would make asimov prompt
(for example an analysis which does not say which subject it is for) is refused with
an error instead.
