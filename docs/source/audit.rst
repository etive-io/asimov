The audit trail
===============

asimov keeps a record of who changed a project and what they applied. Each time a
blueprint changes the project, a record is added to the project's *audit log*:
when it happened, which :doc:`principal <principals>` did it (and who they were
acting for, with the group and role they held), what kind of document it was, what
it was applied to, and the document itself.

Reading the log
---------------

.. code-block:: console

    $ asimov audit show
    1   2026-10-07T08:02:11.482913Z   alice               apply configuration (added)   @project
    2   2026-10-07T08:02:12.031772Z   alice               apply event (added)           GW150914
    3   2026-10-07T08:05:40.117205Z   claude-1 (for dw)   apply analysis (added)        GW150914/bilby-prod

Each filter narrows what is shown: ``--target`` (an event, ``event/analysis``, or
``@project``, including what is under it), ``--principal`` (a person or agent, or
anyone acting for them), ``--kind``, ``--since``, ``--until`` and ``--limit`` (the most
recent N). ``--format json`` includes what was applied, and ``--format prov`` gives
the records as W3C PROV (JSON-LD).

From Python:

.. code-block:: python

    for record in ledger.audit_log(target="GW150914", principal="dw"):
        print(record.timestamp, record.principal_obj, record.kind, record.target)

What is recorded
----------------

* Blueprints applied with ``asimov apply``: ``configuration``, ``event``, ``analysis``,
  ``projectanalysis``, ``postprocessing`` and the analyses in an ``analysisbundle``.
  An event which is updated is recorded as an update. A document which is refused,
  for instance because the analysis already exists, changes nothing and leaves no
  record.
* The principal is *snapshotted* when the change is made. Group membership and roles
  change later; the record keeps what they were then.
* The document is stored as it was applied. The values of keys which look like
  credentials (names containing ``secret``, ``token``, ``password``, ``credential``,
  ``api key`` or ``private key``) are replaced with ``***``, and the hash is taken
  after that. This errs towards losing detail.

Where it is kept
----------------

The log belongs to the project, in its ledger.

*Database ledgers* keep it in an ``audit_log`` table, which is created in an existing
project the next time it is opened. A record is written in the same transaction as the
change it describes, so either both are stored or neither is: if the record cannot be
written, the change is not kept.

*YAML ledgers* keep it in ``.asimov/audit.jsonl``, one JSON record to a line, beside the
ledger. It is appended under the ledger's lock. Inside a ``with project:`` block records are
held back until the block succeeds. A YAML ledger is written by ``save()`` rather than
in a transaction, so the change and its record are not stored atomically: a crash between
the two can leave a change without a record. YAML ledgers are for a single user; use a
database ledger where that matters.

The log is append-only: asimov has no way to change or remove a record. That is a rule
of asimov, not of the storage. Where the log must resist someone with access to the
database, restrict that access (for example, grant the service ``INSERT`` and ``SELECT``
on ``audit_log`` and not ``UPDATE`` or ``DELETE``).

Telemetry sinks
---------------

A copy of each record is also passed to the telemetry sinks the project has enabled
(see :doc:`hooks`), as an event of type ``audit``, for systems outside
asimov. That copy is best effort: a sink which fails is logged and ignored. The ledger
holds the record.

Records as PROV
---------------

``AuditRecord.to_prov()`` describes a change as a ``prov:Activity`` (also a schema.org
``CreateAction``, which RO-Crate uses) that was associated with, and carried out by, the
principal, followed by the agents for the principal and whoever it acted for.
``asimov.audit.prov_document()`` gathers records into one JSON-LD document with the same
context as the RO-Crate export, so it can be included in a crate.

API reference
-------------

.. autoclass:: asimov.audit.AuditRecord
   :members:

.. autofunction:: asimov.audit.new_record

.. autofunction:: asimov.audit.append_audit

.. autofunction:: asimov.audit.filter_records

.. autofunction:: asimov.audit.prov_document
