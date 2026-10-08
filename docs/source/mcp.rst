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
