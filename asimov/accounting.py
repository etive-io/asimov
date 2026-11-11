"""
Who an analysis's jobs are charged to (#181).

On a hosted instance every job runs under one shared account, so the scheduler
can't tell who to charge: asimov tells it, with ``accounting_group_user`` (the
person charged) and ``accounting_group`` (the accounting tag). Neither may come
from a blueprint, since anyone who can apply one could then charge someone
else. :func:`resolve` works them out:

* **Who requested the analysis** is charged for it, and for the work which
  follows from it (resubmissions, runs started when a dependency finishes).
  The requester is whoever applied it, from the project's audit trail, unless
  it has since been handed to someone else (:func:`hand_over`). They are
  charged under the accounting name their sign-in token gave when they applied
  it (see :mod:`asimov.identity`), or else their identifier.
* **A project can bill a group** instead (``billing_group`` in its registry
  entry). The scheduler needs a person, so the group's ``accounting contact``
  in ``groups.yaml`` is charged, and the requester is still recorded.
* **Accounting tags are granted to groups** (``accounting tags`` in
  ``groups.yaml``, as patterns such as ``ligo.prod.*``). Once any group lists
  tags, an analysis may only use a tag granted to a group its requester (or the
  billed group) is in.

An instance without a groups file works as it always has: the ``[condor]``
``user`` and ``accounting`` settings, or the analysis's own ``scheduler``
values.
"""

import dataclasses
import fnmatch
from typing import Optional

from asimov.audit import append_audit, new_record, responsible_identifier

__all__ = ["Accounting", "AccountingError", "hand_over", "requester", "resolve"]


class AccountingError(ValueError):
    """The analysis can't be charged to anyone it is allowed to be."""


@dataclasses.dataclass(frozen=True)
class Accounting:
    """
    Who an analysis's jobs are charged to.

    Attributes
    ----------
    user : str or None
        The ``accounting_group_user``: the person charged.
    tag : str or None
        The ``accounting_group``.
    requested_by : str or None
        The identifier of whoever requested the analysis.
    billed_group : str or None
        The group billed, if it isn't the requester.
    """

    user: Optional[str]
    tag: Optional[str]
    requested_by: Optional[str] = None
    billed_group: Optional[str] = None

    def to_dict(self):
        """For an audit record: the fields which are set."""
        return {k.replace("_", " "): v for k, v in dataclasses.asdict(self).items() if v is not None}


def _target(analysis):
    return f"{analysis.event.name}/{analysis.name}"


def requester(ledger, analysis):
    """
    Who requested ``analysis``, and the accounting name they are charged under.

    The latest handover, if there has been one, otherwise the first time it
    was applied.

    Returns
    -------
    tuple of (str, str) or None
        The identifier and accounting name, or ``None`` if the audit trail
        doesn't say (the analysis predates it).
    """
    target = _target(analysis)
    handovers = ledger.audit_log(target=target, action="hand over")
    for record in reversed(handovers):
        if record.target == target:
            to = (record.content or {}).get("to")
            if to:
                return to, (record.accounting or {}).get("user") or to
    for record in ledger.audit_log(target=target, action="apply"):
        if record.target == target:
            who = responsible_identifier(record.principal)
            return who, (record.accounting or {}).get("user") or who
    return None


def hand_over(ledger, analysis, to, accounting=None, reason=None):
    """
    Make ``to`` the requester of ``analysis``, so they are charged for it.

    The handover is recorded in the audit trail, by whoever makes it. The
    caller checks they may (a maintainer, or the requester).

    Parameters
    ----------
    to : str
        The new requester's identifier.
    accounting : str, optional
        The name they are charged under, if it isn't their identifier.
    reason : str, optional

    Returns
    -------
    AuditRecord
    """
    if not isinstance(to, str) or not to.strip():
        raise AccountingError("Say who the analysis is handed to.")
    content = {"to": to.strip()}
    if reason:
        content["reason"] = str(reason)
    with ledger.transaction():
        return append_audit(
            ledger,
            new_record(
                "hand over", "analysis", _target(analysis), content=content,
                accounting={"user": accounting or to.strip()},
            ),
        )


def _scheduler(analysis):
    meta = getattr(analysis, "meta", {}) or {}
    value = meta.get("scheduler") or {}
    return value if isinstance(value, dict) else {}


def _config(section, option):
    from asimov import config

    try:
        return config.get(section, option)
    except Exception:
        return None


def resolve(ledger, analysis, entry=None, directory=None):
    """
    Who ``analysis``'s jobs are charged to, and under which accounting tag.

    Parameters
    ----------
    ledger : Ledger
    analysis : Analysis
    entry : asimov.registry.ProjectEntry, optional
        The project's registry entry, for its ``billing_group``.
    directory : asimov.membership.GroupDirectory, optional
        The instance's groups. Without one, the single-user rules apply: the
        analysis's own ``scheduler`` values, then the ``[condor]`` settings.

    Returns
    -------
    Accounting

    Raises
    ------
    AccountingError
        If nobody can be charged, the billed group has no accounting contact,
        or the accounting tag isn't one the requester may use.
    """
    asked = _scheduler(analysis)
    tag = asked.get("accounting group") or _config("condor", "accounting")
    if directory is None:
        user = asked.get("accounting group user") or _config("condor", "user")
        return Accounting(user=user, tag=tag)

    found = requester(ledger, analysis)
    if found is None:
        raise AccountingError(
            f"Nobody is recorded as requesting {_target(analysis)}, so it can't be charged: "
            "hand it over to someone first."
        )
    requested_by, user = found
    settings = directory.settings()
    billed = getattr(entry, "billing_group", None) if entry is not None else None
    if billed:
        contact = (settings.get(billed) or {}).get("accounting contact")
        if not contact:
            raise AccountingError(f"The project bills {billed}, which has no accounting contact.")
        user, groups = contact, {billed}
    else:
        groups = set(directory.groups_of(requested_by))

    if any(s.get("accounting tags") for s in settings.values()):
        allowed = [p for g in groups for p in (settings.get(g) or {}).get("accounting tags", [])]
        if not tag or not any(fnmatch.fnmatchcase(tag, p) for p in allowed):
            who = f"the group {billed}" if billed else requested_by
            raise AccountingError(f"{who} may not use the accounting tag {tag!r}.")
    return Accounting(user=user, tag=tag, requested_by=requested_by, billed_group=billed)
