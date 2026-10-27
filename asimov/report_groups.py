"""
A view in the report of the analyses which strategies made (#235).

Analyses are grouped by the id which core stamps on them (``meta.strategy.id``,
see :mod:`asimov.strategies`). Each group has a panel with its strategy, how
many of its analyses are in each status, and its members. If the blueprint that
made the group names two metadata keys, the panel also has a matrix with one
cell per analysis, placed by the two keys and coloured by status::

    kind: analysis
    name: globalfit
    strategy:
      type: round-robin
      rounds: 12
    report:
      rows: stream
      columns: round

Nothing here needs the strategy's code: any strategy which records, say,
``round`` and ``stream`` on its analyses gets the matrix. A key may be dotted
(``likelihood.minimum frequency``) to reach into a nested mapping.
"""
import html
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from asimov.groups import Member, summary
from asimov.strategies import strategy_stamp

#: The bootstrap-like colour class of each status, for the cells and chips.
#: (Anything else is drawn as ``other``.)
STATUS_CLASS = {
    "ready": "ready",
    "wait": "wait",
    "restart": "ready",
    "running": "running",
    "processing": "running",
    "finished": "done",
    "complete": "done",
    "uploaded": "done",
    "stuck": "stuck",
    "stop": "stopped",
    "stopped": "stopped",
    "cancelled": "stopped",
    "manual": "wait",
}

STYLE = """
<style>
.asimov-groups { margin: 1rem; }
.group-panel { background: white; border: 1px solid #e1e4e8; padding: 1rem; margin-bottom: 1.5rem;
               box-shadow: 0 1px 3px rgba(0,0,0,0.12); }
.group-panel h4 small { color: #586069; font-size: 0.7em; margin-left: 0.5rem; }
.group-status-btn { border: 1px solid #c6cbd1; background: white; border-radius: 1rem; padding: 0 0.6rem;
                    margin: 0 0.3rem 0.3rem 0; font-size: 0.8rem; cursor: pointer; }
.group-status-btn.active { box-shadow: 0 0 0 2px #0366d6; }
.group-matrix { border-collapse: separate; border-spacing: 2px; margin-top: 0.5rem; }
.group-matrix th { font-weight: 600; font-size: 0.75rem; padding: 0 0.4rem; white-space: nowrap; }
.group-matrix td { min-width: 1.6rem; height: 1.6rem; padding: 0; text-align: center; background: #f6f8fa; }
.group-cell { display: inline-block; width: 1.4rem; height: 1.4rem; border-radius: 3px; margin: 1px;
              cursor: pointer; vertical-align: middle; }
.group-cell.s-ready { background: #b1bac4; }
.group-cell.s-wait { background: #e1e4e8; }
.group-cell.s-running { background: #0366d6; }
.group-cell.s-done { background: #2ea44f; }
.group-cell.s-stuck { background: #d73a49; }
.group-cell.s-stopped { background: #6a737d; }
.group-cell.s-other { background: #d4a72c; }
.group-cell.dimmed { opacity: 0.15; }
.group-members a { margin-right: 0.8rem; }
</style>
"""

SCRIPT = """
<script>
(function () {
    var byKey = null;
    function modalFor(key) {
        if (!byKey) {
            byKey = {};
            document.querySelectorAll('[data-analysis-key]').forEach(function (el) {
                byKey[el.getAttribute('data-analysis-key')] = el.id;
            });
        }
        return byKey[key];
    }
    document.addEventListener('click', function (event) {
        var cell = event.target.closest('.group-cell');
        if (cell) {
            event.preventDefault();
            var id = modalFor(cell.getAttribute('data-key'));
            if (id && typeof openAnalysisModal === 'function') { openAnalysisModal(id); }
            return;
        }
        var button = event.target.closest('.group-status-btn');
        if (button) {
            var panel = button.closest('.group-panel');
            var wanted = button.classList.contains('active') ? null : button.getAttribute('data-status');
            panel.querySelectorAll('.group-status-btn').forEach(function (b) {
                b.classList.toggle('active', wanted !== null && b === button);
            });
            panel.querySelectorAll('.group-cell').forEach(function (c) {
                c.classList.toggle('dimmed', wanted !== null && c.getAttribute('data-status') !== wanted);
            });
        }
    });
})();
</script>
"""


def lookup(meta: Any, path: str) -> Optional[str]:
    """
    The value at a (dotted) key of an analysis's metadata, as a string, or None
    if it is not there. The whole key is tried first, so a key which has a dot
    in it still works.
    """
    if not isinstance(meta, dict):
        return None
    if path in meta:
        value = meta[path]
    else:
        value = meta
        for part in path.split("."):
            if not isinstance(value, dict) or part not in value:
                return None
            value = value[part]
    if value is None or isinstance(value, (dict, list)):
        return None
    return str(value)


def build_matrix(members: Iterable[Member], rows: str, columns: str) -> Dict[str, Any]:
    """
    Place analyses in a grid by two metadata keys.

    Returns
    -------
    dict
        ``rows`` and ``columns`` (the values found, in natural order),
        ``cells`` (``{(row, column): [Member, ...]}``; a combination which no
        analysis has is absent), and ``unplaced``, the members which lack
        either key.
    """
    cells: Dict[Tuple[str, str], List[Member]] = {}
    unplaced = []
    for member in members:
        meta = getattr(member.analysis, "meta", None)
        row, column = lookup(meta, rows), lookup(meta, columns)
        if row is None or column is None:
            unplaced.append(member)
            continue
        cells.setdefault((row, column), []).append(member)
    return {
        "rows": sorted({r for r, _ in cells}, key=_natural_key),
        "columns": sorted({c for _, c in cells}, key=_natural_key),
        "cells": cells,
        "unplaced": unplaced,
    }


def _natural_key(value: str):
    """Sort numbers as numbers, then words, with numbers inside words in order (r2 before r10)."""
    if re.fullmatch(r"-?\d+(\.\d+)?", value):
        return (0, float(value), [])
    return (1, 0.0, [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", value)])


def find_groups(subjects: Iterable, project_analyses: Iterable = ()) -> Dict[str, Dict[str, Any]]:
    """
    The groups among some subjects' analyses (and project analyses).

    Returns
    -------
    dict
        ``{id: {"type": ..., "members": [Member, ...]}}``, in order of id.
        Analyses which no strategy made are not in any group.
    """
    found: Dict[str, Dict[str, Any]] = {}

    def add(analysis, subject_name):
        stamp = strategy_stamp(getattr(analysis, "meta", None) or {})
        if stamp:
            group = found.setdefault(str(stamp["id"]), {"type": str(stamp["type"]), "members": []})
            group["members"].append(Member(analysis, subject_name))

    for subject in subjects:
        for analysis in subject.productions:
            add(analysis, subject.name)
    for analysis in project_analyses:
        add(analysis, None)
    return dict(sorted(found.items()))


def _settings(record: Optional[dict]) -> Tuple[Optional[str], Optional[str]]:
    """The two keys which the blueprint's ``report:`` names, if it names both."""
    report = ((record or {}).get("blueprint") or {}).get("report")
    if not isinstance(report, dict):
        return None, None
    rows, columns = report.get("rows"), report.get("columns")
    if isinstance(rows, str) and isinstance(columns, str) and rows and columns:
        return rows, columns
    return None, None


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _cell(member: Member) -> str:
    status = member.status
    return (
        f'<a href="#" class="group-cell s-{STATUS_CLASS.get(status, "other")}" '
        f'data-status="{_esc(status)}" data-key="{_esc(member.label)}" '
        f'title="{_esc(member.label)}: {_esc(status)}"></a>'
    )


def _matrix_html(matrix: Dict[str, Any], rows: str, columns: str) -> str:
    cells = matrix["cells"]
    out = [f'<table class="group-matrix"><thead><tr><th>{_esc(rows)} \\ {_esc(columns)}</th>']
    out += [f"<th>{_esc(c)}</th>" for c in matrix["columns"]]
    out.append("</tr></thead><tbody>")
    for row in matrix["rows"]:
        out.append(f"<tr><th>{_esc(row)}</th>")
        for column in matrix["columns"]:
            out.append("<td>" + "".join(_cell(m) for m in cells.get((row, column), [])) + "</td>")
        out.append("</tr>")
    out.append("</tbody></table>")
    if matrix["unplaced"]:
        n = len(matrix["unplaced"])
        out.append(
            f'<p class="text-muted">{n} {"analysis has" if n == 1 else "analyses have"} '
            f"no {_esc(rows)} or no {_esc(columns)}, and {'is' if n == 1 else 'are'} not in the grid.</p>"
        )
    return "".join(out)


def panel_html(identifier: str, kind: str, members: List[Member], record: Optional[dict] = None) -> str:
    """The panel of one group."""
    counts: Dict[str, int] = {}
    for member in members:
        counts[member.status] = counts.get(member.status, 0) + 1

    out = [f'<div class="group-panel" id="group-{_esc(identifier)}">']
    out.append(f"<h4>{_esc(identifier)}<small>{_esc(kind)}</small></h4>")
    out.append(f"<p>{_esc(summary(members))}</p>")
    out.append("<div>")
    for status, number in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0])):
        out.append(
            f'<button type="button" class="group-status-btn" data-status="{_esc(status)}">'
            f"{_esc(status)} {number}</button>"
        )
    out.append("</div>")

    rows, columns = _settings(record)
    if rows and columns:
        out.append(_matrix_html(build_matrix(members, rows, columns), rows, columns))

    out.append(f'<details class="group-members"><summary>Analyses ({len(members)})</summary><p>')
    for member in sorted(members, key=lambda m: m.label):
        target = f"#card-{_esc(member.subject)}" if member.subject else "#"
        out.append(f'<a href="{target}">{_esc(member.label)} <small>[{_esc(member.status)}]</small></a>')
    out.append("</p></details></div>")
    return "".join(out)


def groups_html(subjects: Iterable, project_analyses: Iterable = (), read_record=None) -> str:
    """
    The section of the report for the groups, or ``""`` if there are none.

    Parameters
    ----------
    subjects : iterable of Event
    project_analyses : iterable of ProjectAnalysis
    read_record : callable, optional
        ``read_record(identifier)`` gives the record of a group (see
        :func:`asimov.strategies.read_group`), which holds the blueprint and so
        the settings of its matrix.
    """
    found = find_groups(subjects, project_analyses)
    if not found:
        return ""
    out = ["<div class='asimov-groups'><h3>Strategy groups</h3>", STYLE]
    for identifier, group in found.items():
        record = None
        if read_record is not None:
            try:
                record = read_record(identifier)
            except Exception:
                record = None
        out.append(panel_html(identifier, group["type"], group["members"], record))
    out.append(SCRIPT)
    out.append("</div>")
    return "".join(out)
