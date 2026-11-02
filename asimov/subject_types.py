"""
Subject types (#238): what kind of subject a blueprint makes.

A subject is, by default, an :class:`~asimov.event.Event`, "a specific
gravitational wave event or trigger". A plugin can provide a *subject type* for
its own domain, in the way it provides an analysis type
(:mod:`asimov.analysis_types`): a subject says which with ``type:``, and a type
is a subclass of ``Event`` registered by name in the ``asimov.subject_types``
entry-point group::

    [project.entry-points."asimov.subject_types"]
    fit-component = "my_package.subjects:FitComponent"

For now a type is *display* only: it can say what its subjects are called
(``subject_noun``), which the report and the build commands then use instead of
"subject" and "event", and add its own methods. It still has the repository and
the working directory of an ``Event``. Selecting by ``type:`` is the only way
to choose a type, and nothing is stored but ``type:`` itself, in the metadata of
the subject. A version of asimov which does not know about types loads such a
subject as an ordinary ``Event`` with ``type`` as one more key of metadata, and
so does this one if the plugin which provides the type is not installed (with a
warning), so that a missing plugin cannot make a whole ledger unreadable.
Applying a subject of a type which is not installed is an error.
"""
import logging
import sys
from typing import Any, Dict, Iterable, Optional, Tuple

if sys.version_info < (3, 10):
    from importlib_metadata import entry_points
else:
    from importlib.metadata import entry_points

logger = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "asimov.subject_types"

#: The type of a subject which does not say.
DEFAULT_TYPE = "event"

_registry: Optional[Dict[str, Any]] = None
_warned = set()


class SubjectTypeError(ValueError):
    """A subject asks for a type which is not installed."""


def _builtin() -> Dict[str, Any]:
    import os

    from asimov.event import Event

    found = {DEFAULT_TYPE: Event}
    # (As with the toy analysis type, only there when testing and when asked for.)
    if os.environ.get("ASIMOV_TESTING") and os.environ.get("ASIMOV_TOY_STRATEGY"):
        from asimov.pipelines.testing.types import ToyComponent

        found["toy-component"] = ToyComponent
    return found


def subject_types() -> Dict[str, Any]:
    """
    The subject types which are installed, by name.

    Read once and kept. A plugin which fails to load is reported and left out.
    """
    global _registry
    if _registry is None:
        found = _builtin()
        for entry in entry_points(group=ENTRY_POINT_GROUP):
            try:
                found.setdefault(entry.name, entry.load())
            except Exception as error:
                logger.warning(f"Could not load the subject type plugin '{entry.name}': {error}")
        _registry = found
    return _registry


def reset_subject_types() -> None:
    """Forget what was read, so that the types are looked for again."""
    global _registry
    _registry = None
    _warned.clear()


def get_subject_type(name: str):
    """
    The class of a subject type.

    Raises
    ------
    SubjectTypeError
        If no such type is installed; the message says which are.
    """
    available = subject_types()
    if name not in available:
        installed = ", ".join(sorted(available))
        raise SubjectTypeError(
            f"The subject type '{name}' is not installed, so a subject of that type "
            f"cannot be made. (The plugin which provides it may be missing.) "
            f"The installed types are: {installed}."
        )
    return available[name]


def declared_type(document: Dict[str, Any]) -> Optional[str]:
    """The type which a subject's document asks for, or None if it does not say."""
    explicit = document.get("type")
    return explicit if isinstance(explicit, str) and explicit else None


def check(document: Dict[str, Any]) -> None:
    """
    Raise if the type which a subject's document asks for is not installed.

    Used when a subject is applied, which is when a missing type is a mistake to
    refuse; a ledger which already has one is still loaded.

    Raises
    ------
    SubjectTypeError
    """
    name = declared_type(document)
    if name is not None:
        get_subject_type(name)


def class_for(document: Dict[str, Any]):
    """
    The class to build a subject from.

    A type which is not installed gives an ordinary subject, with a warning (once
    for each such type), rather than an error: the ledger which holds it has to
    be readable.
    """
    name = declared_type(document)
    if name is None:
        return get_subject_type(DEFAULT_TYPE)
    try:
        return get_subject_type(name)
    except SubjectTypeError as error:
        if name not in _warned:
            _warned.add(name)
            logger.warning(f"{error} Subjects of that type are loaded as ordinary subjects.")
        return get_subject_type(DEFAULT_TYPE)


def noun_of(subjects: Iterable) -> Optional[Tuple[str, str]]:
    """
    What the subjects are called, as ``(singular, plural)``, if their type says.

    ``None`` if there are none, if any is of a type which does not say, or if
    they do not agree: callers then say what they always did.
    """
    nouns = set()
    for subject in subjects:
        noun = getattr(type(subject), "subject_noun", None)
        if not noun:
            return None
        plural = getattr(type(subject), "subject_noun_plural", None) or f"{noun}s"
        nouns.add((noun, plural))
    return nouns.pop() if len(nouns) == 1 else None
