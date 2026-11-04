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
to do (``read``, ``write``, ``execute``, ``review`` or ``admin``). What is allowed
is decided by a *policy*.

.. warning::

    Without a groups file (below), the policy allows everything: anyone who can
    reach an instance can do anything to every project in it, so the instance has
    to be protected by who can reach it.

Groups and roles
~~~~~~~~~~~~~~~~

People belong to groups, and groups hold roles on projects. Nobody is granted a
project directly, so a personal project is one owned by a group with one member.
The groups in a project's ``groups`` own it, and hold the *maintainer* role on it.
Its ``grants`` give other groups other roles:

.. code-block:: yaml

    projects:
      gw-o4:
        root: /data/projects/gw-o4
        groups: [cbc-pe, tgr]
        grants:
          cbc-review: [reviewer]
          ligo-all: [viewer]

=============  ==============================================================
Role           May
=============  ==============================================================
viewer         read the project
reviewer       read; set review status, and comment
analyst        read; apply blueprints, comment and label; build and submit
maintainer     everything an analyst or a reviewer may, and change the
               project's registry entry and grants
=============  ==============================================================

Who is in which group is kept in ``groups.yaml``, beside the registry file (or the
file named by ``$ASIMOV_GROUPS``), with the instance admins, who may do anything to
any project:

.. code-block:: yaml

    admins: [dw]
    groups:
      cbc-pe:
        members: [dw, jane]
      cbc-review:
        members: [sam]

Once that file exists, the REST API and the MCP server serving the registry enforce
the grants. The file is read for each request, so a change to it applies at once.
If it can't be read, or doesn't make sense, every request is denied. Membership is
flat: a group can't be a member of another group.

An agent has the authority of the person it acts for, and never more; an agent
acting for nobody has none. The monitor may read, change and run what is in a
project, but not review it. The group and role which allowed a change are recorded
with it in the project's audit trail, as they were at the time.

Groups from an identity provider's token claims (#182) are not supported yet, so
groups are local ones, kept by the instance's admins.

The grants and members can be changed from the command line, rather than by
editing the files:

.. code-block:: console

    $ asimov registry grant gw-o4 cbc-review reviewer
    $ asimov registry revoke gw-o4 cbc-review          # every role it was granted
    $ asimov registry members cbc-review --add sam --remove jane
    $ asimov registry self-approval gw-o4 on

Reviewing your own work
~~~~~~~~~~~~~~~~~~~~~~~

Where groups are enforced, whoever applied an analysis (or an agent acting for them)
may not approve it: setting ``APPROVED`` or ``PREFERRED`` on it is refused, and
someone else has to review it. Rejecting it, deprecating it and commenting on it are
still allowed. Who applied an analysis is taken from the project's audit trail.

There are two ways round this:

* A **maintainer** (or an instance admin) may approve their own analysis by giving a
  reason, which is kept in the audit record of the review (``override_reason`` in the
  MCP ``set_review_status`` tool).
* A project where the same people analyse and review, such as a personal project, can
  set ``self_approval: true`` in its registry entry (``asimov registry self-approval
  NAME on``), and then the rule doesn't apply to it.
