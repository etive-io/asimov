"""
Acting on a group of analyses, and on what depends on an analysis (#234).

A *group* is what one blueprint with a plugin strategy made: its analyses carry
``strategy: {type, id}`` (see :mod:`asimov.strategies`), and the group is
whatever carries the ``id``. Analyses are only ever found by that id, never by
a pattern in their names.

Nothing here prints or asks; the commands (:mod:`asimov.cli.analysis`) do, and
every change is also written to the audit trail.
"""
from dataclasses import dataclass
from typing import List, Optional, Tuple

from asimov.audit import append_audit, new_record
from asimov.strategies import read_group, strategy_stamp

#: The statuses in which an analysis may be running, and so is not deleted
#: without ``force``.
RUNNING = frozenset({"running", "processing", "uploading"})

#: The statuses which ``set`` accepts (as ``asimov production set`` does).
SETTABLE = frozenset({"ready", "wait", "stuck", "stop", "stopped", "cancelled"})


class GroupError(ValueError):
    """The group or analysis asked for cannot be found, or the request is refused."""


@dataclass
class Member:
    """An analysis, and where it is."""

    analysis: object
    #: The name of its subject, or None for a project analysis.
    subject: Optional[str]

    @property
    def name(self):
        return self.analysis.name

    @property
    def key(self) -> Tuple[Optional[str], str]:
        return (self.subject, self.analysis.name)

    @property
    def label(self) -> str:
        return f"{self.subject}/{self.name}" if self.subject else f"@project/{self.name}"

    @property
    def status(self) -> str:
        return str(self.analysis.status)


def everything(ledger) -> List[Member]:
    """Every analysis in the project, subjects' first, in a stable order."""
    members = []
    for subject in sorted(ledger.subject_names()):
        for analysis in sorted(ledger.get_event(subject)[0].productions, key=lambda a: a.name):
            members.append(Member(analysis, subject))
    for analysis in sorted(ledger.project_analyses, key=lambda a: a.name):
        members.append(Member(analysis, None))
    return members


def group_members(ledger, identifier: str, members: Optional[List[Member]] = None) -> List[Member]:
    """
    The analyses which a group made.

    Raises
    ------
    GroupError
        If the group has no record and no analysis carries its id.
    """
    members = everything(ledger) if members is None else members
    found = []
    for member in members:
        stamp = strategy_stamp(getattr(member.analysis, "meta", None) or {})
        if stamp and stamp["id"] == identifier:
            found.append(member)
    if not found and read_group(ledger, identifier) is None:
        raise GroupError(f"There is no group called '{identifier}'.")
    return found


def counts(members: List[Member]) -> dict:
    """How many analyses there are in each status."""
    found = {}
    for member in members:
        found[member.status] = found.get(member.status, 0) + 1
    return dict(sorted(found.items()))


def summary(members: List[Member]) -> str:
    """``96 analyses: 41 finished, 3 running, 52 waiting`` (in order of count)."""
    if not members:
        return "0 analyses"
    parts = sorted(counts(members).items(), key=lambda pair: (-pair[1], pair[0]))
    noun = "analysis" if len(members) == 1 else "analyses"
    return f"{len(members)} {noun}: " + ", ".join(f"{n} {status}" for status, n in parts)


def find(ledger, subject: str, name: str, members: Optional[List[Member]] = None) -> Member:
    """One analysis. ``subject`` is ``@project`` for a project analysis."""
    members = everything(ledger) if members is None else members
    wanted = None if subject in (None, "@project") else subject
    for member in members:
        if member.key == (wanted, name):
            return member
    raise GroupError(f"There is no analysis '{name}' in '{subject}'.")


def downstream(ledger, start: Member, members: Optional[List[Member]] = None) -> List[Member]:
    """
    ``start`` and every analysis which depends on it, directly or through others.

    Dependencies are those which each analysis resolves for itself, so they
    cross subjects as ``needs`` does. The result is in the order in which the
    analyses can be run again: an analysis comes after what it depends on.
    """
    members = everything(ledger) if members is None else members
    by_key = {member.key: member for member in members}

    dependents = {member.key: [] for member in members}
    for member in members:
        try:
            needed = member.analysis._dependency_analyses()
        except Exception:
            needed = []
        for dependency in needed:
            event = getattr(dependency, "event", None)
            key = (getattr(event, "name", None), dependency.name)
            if key in dependents and key != member.key:
                dependents[key].append(member.key)

    seen, order, queue = {start.key}, [start], [start.key]
    while queue:
        for key in sorted(dependents[queue.pop(0)]):
            if key not in seen:
                seen.add(key)
                order.append(by_key[key])
                queue.append(key)
    return order


def _save(ledger, member: Member):
    if member.subject is None:
        ledger.update_analysis_in_project_analysis(member.analysis)
    else:
        ledger.update_event(member.analysis.event)


def _audit(ledger, action, member, content):
    append_audit(
        ledger,
        new_record(action, "analysis", member.label, content=content, outcome="changed"),
    )


def set_status(ledger, members: List[Member], status: str) -> List[Member]:
    """
    Give each analysis a status. Returns those which changed.

    Raises
    ------
    GroupError
        If ``status`` is not one which may be set.
    """
    if status not in SETTABLE:
        raise GroupError(f"'{status}' cannot be set. Use one of: {', '.join(sorted(SETTABLE))}.")
    changed = []
    with ledger.transaction():
        for member in members:
            before = member.status
            if before == status:
                continue
            member.analysis.status = status
            _save(ledger, member)
            _audit(ledger, "set-status", member, {"from": before, "to": status})
            changed.append(member)
    return changed


def reset(ledger, members: List[Member], clean: bool = False) -> List[Member]:
    """
    Make each analysis ready to run again: status ``ready``, no job id, and
    (with ``clean``) its pipeline's artefacts removed.
    """
    with ledger.transaction():
        for member in members:
            analysis = member.analysis
            before = member.status
            if clean:
                analysis.pipeline.clean()
            analysis.status = "ready"
            scheduler = analysis.meta.get("scheduler")
            if isinstance(scheduler, dict):
                scheduler.pop("job id", None)
            _save(ledger, member)
            _audit(ledger, "rerun", member, {"from": before, "clean": bool(clean)})
    return members


def delete(ledger, members: List[Member], force: bool = False) -> List[Member]:
    """
    Remove analyses from the project.

    Raises
    ------
    GroupError
        If any is running and ``force`` is not given; then none is removed.
    """
    running = [m.label for m in members if m.status in RUNNING]
    if running and not force:
        raise GroupError(
            f"{len(running)} of these are running ({', '.join(running[:5])}"
            f"{', ...' if len(running) > 5 else ''}); stop them first, or use --force."
        )
    with ledger.transaction():
        for member in members:
            if member.subject is None:
                ledger.delete_project_analysis(member.name)
            else:
                ledger.delete_analysis(member.subject, member.name)
            _audit(ledger, "delete", member, {"status": member.status})
    return members
