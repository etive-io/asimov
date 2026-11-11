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
import os
from typing import Optional

from asimov.audit import append_audit, new_record, responsible_identifier

__all__ = [
    "Accounting", "AccountingError", "check", "hand_over", "prepare", "requester", "resolve",
    "rules_for", "submit_files",
]


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


# ---------------------------------------------------------------------------
# Applying it at build and submission
# ---------------------------------------------------------------------------

#: Submit-description keys which say who is charged, lower-cased, and which
#: field of :class:`Accounting` each must match.
SUBMIT_KEYS = {
    "accounting_group_user": "user",
    "+acctgroupuser": "user",
    "accounting_group": "tag",
    "+acctgroup": "tag",
    "+accountinggroup": "tag",
}


def rules_for(root):
    """
    The registry entry and groups for the project in ``root``, if it is served
    by an instance which enforces groups.

    Found from the instance's registry (``$ASIMOV_REGISTRY``, or the default),
    so that the command line, the monitor and the MCP server's job workers all
    apply the same rules to a hosted project.

    Returns
    -------
    tuple of (ProjectEntry, GroupDirectory) or (None, None)
    """
    from asimov import access
    from asimov.registry import FileRegistry, RegistryError, default_registry_path

    path = default_registry_path()
    if not root or not os.path.exists(path):
        return None, None
    registry = FileRegistry(path)
    try:
        entries = registry.list()
    except RegistryError:
        return None, None
    here = os.path.realpath(root)
    entry = next((e for e in entries if os.path.realpath(e.root) == here), None)
    if entry is None:
        return None, None
    policy = access.instance_policy(registry)
    if policy is None:
        return None, None
    return entry, policy.directory


def _hosted(analysis):
    from asimov.context import get_active_context

    context = get_active_context()
    if context is None:
        return None, None, None
    entry, directory = rules_for(getattr(context, "root", None))
    return context, entry, directory


def prepare(analysis):
    """
    Put who is charged into ``analysis``, before its configuration is built.

    Pipelines write ``scheduler`` values into the submit files they make, so
    the resolved user and tag replace whatever the blueprint said. Does
    nothing for a project which isn't hosted with groups.

    Returns
    -------
    Accounting or None

    Raises
    ------
    AccountingError
    """
    context, entry, directory = _hosted(analysis)
    if directory is None:
        return None
    found = resolve(context.ledger, analysis, entry, directory)
    scheduler = analysis.meta.setdefault("scheduler", {})
    scheduler["accounting group user"] = found.user
    if found.tag:
        scheduler["accounting group"] = found.tag
    return found


def submit_files(rundir):
    """
    The submit descriptions of the jobs under ``rundir``.

    Every ``*.sub`` and ``*.submit`` file, and every file a DAG under it names
    in a ``JOB`` line (``SUBDAG EXTERNAL`` DAGs are followed), except the
    ``*.condor.sub`` files DAGMan writes for itself.
    """
    found, dags, seen = set(), [], set()
    for here, _, names in os.walk(rundir):
        for name in names:
            path = os.path.join(here, name)
            if name.endswith(".condor.sub"):
                continue
            if name.endswith((".sub", ".submit")):
                found.add(os.path.realpath(path))
            elif name.endswith(".dag"):
                dags.append(path)
    while dags:
        dag = os.path.realpath(dags.pop())
        if dag in seen or not os.path.isfile(dag):
            continue
        seen.add(dag)
        base = os.path.dirname(dag)
        with open(dag, errors="replace") as handle:
            for line in handle:
                words = line.split()
                if len(words) >= 3 and words[0].upper() == "JOB":
                    directory = base
                    if "DIR" in [w.upper() for w in words[3:]]:
                        index = [w.upper() for w in words].index("DIR")
                        if index + 1 < len(words):
                            directory = os.path.join(base, words[index + 1])
                    found.add(os.path.realpath(os.path.join(directory, words[2])))
                elif len(words) >= 4 and words[0].upper() == "SUBDAG" and words[1].upper() == "EXTERNAL":
                    dags.append(os.path.join(base, words[3]))
    return sorted(found)


def problems(path, accounting):
    """What in one submit description doesn't charge ``accounting``."""
    try:
        with open(path, errors="replace") as handle:
            lines = handle.read().splitlines()
    except OSError as error:
        return [f"{path} could not be read: {error}"]
    found, wrong = {}, []
    for line in lines:
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        if text.lower().startswith("include"):
            wrong.append(f"{path} includes another file, which can't be checked")
            continue
        key, separator, value = text.partition("=")
        if not separator:
            continue
        field = SUBMIT_KEYS.get(key.strip().lower())
        if field is None:
            continue
        value = value.strip().strip('"').strip()
        expected = getattr(accounting, field)
        found[field] = value
        if "$(" in value:
            wrong.append(f"{path} sets {key.strip()} from a macro, which can't be checked")
        elif value != expected:
            wrong.append(f"{path} charges {key.strip()} = {value!r}, not {expected!r}")
    for field, key in (("user", "accounting_group_user"), ("tag", "accounting_group")):
        if getattr(accounting, field) and field not in found:
            wrong.append(f"{path} doesn't set {key}")
    return wrong


def check(analysis, dryrun=False):
    """
    Refuse to submit ``analysis`` unless every job charges who it should.

    Does nothing for a project which isn't hosted with groups, or in a dry
    run. The charge is recorded in the audit trail.

    Returns
    -------
    Accounting or None

    Raises
    ------
    AccountingError
        Saying which files charge someone else, or don't say.
    """
    context, entry, directory = _hosted(analysis)
    if directory is None or dryrun:
        return None
    found = resolve(context.ledger, analysis, entry, directory)
    rundir = getattr(analysis, "rundir", None)
    if not rundir or not os.path.isdir(rundir):
        raise AccountingError(f"{_target(analysis)} has no run directory to check.")
    files = submit_files(rundir)
    if not files:
        raise AccountingError(f"No submit files were found for {_target(analysis)} in {rundir}.")
    wrong = [p for path in files for p in problems(path, found)]
    if wrong:
        raise AccountingError(
            f"Refusing to submit {_target(analysis)}: " + "; ".join(wrong[:5])
            + (f"; and {len(wrong) - 5} more" if len(wrong) > 5 else "")
        )
    with context.ledger.transaction():
        append_audit(
            context.ledger,
            new_record("submit", "analysis", _target(analysis), outcome="charged",
                       accounting=found.to_dict()),
        )
    return found
