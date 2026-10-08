"""
Changes to an analysis which aren't applying a blueprint: reviewing it,
commenting on it, and labelling it.

These are the functions the MCP server (:mod:`asimov.mcp_server`) calls. Each
makes its change and writes an audit record of it (see :mod:`asimov.audit`) in
the same transaction, so a change is never made without a record of who made it.

Comments are review messages without a status, which is how comments are made
by hand with ``asimov review add``. A label which has been set by a person (or
an agent) is a *manual* label: labellers (see :mod:`asimov.labellers`) don't
change it, and it stays until it is removed.
"""

from asimov.audit import append_audit, new_record
from asimov.review import STATES, ReviewMessage

__all__ = [
    "MANUAL_LABELS",
    "ActionError",
    "add_comment",
    "add_label",
    "remove_label",
    "set_review_status",
]

#: The key in an analysis's metadata which lists the labels set by hand.
MANUAL_LABELS = "manual labels"


class ActionError(ValueError):
    """The change can't be made, and the message says why."""


def _target(analysis):
    return f"{analysis.event.name}/{analysis.name}"


def _save(ledger, analysis):
    ledger.update_event(analysis.event)


def _review(ledger, analysis, message, status, action):
    if status is not None and str(status).upper() not in STATES:
        raise ActionError(
            f"{status!r} is not a review status: use one of {', '.join(sorted(STATES))}."
        )
    if status is None and not (message and str(message).strip()):
        raise ActionError("There is nothing to add: give a message, a status, or both.")
    status = str(status).upper() if status is not None else None
    with ledger.transaction():
        analysis.review.add(ReviewMessage(message=message, status=status, production=analysis))
        _save(ledger, analysis)
        record = append_audit(
            ledger,
            new_record(
                action,
                "review",
                _target(analysis),
                content={"status": status, "message": message},
                outcome="added",
            ),
        )
    return record


def set_review_status(ledger, analysis, status, message=None):
    """
    Give an analysis a review status, with a message if there is one.

    Parameters
    ----------
    ledger : Ledger
    analysis : Analysis
    status : str
        One of the review states, e.g. ``"APPROVED"``.
    message : str, optional

    Returns
    -------
    AuditRecord

    Raises
    ------
    ActionError
        If ``status`` isn't a review state.
    """
    if status is None:
        raise ActionError("A status is needed.")
    return _review(ledger, analysis, message, status, "review")


def add_comment(ledger, analysis, message):
    """
    Add a comment to an analysis's review. This doesn't change its status.

    Returns
    -------
    AuditRecord

    Raises
    ------
    ActionError
        If the comment is empty.
    """
    if not (message and str(message).strip()):
        raise ActionError("The comment is empty.")
    return _review(ledger, analysis, message, None, "comment")


def _labels(analysis):
    labels = analysis.meta.get("labels")
    if not isinstance(labels, dict):
        labels = analysis.meta["labels"] = {}
    return labels


def add_label(ledger, analysis, name, value=True):
    """
    Set a label on an analysis, which stays until it is removed.

    Labellers don't change or remove a label set this way, even if they would
    set a label with the same name.

    Returns
    -------
    AuditRecord

    Raises
    ------
    ActionError
        If the name is empty.
    """
    name = str(name).strip()
    if not name:
        raise ActionError("A label needs a name.")
    with ledger.transaction():
        labels = _labels(analysis)
        before = labels.get(name)
        labels[name] = value
        manual = analysis.meta.setdefault(MANUAL_LABELS, [])
        if name not in manual:
            manual.append(name)
        _save(ledger, analysis)
        record = append_audit(
            ledger,
            new_record(
                "label",
                "label",
                _target(analysis),
                content={"label": name, "value": value, "previous": before},
                outcome="added" if before is None else "updated",
            ),
        )
    return record


def remove_label(ledger, analysis, name):
    """
    Remove a label from an analysis, whoever set it.

    A label a labeller sets can come back the next time the labeller runs.

    Returns
    -------
    AuditRecord

    Raises
    ------
    ActionError
        If the analysis doesn't have the label.
    """
    labels = _labels(analysis)
    if name not in labels:
        raise ActionError(f"{_target(analysis)} has no label {name!r}.")
    with ledger.transaction():
        before = labels.pop(name)
        manual = analysis.meta.get(MANUAL_LABELS, [])
        if name in manual:
            manual.remove(name)
        _save(ledger, analysis)
        record = append_audit(
            ledger,
            new_record(
                "label",
                "label",
                _target(analysis),
                content={"label": name, "previous": before},
                outcome="removed",
            ),
        )
    return record
