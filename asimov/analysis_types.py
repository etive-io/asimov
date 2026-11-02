"""
Analysis types (#238): what kind of analysis a blueprint makes.

Every analysis of a subject used to be built as a gravitational-wave analysis
(:class:`~asimov.analysis.GravitationalWaveTransient`), whatever its domain. A
plugin can now provide a *type*, in the way it provides a pipeline, and a type
is chosen for an analysis in this order:

1. ``type:`` on the analysis (or its blueprint), which can mix a type with any
   pipeline;
2. ``analysis_type`` on the pipeline's class, which is looked up *before* the
   analysis is built;
3. the default, ``gravitational-wave-transient``, which is what every analysis
   was before. A pipeline which declares nothing is unaffected.

A type is a class, registered by name in the ``asimov.analysis_types``
entry-point group::

    [project.entry-points."asimov.analysis_types"]
    fit-component = "my_package.types:FitComponent"

asimov registers two itself: ``simple`` (:class:`~asimov.analysis.SimpleAnalysis`,
which adds nothing of any domain) and ``gravitational-wave-transient``.

Nothing about the type is stored but ``type:`` itself, in the analysis's
metadata, and only if it was given there. So a ledger needs no migration, and
a version of asimov which does not know about types loads a typed analysis as
a gravitational-wave one, with the ``type`` as plain metadata.
"""
import logging
import os
import sys
from typing import Any, Dict, Optional

if sys.version_info < (3, 10):
    from importlib_metadata import entry_points
else:
    from importlib.metadata import entry_points

logger = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "asimov.analysis_types"

#: The type of an analysis which does not say, and whose pipeline does not.
DEFAULT_TYPE = "gravitational-wave-transient"

_registry: Optional[Dict[str, Any]] = None


class AnalysisTypeError(ValueError):
    """An analysis asks for a type which is not installed."""


def _builtin() -> Dict[str, Any]:
    from asimov.analysis import GravitationalWaveTransient, SimpleAnalysis

    found = {"simple": SimpleAnalysis, DEFAULT_TYPE: GravitationalWaveTransient}
    # (As with the testing pipelines, the toy type is only there when testing, and then
    # only when asked for, so that tests of "no extra types" are unaffected.)
    if os.environ.get("ASIMOV_TESTING") and os.environ.get("ASIMOV_TOY_STRATEGY"):
        from asimov.pipelines.testing.types import ToyStep

        found["toy-step"] = ToyStep
    return found


def analysis_types() -> Dict[str, Any]:
    """
    The analysis types which are installed, by name.

    Read once and kept (looking at entry points is not free, and this is asked
    for each analysis loaded). A plugin which fails to load is reported and left
    out, so that a broken plugin cannot break unrelated commands.
    """
    global _registry
    if _registry is None:
        found = _builtin()
        for entry in entry_points(group=ENTRY_POINT_GROUP):
            try:
                found.setdefault(entry.name, entry.load())
            except Exception as error:
                logger.warning(f"Could not load the analysis type plugin '{entry.name}': {error}")
        _registry = found
    return _registry


def reset_analysis_types() -> None:
    """Forget what was read, so that the types are looked for again."""
    global _registry
    _registry = None


def get_analysis_type(name: str):
    """
    The class of an analysis type.

    Raises
    ------
    AnalysisTypeError
        If no such type is installed; the message says which are.
    """
    available = analysis_types()
    if name not in available:
        installed = ", ".join(sorted(available))
        raise AnalysisTypeError(
            f"The analysis type '{name}' is not installed, so an analysis of that type "
            f"cannot be made. (The plugin which provides it may be missing.) "
            f"The installed types are: {installed}."
        )
    return available[name]


def declared_type(parameters: Dict[str, Any]) -> Optional[str]:
    """
    The type which a document asks for, or None if it does not say: its
    ``type:``, or else the ``analysis_type`` of the class of its pipeline.
    """
    explicit = parameters.get("type")
    if isinstance(explicit, str) and explicit:
        return explicit
    from asimov.pipelines import known_pipelines

    # (A document with a command and no pipeline is run by the command pipeline.)
    pipeline = parameters.get("pipeline") or ("command" if "command" in parameters else None)
    if isinstance(pipeline, str):
        declared = getattr(known_pipelines.get(pipeline.lower()), "analysis_type", None)
        if isinstance(declared, str) and declared:
            return declared
    return None


def analysis_class_for(parameters: Dict[str, Any]):
    """
    The class to build an analysis from, for the document which describes it.

    Raises
    ------
    AnalysisTypeError
        If the type which it asks for (or whose pipeline asks for) is not installed.
    """
    return get_analysis_type(declared_type(parameters) or DEFAULT_TYPE)


def build_analysis(parameters: Dict[str, Any], subject=None, ledger=None):
    """
    Build the analysis which a document describes, of the type it asks for.

    This is what :meth:`asimov.event.Production.from_dict` does when the type is
    not the default.
    """
    return analysis_class_for(parameters).from_dict(parameters, subject=subject, ledger=ledger)


_OPERATORS = (">=", "<=", "==", "!=", ">", "<")


def compare(value: Any, spec: Any) -> bool:
    """
    Whether a value satisfies a filter such as ``"<3"``, ``">=2"``, ``"!=5"`` or ``"4"``.

    For :meth:`asimov.analysis.Analysis.match_attribute`. Numbers are compared as
    numbers, and anything else as lower-case text (for which only ``==``, ``!=``
    and a plain value mean anything).

    Parameters
    ----------
    value
        What the analysis has.
    spec : str
        A comparison operator (``>=``, ``<=``, ``==``, ``!=``, ``>``, ``<``) and a
        value, or just a value, which means ``==``.
    """
    text = str(spec).strip()
    operator = "=="
    for candidate in _OPERATORS:
        if text.startswith(candidate):
            operator, text = candidate, text[len(candidate):].strip()
            break
    try:
        left, right = float(value), float(text)
    except (TypeError, ValueError):
        left, right = str(value).lower(), text.lower()
        if operator in ("<", "<=", ">", ">="):
            return False
    return {
        "==": left == right,
        "!=": left != right,
        ">": left > right,
        ">=": left >= right,
        "<": left < right,
        "<=": left <= right,
    }[operator]
