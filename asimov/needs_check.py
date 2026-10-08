"""
Check the graph of ``needs`` which a blueprint leaves behind (#231).

``needs`` can now reach analyses of other subjects, so a mistake in one
blueprint can leave something which cannot run: a cycle, or a need which names
an analysis that is not there. Applying reports these straight away rather than
leaving them to be found when the analysis never starts.
"""
from typing import Iterable, List, Tuple

#: (level, message), where the level is "error" or "warning" (see :class:`asimov.preview.Problem`).
Finding = Tuple[str, str]


def _name(analysis) -> str:
    subject = getattr(getattr(analysis, "event", None), "name", None)
    return f"{subject}/{analysis.name}" if subject else analysis.name


def _dangling(subject_names, analysis) -> List[Finding]:
    """
    The needs of one analysis which name something which is not there.

    ``subject_names`` is a function giving the names of the subjects of the
    project, which is only called if a need is found not to resolve.
    """
    found = []
    for requirement in analysis.required_dependencies:
        if not analysis._is_qualified_requirement(requirement):
            continue
        if analysis._requirement_matches(requirement):
            continue
        conditions = requirement if isinstance(requirement, list) else [requirement]
        target = analysis._qualified_target(conditions)
        if target is None:
            # A ``subject:`` filter: nothing matches yet, which can change.
            found.append(
                ("warning", f"{_name(analysis)}: {analysis._describe_requirement(requirement)}")
            )
            continue
        subject, name, _ = target
        if subject not in subject_names():
            found.append(
                (
                    "warning",
                    f"{_name(analysis)} needs {subject}/{name}, but there is no subject "
                    f"'{subject}' (yet)",
                )
            )
        else:
            found.append(
                (
                    "error",
                    f"{_name(analysis)} needs {subject}/{name}, but '{subject}' has no "
                    f"analysis named '{name}'",
                )
            )
    return found


def _cycles(start: Iterable) -> List[Finding]:
    """
    The cycles which can be reached from some analyses by following ``needs``,
    each reported once.
    """
    colour = {}  # key -> 1 (on the path) or 2 (done)
    found = []
    seen = set()

    def key(analysis):
        return (getattr(getattr(analysis, "event", None), "name", None), analysis.name)

    for origin in start:
        if key(origin) in colour:
            continue
        path = []
        stack = [(origin, iter(origin.dependency_objects))]
        colour[key(origin)] = 1
        path.append(origin)
        while stack:
            analysis, children = stack[-1]
            for child in children:
                state = colour.get(key(child))
                if state is None:
                    colour[key(child)] = 1
                    path.append(child)
                    stack.append((child, iter(child.dependency_objects)))
                    break
                if state == 1:
                    cycle = path[[key(a) for a in path].index(key(child)):]
                    # The same cycle is found from each of its members.
                    identity = frozenset(key(a) for a in cycle)
                    if identity not in seen:
                        seen.add(identity)
                        names = [_name(a) for a in cycle] + [_name(child)]
                        found.append(("error", "needs form a cycle: " + " -> ".join(names)))
            else:
                colour[key(analysis)] = 2
                path.pop()
                stack.pop()
    return found


def check_needs(ledger, subjects: Iterable[str], loaded=None) -> List[Finding]:
    """
    Find what is wrong with the ``needs`` of the analyses in some subjects.

    Only these subjects are read, and those which their needs lead to, so
    checking what a blueprint touched does not cost the size of the project.

    Parameters
    ----------
    ledger : Ledger
    subjects : iterable of str
        The subjects to check, usually those a blueprint changed.
    loaded : dict, optional
        Subjects which are already built, by name, which are used instead of
        reading them again.

    Returns
    -------
    list of (str, str)
        ``(level, message)`` for each problem: ``"error"`` for a cycle, or a
        need which names an analysis which a subject that exists does not
        have; ``"warning"`` for a need on a subject which does not exist yet.
    """
    names = []

    def subject_names():
        # Reading them costs a query on some ledgers, so once and only if needed.
        if not names:
            names.append(set(ledger.subject_names()))
        return names[0]

    known = subject_names()
    analyses = []
    for name in sorted(set(subjects)):
        if name not in known:
            continue
        subject = (loaded or {}).get(name) or ledger.get_event(name)[0]
        analyses.extend(subject.productions)
    findings = []
    for analysis in analyses:
        findings.extend(_dangling(subject_names, analysis))
    findings.extend(_cycles(analyses))
    return findings
