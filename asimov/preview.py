"""
Previewing what applying a blueprint would do, without doing it.

``asimov apply --dry-run`` runs the same code which applies a blueprint, so the
decisions it makes (which documents are accepted, which are refused, what an
analysis is called) are the real ones. The ledger is put in a mode where
nothing it writes is kept, and each change which would be made is recorded in
an :class:`ApplyPlan` instead, in the same shape as the audit record which
applying it would add (see :mod:`asimov.audit`).

Examples
--------
Ask what a blueprint would do, from Python::

    plan = apply_page("blueprint.yaml", ledger=ledger, dry_run=True)
    for change in plan.changes:
        print(change.record.kind, change.record.target, change.record.outcome)
    for refusal in plan.refused:
        print(refusal.message)
"""

import contextlib
import copy
import dataclasses
from contextvars import ContextVar
from typing import List, Optional

from asimov.audit import AuditRecord
from asimov.utils import diff_dict

__all__ = [
    "ApplyPlan",
    "PlannedChange",
    "Refusal",
    "changed_paths",
    "current_plan",
    "is_dry_run",
    "preview",
]

# The plan being made in this thread or task, if a dry run is in progress.
_plan: ContextVar = ContextVar("asimov_apply_plan", default=None)


def is_dry_run():
    """Whether a dry run is in progress in this thread or task."""
    return _plan.get() is not None


def current_plan():
    """The :class:`ApplyPlan` being made by the dry run in progress, or ``None``."""
    return _plan.get()


def _lookup(data, path):
    for key in path:
        if not isinstance(data, dict) or key not in data:
            return None
        data = data[key]
    return data


def changed_paths(before, after):
    """
    What differs between two dictionaries, one entry per value which changes.

    Uses :func:`asimov.utils.diff_dict`, which is how asimov decides what a
    blueprint changes: values which are new or different in ``after``. A key
    which is only in ``before`` is not a change, since applying a blueprint
    never removes anything.

    Parameters
    ----------
    before, after : dict

    Returns
    -------
    list of dict
        Each has ``path`` (dotted), ``before`` (``None`` if the key is new) and
        ``after``.
    """
    changes = []

    def walk(delta, prefix):
        for key, value in delta.items():
            path = prefix + [str(key)]
            if isinstance(value, dict) and isinstance(_lookup(before, path), dict):
                walk(value, path)
            else:
                changes.append(
                    {
                        "path": ".".join(path),
                        "before": copy.deepcopy(_lookup(before, path)),
                        "after": copy.deepcopy(value),
                    }
                )

    walk(diff_dict(before, after), [])
    return changes


@dataclasses.dataclass
class PlannedChange:
    """
    One change applying a blueprint would make.

    Parameters
    ----------
    record : asimov.audit.AuditRecord
        The audit record which would be written for it: who, what kind of
        document, to what, and the document itself.
    diff : list of dict, optional
        For a change to something which already exists (the configuration, an
        event which is updated), what would be different: see
        :func:`changed_paths`.
    """

    record: AuditRecord
    diff: Optional[List[dict]] = None

    def to_dict(self):
        data = self.record.to_dict()
        data.pop("id", None)
        data["diff"] = self.diff
        return data


@dataclasses.dataclass
class Refusal:
    """
    Something in a blueprint which would not be applied, and why.

    Parameters
    ----------
    message : str
        What asimov would say.
    level : str
        ``"refused"`` for a document which is not applied, ``"skipped"`` for
        one which is left out of a bundle.
    """

    message: str
    level: str = "refused"

    def to_dict(self):
        return dataclasses.asdict(self)


@dataclasses.dataclass
class ApplyPlan:
    """
    What applying a blueprint would do: the changes it would make, in order,
    and what it would refuse.
    """

    changes: List[PlannedChange] = dataclasses.field(default_factory=list)
    refused: List[Refusal] = dataclasses.field(default_factory=list)

    def add_change(self, record, diff=None):
        """Note a change which would be made."""
        self.changes.append(PlannedChange(record, diff))

    def refuse(self, message, level="refused"):
        """Note something which would not be applied."""
        self.refused.append(Refusal(message, level))

    @property
    def empty(self):
        """Whether applying the blueprint would change nothing."""
        return not self.changes

    def to_dict(self):
        """The plan as plain data."""
        return {
            "dry_run": True,
            "changes": [change.to_dict() for change in self.changes],
            "refused": [refusal.to_dict() for refusal in self.refused],
        }

    def render(self):
        """
        The plan as lines of text for a person.

        Returns
        -------
        list of str
        """
        lines = ["Dry run: nothing was written."]
        for change in self.changes:
            record = change.record
            mark = "~" if record.outcome == "updated" else "+"
            lines.append(f"  {mark} {record.kind} {record.target} ({record.outcome})")
            for entry in change.diff or []:
                if entry["before"] is None:
                    lines.append(f"      {entry['path']}: {entry['after']!r}")
                else:
                    lines.append(
                        f"      {entry['path']}: {entry['before']!r} -> {entry['after']!r}"
                    )
        for refusal in self.refused:
            lines.append(f"  ! {refusal.message}")
        if self.empty and not self.refused:
            lines.append("  Nothing would change.")
        return lines


@contextlib.contextmanager
def preview(ledger):
    """
    Make a plan of what is done in the block, and keep none of it.

    Inside the block ``ledger`` discards what it is asked to write, and
    asimov skips what it would otherwise create on disk. Whatever applies a
    blueprint reports each change to the plan with
    :func:`asimov.cli.application.apply_page`.

    Parameters
    ----------
    ledger : Ledger
        The ledger which would be changed.

    Yields
    ------
    ApplyPlan
    """
    plan = ApplyPlan()
    token = _plan.set(plan)
    try:
        with ledger.dry_run():
            yield plan
    finally:
        _plan.reset(token)
