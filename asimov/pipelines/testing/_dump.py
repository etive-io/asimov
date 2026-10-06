"""
Ledger dumps for asimov's bundled testing pipelines.

The testing pipelines exist so that end-to-end runs can check what asimov
hands a pipeline. Each pipeline writes a ``ledger_dump.json`` into its run
directory when its DAG is built, recording everything the ledger makes
available to that analysis at that moment:

* the analysis's own ledger entry and effective settings,
* the subject (event) it belongs to,
* every other analysis it can see, with its status, the files in its run
  directory, and the assets its pipeline reports, marking which of them the
  analysis actually depends on,
* for subject and project analyses, the analyses they encompass.

The dump is built when the DAG is built, because that is when asimov (rather
than the job on the cluster) has access to the ledger. It therefore shows what
the analysis could see at submission time.
"""

import json
import os
from datetime import datetime

#: Name of the dump written into each analysis's run directory.
DUMP_FILENAME = "ledger_dump.json"

#: Bump when the layout of the dump changes.
DUMP_VERSION = 1

# Keys that hold live objects (or would recurse into the whole ledger) rather
# than data, and so are left out of the dumped settings.
_SKIPPED_KEYS = {"ledger", "repository", "productions", "event"}


def _plain(value):
    """
    Convert ``value`` into something ``json`` can serialise, without following
    references to live objects such as the ledger or the event repository.
    """
    if isinstance(value, dict):
        return {
            str(key): _plain(item)
            for key, item in value.items()
            if key not in _SKIPPED_KEYS
        }
    if isinstance(value, (list, tuple, set)):
        return [_plain(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _run_files(rundir, exclude=()):
    """List the files below ``rundir`` as ``{"path": ..., "size": ...}``."""
    if not rundir or not os.path.isdir(rundir):
        return []
    files = []
    for root, _, names in os.walk(rundir):
        for name in sorted(names):
            path = os.path.join(root, name)
            relative = os.path.relpath(path, rundir)
            if relative in exclude:
                continue
            try:
                size = os.path.getsize(path)
            except OSError:
                size = None
            files.append({"path": relative, "size": size})
    return sorted(files, key=lambda item: item["path"])


def _assets(analysis):
    """The assets ``analysis``'s pipeline reports, or ``{}`` if it can't say."""
    pipeline = getattr(analysis, "pipeline", None)
    collect = getattr(pipeline, "collect_assets", None)
    if collect is None:
        return {}
    try:
        return _plain(collect() or {})
    except Exception as exc:  # a dump must never stop a DAG being built
        return {"error": f"{type(exc).__name__}: {exc}"}


def _subject_name(analysis):
    event = getattr(analysis, "event", None)
    return getattr(event, "name", None)


def describe_analysis(analysis, dependencies=()):
    """
    Summarise an analysis: what it is, its state, and what it has produced.

    Parameters
    ----------
    analysis : :class:`asimov.analysis.Analysis`
        The analysis to describe.
    dependencies : iterable of str
        Names of the analyses the *dumping* analysis depends on. If
        ``analysis.name`` is among them the summary is marked
        ``"dependency": true``.

    Returns
    -------
    dict
    """
    pipeline = getattr(analysis, "pipeline", None)
    rundir = getattr(analysis, "rundir", None)
    review = getattr(analysis, "review", None)
    return {
        "name": analysis.name,
        "subject": _subject_name(analysis),
        "kind": type(analysis).__name__,
        "pipeline": getattr(pipeline, "name", None) or str(pipeline),
        "status": getattr(analysis, "status", None),
        "review status": getattr(review, "status", None),
        "run directory": str(rundir) if rundir else None,
        "dependency": analysis.name in set(dependencies),
        "files": _run_files(rundir, exclude=(DUMP_FILENAME,)),
        "assets": _assets(analysis),
    }


def _dependency_names(analysis):
    try:
        return [str(getattr(dep, "name", dep)) for dep in analysis.dependencies]
    except Exception:  # resolving dependencies can fail on a half-built ledger
        return []


def _subjects_of(analysis):
    """The subject (event) objects an analysis operates on."""
    subjects = getattr(analysis, "subjects", None)
    if subjects:
        return list(subjects)
    event = getattr(analysis, "event", None)
    return [event] if event is not None else []


def _visible_analyses(analysis, dependencies):
    """Every other analysis on the subjects ``analysis`` can see."""
    seen = []
    for subject in _subjects_of(analysis):
        for other in getattr(subject, "analyses", []):
            if other is analysis or (
                other.name == analysis.name
                and _subject_name(other) == _subject_name(analysis)
            ):
                continue
            seen.append(describe_analysis(other, dependencies))
    return seen


def _subject_settings(subject):
    return {
        "name": getattr(subject, "name", str(subject)),
        "settings": _plain(getattr(subject, "meta", {})),
    }


def encompassed_analyses(production):
    """
    The analyses a subject or project analysis combines.

    These come from its resolved ``analyses:`` filter (a ``SubjectAnalysis`` or
    ``ProjectAnalysis``) and from its ``needs:`` dependencies, which is how a
    plain analysis running a combining pipeline names its inputs.

    Returns
    -------
    list of :class:`asimov.analysis.Analysis`
    """
    dependencies = _dependency_names(production)
    found = {}
    for other in getattr(production, "analyses", None) or []:
        found[(_subject_name(other), other.name)] = other
    if dependencies:
        for subject in _subjects_of(production):
            for other in getattr(subject, "analyses", []):
                if other.name in dependencies:
                    found.setdefault((_subject_name(other), other.name), other)
    return list(found.values())


def ledger_dump(production, combines=False):
    """
    Collect everything the ledger makes available to ``production``.

    Parameters
    ----------
    production : :class:`asimov.analysis.Analysis`
        A simple, subject or project analysis.
    combines : bool
        Whether the analysis combines others (a subject or project analysis).
        If so the dump lists the analyses it encompasses, whether it names them
        with ``analyses:`` or with ``needs:``.

    Returns
    -------
    dict
        A JSON-serialisable description; see the module docstring.
    """
    dependencies = _dependency_names(production)
    subjects = _subjects_of(production)
    encompassed = None
    if combines:
        encompassed = [
            describe_analysis(other, dependencies)
            for other in encompassed_analyses(production)
        ]

    dump = {
        "version": DUMP_VERSION,
        "generated": datetime.now().isoformat(timespec="seconds"),
        "analysis": {
            "name": production.name,
            "kind": type(production).__name__,
            "pipeline": getattr(production.pipeline, "name", None),
            "status": getattr(production, "status", None),
            "run directory": str(production.rundir) if production.rundir else None,
            "dependencies": dependencies,
            "ledger entry": _plain(production.to_dict()),
            "effective settings": _plain(production.meta),
        },
        "subjects": [_subject_settings(subject) for subject in subjects],
        "visible analyses": _visible_analyses(production, dependencies),
    }
    if encompassed is not None:
        dump["encompassed analyses"] = encompassed
    return dump


def write_ledger_dump(production, directory=None, combines=False):
    """
    Write ``production``'s ledger dump to ``ledger_dump.json``.

    Parameters
    ----------
    production : :class:`asimov.analysis.Analysis`
        The analysis to dump.
    directory : str, optional
        Where to write it. Defaults to the analysis's run directory.
    combines : bool
        See :func:`ledger_dump`.

    Returns
    -------
    str or None
        The path written, or ``None`` if there was nowhere to write it.
    """
    directory = directory or production.rundir
    if not directory:
        return None
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, DUMP_FILENAME)
    with open(path, "w") as handle:
        json.dump(ledger_dump(production, combines=combines), handle, indent=2, sort_keys=True)
        handle.write("\n")
    return path


def analysis_lines(analyses):
    """
    Comment lines listing ``analyses``, for a pipeline's results file.

    Parameters
    ----------
    analyses : iterable of :class:`asimov.analysis.Analysis`

    Returns
    -------
    list of str
        Newline-terminated lines.
    """
    analyses = list(analyses)
    lines = [f"# Number of analyses combined: {len(analyses)}\n"]
    for index, analysis in enumerate(analyses, start=1):
        lines.append(
            f"# Analysis {index}: {_subject_name(analysis)}/{analysis.name} "
            f"({getattr(analysis.pipeline, 'name', analysis.pipeline)}, "
            f"{getattr(analysis, 'status', None)})\n"
        )
    return lines
