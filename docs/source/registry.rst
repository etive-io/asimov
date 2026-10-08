The project registry
====================

An asimov instance which serves more than one project (see the
:doc:`MCP server <mcp>` and the REST API) needs to know which projects there are and
where they live. The *registry* is that list. Each project in it has:

``root``
    The project's directory. A relative path is relative to the registry file.
``groups``
    The groups which own the project. They aren't used to make decisions yet: see
    `Access`_.
``ledger``
    Optional: the ``engine`` and ``location`` of the project's ledger, when they
    aren't the ones in the project's own configuration. The location may be a
    database URL, and may use environment variables (``$NAME``), so that a password
    needn't be written in the registry.
``storage``
    Optional: where the project's results are stored.
``scheduler``
    Optional: the scheduler it submits to, such as ``htcondor``, ``slurm`` or ``local``.
``quotas``
    Optional: how much the project may submit. ``max_queued``,
    ``max_submit_per_pass`` and ``submit_interval`` are the ``[scheduler]`` limits
    described in :doc:`scheduler-integration`; the registry sets them for that
    project, so they hold for everything which submits on its behalf. Other keys are
    kept but not used.

Each project has its own ledger, as it always has, so one project's events,
analyses and history are never mixed with another's.

The registry file
-----------------

The registry is a YAML file, by default ``asimov/registry.yaml`` in your
configuration directory, or the file named by ``$ASIMOV_REGISTRY``:

.. code-block:: yaml

    projects:
      gw-o4:
        root: /data/projects/gw-o4
        groups: [cbc-pe]
        ledger:
          engine: postgresql
          location: postgresql://asimov:$GW_O4_DB_PASSWORD@db.example.org/gw_o4
        storage: /results/gw-o4
        scheduler: htcondor
        quotas:
          max_queued: 100
          max_submit_per_pass: 10

Project names are lower case letters, digits, ``.``, ``_`` and ``-`` (at most 64),
because they appear in URLs.

Managing it
-----------

.. code-block:: console

    $ asimov registry add gw-o4 /data/projects/gw-o4 -g cbc-pe --quota max_queued=100
    $ asimov registry list
    $ asimov registry show gw-o4
    $ asimov registry remove gw-o4

``--registry FILE`` chooses another file. These commands work anywhere, not only
inside a project. Removing a project from the registry leaves the project itself,
and everything in it, alone. ``show`` and ``list --format json`` hide the password in
a database URL.

From Python
-----------

.. code-block:: python

    from asimov.registry import FileRegistry

    registry = FileRegistry()
    context = registry.resolve("gw-o4")     # a new ProjectContext
    with context.activate():
        ...

Each call to ``resolve`` makes a new :class:`~asimov.context.ProjectContext`, so
requests which are handled at the same time don't share a ledger. Leaving out the
name is allowed when there is exactly one project, and an error which lists the
names otherwise. :class:`~asimov.registry.SingleProjectRegistry` wraps one project
directory, so code which takes a registry also works for a single project.

Access
------

Whatever handles a request for a project should call
:func:`asimov.access.authorize` with who is asking, the project, and what they want
to do (``read``, ``write``, ``execute`` or ``admin``). What is allowed is decided by
a *policy*, which can be replaced with :func:`asimov.access.set_policy`.

.. warning::

    The policy asimov starts with allows everything. Until projects have groups
    with roles (#183), anyone who can reach an instance can do anything to every
    project in it, so the instance has to be protected by who can reach it. The
    ``groups`` in the registry are recorded for that work, and aren't enforced.
