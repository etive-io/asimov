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

Use ``--read-only`` to offer only the tools which read the project,
``--registry FILE`` to serve several projects (see `Several projects`_), and
``--acting-for NAME`` to say which person the client acts for (the default is the
local user).

Tools
-----

Everything is described in terms of *subjects* (what analyses are of: for
gravitational-wave work, events).

``list_projects``
    The projects you can use (see `Several projects`_).
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
``list_plugins``
    What is installed which a blueprint can name: pipelines (``pipeline:``),
    analysis types (``type:``), subject types and strategies, each with the package
    which provides it, and the labellers and telemetry sinks. It describes the
    server's installation, not a project, so it is the one tool (with
    ``list_projects``) which takes no ``project``.
``preview_blueprint``
    What applying a blueprint would do, and what would be refused. Changes
    nothing (see :doc:`blueprints`).
``apply_blueprint``
    Apply a blueprint. Returns what was changed and what was refused.

The server also offers one *resource*, ``asimov://blueprints/reference``, which says
how to write a blueprint: the kinds, examples, and the rules below, so a client doesn't
have to learn them by being refused.

Each of these changes is recorded in the :doc:`audit log <audit>` (kinds ``review``
and ``label``), in the same transaction as the change. ``--read-only`` leaves out
every tool which changes anything. Only ``remove_label`` removes anything: it is
marked as destructive so that clients can ask first.

Lists are paged (``limit`` and ``offset``), and log and telemetry results are
capped, so a large project cannot flood the client. A filter which matches nothing
is not an error, but if the value isn't one that any analysis has (a misspelt
``status`` or ``pipeline``), the result has a ``warnings`` entry which says what
there is. There is no tool which deletes
an analysis, a subject or a record.

Blueprints
----------

``preview_blueprint`` and ``apply_blueprint`` take the blueprint as YAML text and
check it before asimov sees it:

* An analysis is for one subject. Say which with the ``subject`` argument or with
  ``event:`` (or ``subject:``) in the blueprint. If it is said twice the two must
  agree, and if they differ the call is an error: asimov would otherwise use the
  argument and ignore the rest.
* A document of a kind asimov doesn't know is refused (it is listed under
  ``refused``), as it is by ``asimov apply``.
* Names cannot contain control characters, ``<``, ``>`` or ``"``, because names are
  put into the markup which marks text as untrusted.
* ``update`` updates existing subjects and the configuration. It does not change an
  analysis which exists already: that is refused, and the result says so under
  ``problems``.

Several projects
----------------

To serve every project in a :doc:`registry <registry>` from one server, give it the
registry file instead of a project directory:

.. code-block:: console

    $ asimov mcp-server --registry /etc/asimov/registry.yaml

Every tool then takes an optional ``project`` argument, and ``list_projects`` says
which projects the agent can use. With one project (a directory, or a registry
with a single entry) ``project`` can be left out, which is why the tools take it
from the start; with several, leaving it out is an error which lists them.

Each call is for one project: it runs against that project's ledger, and a call for
one project doesn't wait for a call for another. Jobs (see below) belong to the
project they were started in, so ``get_job`` for a job in another project says there
is no such job.

Before each call the server asks :func:`asimov.access.authorize` whether the agent
(acting for the person who started the server) may do what the tool does to the
project: ``read`` for tools which look (and for ``preview_blueprint``), ``write``
for ``apply_blueprint`` and the review, comment and label tools, and ``execute``
for ``trigger_build`` and ``trigger_submit``. A project the agent may not read is
reported as not existing, as in the REST API.

.. warning::

    The policy asimov starts with allows everything, so an agent served a registry
    can use every project in it. See :doc:`registry`.

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
started and finished, what it did (for submit, ``{"submitted": n}``; for a dry run,
which submits nothing, ``{"dryrun": true, "would_submit": n}``)
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
instructions that it is data, not instructions. A closing tag inside the text is
altered, and the ``source`` the tag names (which can include the name of an analysis)
is escaped, so text cannot end the tag early. That reduces the chance that a model
follows an instruction hidden in a log, but it cannot prevent it, so do not give an
agent applying rights over a project whose logs you do not trust.

Names (of subjects, analyses and the like) are not marked: an agent needs them as
they are to ask about the thing they name. Those that a blueprint makes through the
server cannot contain markup characters, but names which were already in the project,
or were made by other means, can.

An MCP server cannot ask questions, so a blueprint which would make asimov prompt
(for example an analysis which does not say which subject it is for) is refused with
an error instead.
