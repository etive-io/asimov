"""
Strategy expansion for asimov blueprints.

This module provides functionality to expand strategy definitions in blueprints
into multiple analyses, similar to GitHub Actions matrix strategies.

There are two kinds of strategy:

* A **matrix** strategy varies parameters across otherwise identical analyses
  (``strategy: {waveform.approximant: [...]}``).
* A **plugin** strategy (``strategy: {type: <name>, ...}``) is a named strategy
  provided by a plugin, which expands the blueprint into a graph of analyses
  which differ in role and depend on each other. See :class:`Strategy`.
"""

import logging
import sys
from abc import ABC, abstractmethod
from copy import deepcopy
from typing import Any, Dict, List, Optional
import itertools

if sys.version_info < (3, 10):
    from importlib_metadata import entry_points
else:
    from importlib.metadata import entry_points

logger = logging.getLogger(__name__)

#: The entry-point group which plugins register their strategies in.
ENTRY_POINT_GROUP = "asimov.strategies"

#: The kinds of document which a strategy may return, as they are written in a
#: blueprint (lower case). A strategy cannot change the project's configuration.
ALLOWED_KINDS = frozenset({"analysis", "projectanalysis", "event", "subject"})

#: The kinds which are marked with the strategy which made them. A subject is
#: not, because the settings of a subject are inherited by every analysis in it,
#: which would then look as if the strategy had made all of them.
STAMPED_KINDS = frozenset({"analysis", "projectanalysis"})


class StrategyError(ValueError):
    """A strategy could not be expanded."""


class StrategyContext:
    """
    What a strategy may know about the project it expands a blueprint in.

    This is read-only: strategies return documents, and asimov applies them
    through the normal route, so existing validation, provenance and the
    ledger are not the plugin's concern.

    Parameters
    ----------
    ledger : asimov.ledger.Ledger, optional
        The project's ledger. Without one the project is empty.
    event : str, optional
        The subject the blueprint is being applied to, if it is known.
    logger : logging.Logger, optional
        The logger to use; defaults to this module's.
    """

    def __init__(self, ledger=None, event=None, logger=None):
        self._ledger = ledger
        self.event = event
        self.logger = logger or globals()["logger"]

    def subjects(self) -> List[str]:
        """The names of the subjects which exist in the project."""
        names = getattr(self._ledger, "subject_names", None)
        return list(names()) if names else []

    def analyses(self, subject: Optional[str] = None) -> List[str]:
        """
        The names of the analyses which exist in a subject.

        Parameters
        ----------
        subject : str, optional
            The subject; defaults to the one the blueprint is applied to.
        """
        subject = subject or self.event
        if self._ledger is None or subject is None:
            return []
        from asimov.cli.application import _raw_production_names

        return sorted(_raw_production_names(self._ledger, subject))

    def has_analysis(self, subject: str, name: str) -> bool:
        """Whether an analysis of this name exists in a subject."""
        return name in self.analyses(subject)

    @property
    def project(self) -> Dict[str, Any]:
        """A copy of the project's settings."""
        data = getattr(self._ledger, "data", None) or {}
        return deepcopy(data.get("project", {})) if isinstance(data, dict) else {}


class Strategy(ABC):
    """
    A strategy which a plugin provides, to expand a blueprint into a graph.

    Register one in the ``asimov.strategies`` entry-point group::

        [project.entry-points."asimov.strategies"]
        round-robin = "my_package.strategies:RoundRobinStrategy"

    and select it in a blueprint with ``strategy: {type: round-robin, ...}``.

    Attributes
    ----------
    name : str
        The name which blueprints select it by (the entry-point name).
    """

    name: str = ""

    def validate(self, spec: Dict[str, Any]) -> None:
        """
        Raise early, at apply time, if the strategy's options are bad.

        Parameters
        ----------
        spec : dict
            The ``strategy:`` block of the blueprint, ``type`` included.
        """

    @abstractmethod
    def expand(self, blueprint: Dict[str, Any], context: StrategyContext) -> List[Dict[str, Any]]:
        """
        Expand a blueprint into the documents to apply.

        Parameters
        ----------
        blueprint : dict
            The blueprint, ``strategy`` block included. It is a copy, which
            may be changed.
        context : StrategyContext
            Read-only information about the project.

        Returns
        -------
        list of dict
            The documents to apply, in the order to apply them (a subject
            before the analyses which are in it). Each has a ``kind``, which
            is ``analysis`` if left out, and may be ``analysis``,
            ``projectanalysis`` or ``subject`` (``event`` also works). Each
            needs a ``name``, which must be the same every time this is called
            for the same blueprint (so that applying it again is safe).
            Analyses need a ``pipeline``, may have ``needs`` to depend on the
            others, and say which subject they are for in ``event``: if they
            do not, it is the one the blueprint is applied to.
        """

    def extend(self, analysis, context: StrategyContext) -> List[Dict[str, Any]]:
        """
        Optionally, return further documents when one of the analyses finishes.

        Not used yet; the default adds nothing.
        """
        return []


def strategy_plugins() -> Dict[str, Any]:
    """
    The strategies which plugins have registered, by name.

    A plugin which fails to load is reported and left out, so that a broken
    plugin cannot break unrelated commands.
    """
    found = {}
    for entry in entry_points(group=ENTRY_POINT_GROUP):
        try:
            found[entry.name] = entry.load()
        except Exception as error:
            logger.warning(f"Could not load the strategy plugin '{entry.name}': {error}")
    return found


def is_plugin_strategy(strategy: Any) -> bool:
    """
    Whether a ``strategy`` block selects a plugin strategy.

    That is a mapping with a ``type`` whose value is a string. A matrix
    strategy has only lists as values, and a value which is not a list is an
    error there, so no matrix strategy can look like this.
    """
    return isinstance(strategy, dict) and isinstance(strategy.get("type"), str)


def strategy_stamp(document: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """
    The ``{type, id}`` which core stamps on analyses emitted by a plugin
    strategy, or None for any other document.
    """
    stamp = document.get("strategy") if isinstance(document, dict) else None
    if isinstance(stamp, dict) and "type" in stamp and "id" in stamp:
        return stamp
    return None


def set_nested_value(dictionary: Dict[str, Any], path: str, value: Any) -> None:
    """
    Set a value in a nested dictionary using dot notation.
    
    Parameters
    ----------
    dictionary : dict
        The dictionary to modify
    path : str
        The path to the value using dot notation (e.g., "waveform.approximant")
    value : Any
        The value to set
        
    Examples
    --------
    >>> d = {}
    >>> set_nested_value(d, "waveform.approximant", "IMRPhenomXPHM")
    >>> d
    {'waveform': {'approximant': 'IMRPhenomXPHM'}}
    
    Raises
    ------
    TypeError
        If an intermediate key exists but is not a dictionary
    """
    keys = path.split(".")
    current = dictionary
    
    for key in keys[:-1]:
        if key not in current:
            current[key] = {}
        elif not isinstance(current[key], dict):
            raise TypeError(
                f"Cannot set nested value for path '{path}': "
                f"intermediate key '{key}' is of type "
                f"{type(current[key]).__name__}, expected dict."
            )
        current = current[key]
    
    current[keys[-1]] = value


def expand_strategy(
    blueprint: Dict[str, Any], context: Optional[StrategyContext] = None
) -> List[Dict[str, Any]]:
    """
    Expand a blueprint with a strategy into multiple blueprints.
    
    A strategy allows you to create multiple similar analyses by specifying
    parameter variations. This is similar to GitHub Actions matrix strategies.
    
    Parameters
    ----------
    blueprint : dict
        The blueprint document, which may contain a 'strategy' field
    context : StrategyContext, optional
        What a plugin strategy may know about the project. Not used by a
        matrix strategy.

    Returns
    -------
    list
        A list of expanded blueprint documents. If no strategy is present,
        returns a list containing only the original blueprint.
        
    Examples
    --------
    A blueprint with a strategy:
    
    >>> blueprint = {
    ...     'kind': 'analysis',
    ...     'name': 'bilby-{waveform.approximant}',
    ...     'pipeline': 'bilby',
    ...     'strategy': {
    ...         'waveform.approximant': ['IMRPhenomXPHM', 'SEOBNRv4PHM']
    ...     }
    ... }
    >>> expanded = expand_strategy(blueprint)
    >>> len(expanded)
    2
    >>> expanded[0]['waveform']['approximant']
    'IMRPhenomXPHM'
    >>> expanded[1]['waveform']['approximant']
    'SEOBNRv4PHM'
    
    Notes
    -----
    - The 'strategy' field is removed from the expanded blueprints
    - Parameter names can use dot notation for nested values
    - Name templates can reference strategy parameters using {parameter_name}
      where parameter_name is the full parameter path (e.g., {waveform.approximant})
    - Multiple strategy parameters create a cross-product (matrix)
    - If multiple parameters have the same final component (e.g., 
      waveform.frequency and sampler.frequency), the behavior is undefined
      and should be avoided
    """
    if "strategy" not in blueprint:
        return [blueprint]

    if is_plugin_strategy(blueprint["strategy"]):
        return expand_plugin_strategy(blueprint, context)

    # Create a copy to avoid modifying the original
    blueprint = deepcopy(blueprint)
    strategy = blueprint.pop("strategy")
    
    # Validate strategy parameters
    if not strategy:
        raise ValueError("Strategy is defined but empty")
    
    # Get all parameter combinations
    param_names = list(strategy.keys())
    param_values = list(strategy.values())
    
    # Validate that all strategy values are lists or iterables
    for param_name, values in zip(param_names, param_values):
        if not isinstance(values, (list, tuple)):
            raise TypeError(
                f"Strategy parameter '{param_name}' must be a list, "
                f"got {type(values).__name__}. "
                f"Did you mean: {param_name}: [{values}]?"
            )
        if len(values) == 0:
            raise ValueError(
                f"Strategy parameter '{param_name}' has an empty list. "
                f"Each parameter must have at least one value."
            )
    
    # Create all combinations (cross product)
    combinations = list(itertools.product(*param_values))
    
    expanded_blueprints = []
    
    for combination in combinations:
        # Create a copy of the blueprint for this combination
        new_blueprint = deepcopy(blueprint)
        
        # Build a context for name formatting
        # The context uses the fully qualified parameter name as the key
        context = {}
        for param_name, value in zip(param_names, combination):
            # Use the full parameter path for name templates
            context[param_name] = value
        
        # Apply the parameter values to the blueprint
        for param_name, value in zip(param_names, combination):
            set_nested_value(new_blueprint, param_name, value)
        
        # Expand the name template if it contains placeholders
        if "name" in new_blueprint and isinstance(new_blueprint["name"], str):
            new_name = new_blueprint["name"]
            # Replace each parameter placeholder with its value
            for param_name, value in context.items():
                placeholder = "{" + param_name + "}"
                # Convert booleans to lowercase strings for YAML convention
                if isinstance(value, bool):
                    value_str = str(value).lower()
                else:
                    value_str = str(value)
                new_name = new_name.replace(placeholder, value_str)
            new_blueprint["name"] = new_name
        
        expanded_blueprints.append(new_blueprint)
    
    return expanded_blueprints


def expand_plugin_strategy(
    blueprint: Dict[str, Any], context: Optional[StrategyContext] = None
) -> List[Dict[str, Any]]:
    """
    Expand a blueprint with the plugin strategy which its ``strategy.type`` names.

    Everything the plugin returns is checked before any of it is used, so a
    mistake in a plugin is reported with nothing applied. Core then stamps
    ``strategy: {type, id}`` on each analysis (and project analysis), where
    ``id`` is the name of the blueprint, so the analyses of one expansion can
    be found again.

    Parameters
    ----------
    blueprint : dict
        The blueprint, with a ``strategy`` block which has a ``type``.
    context : StrategyContext, optional
        What the plugin may know about the project.

    Returns
    -------
    list of dict
        The documents to apply, in order, each with its ``kind``.

    Raises
    ------
    StrategyError
        If the type is not installed, or the plugin fails or returns
        something which cannot be applied.
    """
    context = context or StrategyContext()
    spec = deepcopy(blueprint["strategy"])
    kind = spec["type"]

    identifier = blueprint.get("name")
    if not isinstance(identifier, str) or not identifier:
        raise StrategyError(
            f"The strategy '{kind}' needs the blueprint to have a name, which identifies the group."
        )

    available = strategy_plugins()
    if kind not in available:
        installed = ", ".join(sorted(available)) or "none"
        raise StrategyError(
            f"Unknown strategy type '{kind}'. The installed strategies are: {installed}."
        )

    try:
        plugin = available[kind]()
        plugin.name = getattr(plugin, "name", "") or kind
        plugin.validate(deepcopy(spec))
        documents = plugin.expand(deepcopy(blueprint), context)
    except StrategyError:
        raise
    except Exception as error:
        raise StrategyError(f"The strategy '{kind}' could not be expanded: {error}") from error

    if not isinstance(documents, (list, tuple)) or not documents:
        raise StrategyError(f"The strategy '{kind}' did not return any documents to apply.")

    seen = set()
    emitted = []
    for document in documents:
        if not isinstance(document, dict):
            raise StrategyError(
                f"The strategy '{kind}' returned a {type(document).__name__}, not a document."
            )
        document = deepcopy(document)
        document_kind = str(document.get("kind", "analysis")).lower()
        if document_kind not in ALLOWED_KINDS:
            allowed = ", ".join(sorted(ALLOWED_KINDS))
            raise StrategyError(
                f"The strategy '{kind}' returned a document of kind "
                f"'{document.get('kind')}'; it can return: {allowed}."
            )
        document["kind"] = document_kind
        name = document.get("name")
        if not isinstance(name, str) or not name:
            raise StrategyError(f"The strategy '{kind}' returned a {document_kind} with no name.")

        stamped = document_kind in STAMPED_KINDS
        if stamped and "pipeline" not in document:
            # Everything which applying needs is checked now, so that a
            # mistake is found before any of the documents have been applied.
            raise StrategyError(
                f"The strategy '{kind}' returned the {document_kind} '{name}' with no pipeline."
            )

        # A name is unique among documents of its kind; an analysis's name only
        # has to be different from those in the same subject.
        scope = document.get("event") if document_kind == "analysis" else None
        identity = ("event" if document_kind == "subject" else document_kind, scope, name)
        if identity in seen:
            raise StrategyError(
                f"The strategy '{kind}' returned more than one {document_kind} named '{name}'."
            )
        seen.add(identity)

        if stamped:
            document["strategy"] = {"type": kind, "id": identifier}
        else:
            document.pop("strategy", None)
        emitted.append(document)
    return emitted
