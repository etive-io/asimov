"""
The audit trail: a record of who changed a project, and what they applied.

Every change made to a project by applying a blueprint is recorded as an
:class:`AuditRecord`: when, by which principal (and who they acted for, with
the group and role that gave them authority, as they were at the time), what
was applied, and to what. The records belong to the project, and are kept in
its ledger, so they are made in the same transaction as the change they
describe: either both persist or neither does.

The log is append-only. Nothing in asimov changes or deletes a record.

Records are shaped to map onto W3C PROV, so they fit in the RO-Crate export
rather than forming a separate record (see :meth:`AuditRecord.to_prov`).

Examples
--------
What has been applied to an event, newest last::

    for record in ledger.audit_log(target="GW150914"):
        print(record.timestamp, record.principal_obj, record.kind, record.target)
"""

import dataclasses
import datetime
import hashlib
import json
import re
from typing import Optional

from asimov import logger as _logger
from asimov.principal import Principal, current_principal

logger = _logger.getChild("audit")

__all__ = [
    "AuditRecord",
    "PROJECT",
    "append_audit",
    "filter_records",
    "new_record",
    "prov_document",
    "responsible_identifier",
    "timestamp_for",
]

#: The target of a change to the project as a whole, rather than to one event
#: or analysis. Event names don't begin with ``@``, so it can't be mistaken for one.
PROJECT = "@project"

_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"

# Keys whose values are not recorded, whatever they hold (a list or a mapping
# included). Audit records are readable by anyone who can read the log, and a
# blueprint may well carry credentials. This errs towards losing detail.
_SECRET_KEY = re.compile(
    r"secret|token|passw(or)?d|credential|api[ _-]?key|private[ _-]?key", re.IGNORECASE
)
_REDACTED = "***"


def timestamp_for(moment=None):
    """
    A moment in the fixed-width UTC form records are stamped with.

    The width never varies, so timestamps sort and compare correctly as text.

    Parameters
    ----------
    moment : datetime.datetime, optional
        Defaults to now. A naive datetime is taken to be UTC.
    """
    if moment is None:
        moment = datetime.datetime.now(datetime.timezone.utc)
    elif moment.tzinfo is None:
        moment = moment.replace(tzinfo=datetime.timezone.utc)
    return moment.astimezone(datetime.timezone.utc).strftime(_TIMESTAMP_FORMAT)


def _plain(value):
    """``value`` as plain JSON data, with secret-looking values removed."""
    if isinstance(value, dict):
        return {
            str(key): _REDACTED if _SECRET_KEY.search(str(key)) else _plain(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _hash(content):
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf8")).hexdigest()


@dataclasses.dataclass(frozen=True)
class AuditRecord:
    """
    One change to a project.

    Parameters
    ----------
    action : str
        What was done, e.g. ``"apply"``.
    kind : str
        The kind of blueprint document applied (``"analysis"``, ``"event"``,
        ``"configuration"``, ...).
    target : str
        What it was applied to: an event name, ``event/analysis``,
        or :data:`PROJECT` (``@project``, or ``@project/name``) for the project itself.
    principal : dict
        The :class:`~asimov.principal.Principal` who acted, as data, as it
        was when they acted. Not looked up again: group membership changes.
    timestamp : str
        When, as :func:`timestamp_for` gives it.
    outcome : str
        ``"added"`` or ``"updated"``.
    content : dict, optional
        The document as applied, with the values of secret-looking keys
        removed.
    content_hash : str
        SHA-256 of ``content``, so a record can be compared without it.
    accounting : dict, optional
        The accounting identity charged, where the change launched jobs.
        Reserved: nothing sets it yet.
    id : int, optional
        The record's place in the log, given when it is stored.
    """

    action: str
    kind: str
    target: str
    principal: dict
    timestamp: str
    outcome: str = "added"
    content: Optional[dict] = None
    content_hash: str = ""
    accounting: Optional[dict] = None
    id: Optional[int] = None

    @property
    def principal_obj(self):
        """The principal, as a :class:`~asimov.principal.Principal`."""
        return Principal.from_dict(self.principal)

    def to_dict(self):
        """The record as plain data."""
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data):
        """Rebuild a record from :meth:`to_dict`, ignoring keys it doesn't know."""
        known = {field.name for field in dataclasses.fields(cls)}
        return cls(**{key: value for key, value in data.items() if key in known})

    @property
    def prov_id(self):
        """The identifier of this change as a PROV activity."""
        return f"urn:asimov:activity:audit:{self.id if self.id is not None else self.content_hash[:16]}"

    def to_prov(self):
        """
        The record as W3C PROV, in the form of the provenance export.

        Returns
        -------
        list of dict
            JSON-LD nodes: a ``prov:Activity`` (also a schema.org
            ``CreateAction``, which is how RO-Crate describes one) associated
            with and carried out by the principal, followed by the agents for
            the principal and whoever it acted for.
        """
        principal = self.principal_obj
        activity = {
            "@id": self.prov_id,
            "@type": ["prov:Activity", "CreateAction"],
            "asimov:action": self.action,
            "asimov:kind": self.kind,
            "asimov:target": self.target,
            "asimov:outcome": self.outcome,
            "prov:startedAtTime": self.timestamp,
            "prov:wasAssociatedWith": {"@id": principal.prov_id},
            "agent": {"@id": principal.prov_id},
        }
        if self.content_hash:
            activity["asimov:contentHash"] = self.content_hash
        if self.accounting:
            activity["asimov:accounting"] = self.accounting
        return [activity] + principal.to_prov()


def new_record(action, kind, target, content=None, outcome="added", accounting=None, principal=None):
    """
    Make a record of a change being made now, by the current principal.

    Parameters
    ----------
    action, kind, target, outcome
        See :class:`AuditRecord`.
    content : dict, optional
        The document applied. It is copied, and values of secret-looking keys
        are not kept.
    accounting : dict, optional
        See :class:`AuditRecord`.
    principal : Principal, optional
        Who acted. Defaults to :func:`~asimov.principal.current_principal`.
    """
    principal = principal if principal is not None else current_principal()
    plain = None if content is None else _plain(content)
    return AuditRecord(
        action=action,
        kind=kind,
        target=target,
        principal=principal.to_dict(),
        timestamp=timestamp_for(),
        outcome=outcome,
        content=plain,
        content_hash="" if plain is None else _hash(plain),
        accounting=accounting,
    )


def append_audit(ledger, record):
    """
    Add ``record`` to the project's audit log.

    Call it where the change is made, inside ``ledger.transaction()`` so the
    two are stored together. The record is also passed, as a best-effort copy,
    to any telemetry sinks the project has enabled, for systems outside asimov;
    that is not the record, and a sink which fails does not matter.

    Returns
    -------
    AuditRecord
        The record as stored, with its ``id``.
    """
    stored = ledger.append_audit(record)
    _copy_to_sinks(ledger, stored)
    return stored


def _copy_to_sinks(ledger, record):
    """Give external telemetry sinks a copy of an audit record. Never raises."""
    try:
        from asimov import telemetry

        event = telemetry.TelemetryEvent(
            timestamp=record.timestamp,
            event_type="audit",
            event_name=record.target,
            analysis_name="",
            rundir="",
            data=record.to_dict(),
        )
        for name in telemetry._enabled_sink_names(ledger):
            sink = telemetry.TELEMETRY_SINK_REGISTRY.get(name)
            if sink is None:
                continue
            try:
                sink.emit(event)
            except Exception as error:
                logger.warning("Telemetry sink '%s' failed for an audit record: %s", name, error)
    except Exception as error:  # pragma: no cover - telemetry must not matter
        logger.debug("Could not copy an audit record to telemetry: %s", error)


def _under(target, prefix):
    return target == prefix or target.startswith(prefix + "/")


def filter_records(
    records, target=None, principal=None, kind=None, action=None, since=None, until=None
):
    """
    The records which match every filter given, in the order they came.

    This is the filtering the ledgers which can't ask a database to do it use;
    the database ledger asks the database, with the same meaning.

    Parameters
    ----------
    target : str, optional
        Records for this target, and for what is under it: ``"GW150914"``
        also matches ``"GW150914/bilby-1"``.
    principal : str, optional
        Records made by the principal with this identifier, or by an agent
        acting for them (at any depth).
    kind, action : str, optional
        Records of this kind of document, or this action.
    since, until : datetime.datetime or str, optional
        Records from this moment (inclusive) / until it (exclusive).
    """
    since = timestamp_for(since) if isinstance(since, datetime.datetime) else since
    until = timestamp_for(until) if isinstance(until, datetime.datetime) else until
    for record in records:
        if target is not None and not _under(record.target, target):
            continue
        if principal is not None and principal not in (
            record.principal.get("identifier"),
            responsible_identifier(record.principal),
        ):
            continue
        if kind is not None and record.kind != kind:
            continue
        if action is not None and record.action != action:
            continue
        if since is not None and record.timestamp < since:
            continue
        if until is not None and record.timestamp >= until:
            continue
        yield record


def responsible_identifier(principal_data):
    """The identifier of the principal at the end of an ``acting for`` chain."""
    while principal_data.get("acting for") is not None:
        principal_data = principal_data["acting for"]
    return principal_data.get("identifier")


def prov_document(records):
    """
    A JSON-LD document describing ``records`` as W3C PROV.

    It uses the same context as the RO-Crate export, so the graph can be
    included in a crate as it is. An agent which appears in several records
    is described once.

    Parameters
    ----------
    records : iterable of AuditRecord

    Returns
    -------
    dict
    """
    from asimov.provenance import PROV_CONTEXT
    from asimov.rocrate import RO_CRATE_CONTEXT

    graph, seen = [], set()
    for record in records:
        for node in record.to_prov():
            if node["@id"] in seen:
                continue
            seen.add(node["@id"])
            graph.append(node)
    return {"@context": [RO_CRATE_CONTEXT, PROV_CONTEXT], "@graph": graph}
