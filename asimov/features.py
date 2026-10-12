"""
Which features a project's ledger depends on (#231).

Some features change what a ledger *means*, not only what it holds: a version
of asimov without cross-subject ``needs`` reads ``needs: [EvB/fit]`` as a name
which matches nothing, and so starts the analysis without waiting for it. Such
a feature is recorded in the ledger when a blueprint first makes the project
use it, under ``asimov: features:``, so that the person applying can be told,
and so that a later version which meets a feature it does not know can say so.

This only warns: it never stops a ledger being used. An older version which
does not know about this cannot read the record, so the warning at the time of
applying is the one which reaches people running one.
"""
import logging
from typing import Dict, Iterable, List

logger = logging.getLogger(__name__)

#: The features a ledger can depend on, and what each means for older versions.
FEATURES: Dict[str, str] = {
    "cross-subject-needs": (
        "needs which name an analysis of another subject (subject/name) or select "
        "analyses by subject (subject:). A version without this feature ignores "
        "them, and starts the analysis without waiting"
    ),
    "subject-analysis-needs": (
        "subject analyses which have both 'analyses:' (what they combine) and 'needs:' "
        "(what they wait on). A version without this feature reads 'needs:' as what "
        "they combine, and does not wait"
    ),
}


def recorded(ledger) -> Dict[str, str]:
    """The features which a ledger records using, with the version which recorded each."""
    data = getattr(ledger, "data", None)
    section = data.get("asimov") if isinstance(data, dict) else None
    features = section.get("features") if isinstance(section, dict) else None
    return dict(features) if isinstance(features, dict) else {}


def unknown(ledger) -> List[str]:
    """The features which a ledger records using which this version does not know."""
    return sorted(name for name in recorded(ledger) if name not in FEATURES)


def missing(ledger, names: Iterable[str]) -> List[str]:
    """Of some features, those which the ledger does not yet record."""
    have = recorded(ledger)
    return sorted(name for name in set(names) if name not in have)


def record(ledger, names: Iterable[str]) -> List[str]:
    """
    Record that a ledger uses some features. Call ``ledger.save()`` to keep it.

    Returns
    -------
    list of str
        The features which were not recorded before.
    """
    import asimov

    new = missing(ledger, names)
    if new:
        section = ledger.data.setdefault("asimov", {})
        features = section.setdefault("features", {})
        for name in new:
            features[name] = asimov.__version__
    return new


def describe(name: str) -> str:
    return FEATURES.get(name, name)


def warn_unknown(ledger) -> List[str]:
    """
    Warn about features which a ledger records using that this version does not
    know, which means it was written by a newer one. Never raises.
    """
    try:
        names = unknown(ledger)
    except Exception:
        return []
    if names:
        logger.warning(
            "This project's ledger uses features this version of asimov does not know "
            f"({', '.join(names)}). It was written by a newer version, and may be read "
            "differently by this one: upgrade asimov."
        )
    return names
