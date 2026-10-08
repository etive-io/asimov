"""
Reading a project: its subjects, their analyses, and what is known of each.

These functions take the objects from a ledger and give back plain data
(dictionaries, lists, strings), so that the command line, the REST API and the
MCP server (:mod:`asimov.mcp_server`) describe a project the same way. They only
read: nothing here changes a ledger.

"Subject" is the term for what an analysis is of, which for gravitational-wave
analyses is an event.
"""

import json
import os

__all__ = [
    "NotFound",
    "subject_names",
    "analysis_detail",
    "analysis_summary",
    "find_analysis",
    "find_subject",
    "labels",
    "plain",
    "read_logs",
    "read_telemetry",
    "review_summary",
    "subject_detail",
    "subject_summary",
]


class NotFound(LookupError):
    """There is no subject or analysis with that name."""


def plain(value):
    """``value`` as plain JSON data, with anything which isn't turned into text."""
    return json.loads(json.dumps(value, default=str))


def subject_names(ledger):
    """
    The names of the subjects in a ledger, in order, without building them.

    Building a subject builds each of its analyses, so this is the way to list
    a large project cheaply.
    """
    database = getattr(ledger, "db", None)
    if database is None:
        return sorted(ledger.events)
    return sorted(row["name"] for row in database.query("event"))


def find_subject(ledger, name):
    """
    The subject called ``name``.

    Raises
    ------
    NotFound
        If there is no such subject.
    """
    try:
        subjects = ledger.get_event(name)
    except (KeyError, ValueError):
        subjects = []
    if not subjects:
        raise NotFound(f"There is no subject called {name!r}.")
    return subjects[0]


def find_analysis(subject, name):
    """
    The analysis called ``name`` on ``subject``.

    Raises
    ------
    NotFound
        If there is no such analysis.
    """
    for analysis in subject.productions:
        if analysis.name == name:
            return analysis
    raise NotFound(f"There is no analysis called {name!r} on {subject.name!r}.")


def _review_status(analysis):
    review = getattr(analysis, "review", None)
    return review.status if review else None


def _pipeline_name(analysis):
    pipeline = getattr(analysis, "pipeline", None)
    return getattr(pipeline, "name", None) or (str(pipeline) if pipeline else None)


def analysis_summary(analysis):
    """One line's worth about an analysis: where it is and what is said of it."""
    return {
        "subject": analysis.event.name,
        "name": analysis.name,
        "pipeline": _pipeline_name(analysis),
        "status": str(analysis.status),
        "review": _review_status(analysis),
    }


def analysis_detail(analysis):
    """Everything the ledger holds about an analysis, as plain data."""
    return plain(analysis.to_dict(event=False))


def subject_summary(subject):
    """One line's worth about a subject: how many analyses it has, in which states."""
    states = {}
    for analysis in subject.productions:
        state = str(analysis.status)
        states[state] = states.get(state, 0) + 1
    return {
        "name": subject.name,
        "analyses": len(subject.productions),
        "statuses": states,
    }


def subject_detail(subject):
    """A subject's own settings, and a summary of each of its analyses."""
    detail = plain(subject.to_dict(productions=False))
    detail.pop("ledger", None)
    return {
        "name": subject.name,
        "settings": detail,
        "analyses": [analysis_summary(a) for a in subject.productions],
    }


def review_summary(analysis):
    """The review status of an analysis, and the messages which led to it."""
    review = getattr(analysis, "review", None)
    return {
        "status": _review_status(analysis),
        "messages": plain(review.to_dicts()) if review else [],
    }


def labels(analysis):
    """The labels on an analysis, by name."""
    return plain(getattr(analysis, "meta", {}).get("labels", {}) or {})


def read_logs(analysis, max_bytes=20_000, max_files=20):
    """
    The log files an analysis has written, each cut to its last ``max_bytes``.

    Parameters
    ----------
    analysis : Analysis
    max_bytes : int
        The most to give of each file, taken from the end.
    max_files : int
        The most files to give.

    Returns
    -------
    dict
        ``files``: a list of ``{"name", "text", "truncated"}``, and
        ``omitted``, how many files were left out for want of room.
    """
    pipeline = getattr(analysis, "pipeline", None)
    collect = getattr(pipeline, "collect_logs", None)
    logs = collect() if collect is not None else {}
    files = []
    for name in sorted(logs)[:max_files]:
        text = logs[name]
        data = text.encode("utf-8", errors="replace")
        truncated = len(data) > max_bytes
        if truncated:
            text = data[-max_bytes:].decode("utf-8", errors="replace")
        files.append({"name": name, "text": text, "truncated": truncated})
    return {"files": files, "omitted": max(0, len(logs) - max_files)}


def read_telemetry(analysis, event_type=None, since=None):
    """
    The telemetry events recorded for an analysis, oldest first.

    Read live from the analysis's ``telemetry.jsonl`` in its run directory,
    where the built-in local telemetry sink writes them. Lines which aren't
    JSON are skipped.

    Parameters
    ----------
    event_type : str, optional
        Only events of this type.
    since : str, optional
        Only events with a timestamp at or after this ISO 8601 time (compared
        as text, which is right for ISO 8601).

    Raises
    ------
    OSError
        If the file exists but can't be read.
    """
    try:
        rundir = analysis.rundir
    except Exception:
        rundir = None
    events = []
    path = os.path.join(rundir, "telemetry.jsonl") if rundir else None
    if path and os.path.isfile(path):
        with open(path, "r") as telemetry_file:
            for line in telemetry_file:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    if event_type:
        events = [e for e in events if e.get("event_type") == event_type]
    if since:
        events = [e for e in events if e.get("timestamp", "") >= since]
    return events
