"""
Labeller plugin system for asimov monitor.

This module provides a plugin architecture for labelling analyses during monitoring.
Labellers can be used to automatically determine properties like "interest status"
based on analysis characteristics.
"""

from abc import ABC, abstractmethod
import sys
from typing import Dict

from asimov import logger, LOGGER_LEVEL

if sys.version_info < (3, 10):
    from importlib_metadata import entry_points
else:
    from importlib.metadata import entry_points

logger = logger.getChild("labellers")
logger.setLevel(LOGGER_LEVEL)


class Labeller(ABC):
    """
    Abstract base class for analysis labellers.
    
    Labellers are plugins that can assign labels or properties to analyses
    during the monitoring process. They can be used to mark analyses as
    "interesting", assign priorities, or add any custom metadata.
    
    Examples
    --------
    Create a custom labeller:
    
    >>> class ConvergenceLabeller(Labeller):
    ...     @property
    ...     def name(self):
    ...         return "convergence_checker"
    ...     
    ...     def label(self, analysis, context):
    ...         # Check if analysis has converged
    ...         if self.check_convergence(analysis):
    ...             return {"interest status": True, "converged": True}
    ...         return {}
    """
    
    @property
    @abstractmethod
    def name(self):
        """
        Return the unique name of this labeller.
        
        Returns
        -------
        str
            The labeller name (e.g., "interest_checker", "priority_assigner").
        """
        pass
    
    @abstractmethod
    def label(self, analysis, context=None):
        """
        Determine labels for the given analysis.
        
        This method should inspect the analysis and return a dictionary
        of labels/properties to add to the analysis metadata.
        
        Parameters
        ----------
        analysis : Analysis
            The analysis object to label.
        context : MonitorContext, optional
            The monitoring context, providing access to job info, ledger, etc.
            
        Returns
        -------
        dict
            Dictionary of labels/properties to add to analysis.meta.
            Common keys include:
            - "interest status": bool - Whether the analysis is interesting
            - Custom keys for specific labelling logic
            
        Examples
        --------
        Return interest status:
        
        >>> def label(self, analysis, context=None):
        ...     if analysis.pipeline.name == "bilby":
        ...         return {"interest status": True}
        ...     return {}
        
        Return multiple properties:
        
        >>> def label(self, analysis, context=None):
        ...     return {
        ...         "interest status": True,
        ...         "priority": 10,
        ...         "validated": True
        ...     }
        """
        pass
    
    #: What this labeller labels. Plugins which also label subjects set this to
    #: ``("analysis", "subject")`` and implement :meth:`label_subject`.
    targets = ("analysis",)

    def label_subject(self, subject, context=None):
        """
        Determine labels for a subject (an :class:`~asimov.event.Event`).

        Only called if ``"subject"`` is in :attr:`targets`. Return a dictionary
        of labels, as :meth:`label` does for an analysis. They're stored in
        ``subject.meta["labels"]``, and read with ``subject.labels``.
        """
        return {}

    def should_label_subject(self, subject, context=None):
        """Whether this labeller should run for the subject (default: always)."""
        return True

    def should_label(self, analysis, context=None):
        """
        Determine if this labeller should run for the given analysis.
        
        This method can be overridden to control when a labeller runs.
        By default, labellers run for all analyses.
        
        Parameters
        ----------
        analysis : Analysis
            The analysis to check.
        context : MonitorContext, optional
            The monitoring context.
            
        Returns
        -------
        bool
            True if the labeller should run, False otherwise.
            
        Examples
        --------
        Only label finished analyses:
        
        >>> def should_label(self, analysis, context=None):
        ...     return analysis.status == "finished"
        """
        return True


# Registry of all labellers
LABELLER_REGISTRY: Dict[str, Labeller] = {}


def register_labeller(labeller):
    """
    Register a labeller plugin.
    
    This function allows labellers to be registered at runtime,
    either programmatically or via entry points.
    
    Parameters
    ----------
    labeller : Labeller
        An instance of a Labeller subclass to register.
        
    Examples
    --------
    >>> class InterestLabeller(Labeller):
    ...     @property
    ...     def name(self):
    ...         return "interest_checker"
    ...     def label(self, analysis, context=None):
    ...         return {"interest status": True}
    >>> register_labeller(InterestLabeller())
    """
    if not isinstance(labeller, Labeller):
        raise TypeError(
            f"Labeller must be an instance of Labeller, "
            f"got {type(labeller).__name__}"
        )
    
    labeller_name = labeller.name
    if labeller_name in LABELLER_REGISTRY:
        logger.warning(
            f"Overwriting existing labeller '{labeller_name}'"
        )
    
    LABELLER_REGISTRY[labeller_name] = labeller
    logger.debug(f"Registered labeller '{labeller_name}'")


def discover_labellers():
    """
    Discover and register labellers via entry points.
    
    This function looks for entry points in the 'asimov.labellers' group
    and automatically registers any labeller plugins defined by packages.
    
    Entry points should return an instance of a Labeller subclass.
    
    Examples
    --------
    In your package's setup.py or pyproject.toml:
    
    .. code-block:: python
    
        # setup.py
        entry_points={
            'asimov.labellers': [
                'interest = mypackage.labellers:InterestLabeller',
            ]
        }
        
    Or in pyproject.toml:
    
    .. code-block:: toml
    
        [project.entry-points."asimov.labellers"]
        interest = "mypackage.labellers:InterestLabeller"
    """
    try:
        discovered_labellers = entry_points(group="asimov.labellers")
        
        for labeller_entry in discovered_labellers:
            try:
                # Load the labeller class or instance
                labeller_obj = labeller_entry.load()
                
                # If it's a class, instantiate it
                if isinstance(labeller_obj, type):
                    labeller = labeller_obj()
                else:
                    labeller = labeller_obj
                
                # Register the labeller
                register_labeller(labeller)
                logger.info(
                    f"Discovered and registered labeller '{labeller_entry.name}' "
                    f"from {labeller_entry.value}"
                )
            except Exception as e:
                logger.warning(
                    f"Failed to load labeller '{labeller_entry.name}': {e}"
                )
    except Exception as e:
        logger.debug(f"No labellers discovered: {e}")


def load_labellers_from_ledger(ledger):
    """
    Load and register labellers from ledger configuration.
    
    Labellers can be configured in the ledger via blueprint:
    
    .. code-block:: yaml
    
        kind: configuration
        labellers:
          interesting:
            my_package.labellers:InterestLabeller:
              config_key: config_value
    
    Parameters
    ----------
    ledger : Ledger
        The ledger object containing the configuration.
        
    Examples
    --------
    >>> from asimov import current_ledger
    >>> from asimov.labellers import load_labellers_from_ledger
    >>> load_labellers_from_ledger(current_ledger)
    """
    if "labellers" not in ledger.data:
        return
    
    labellers_config = ledger.data["labellers"]
    
    for labeller_name, labeller_spec in labellers_config.items():
        try:
            # labeller_spec can be either:
            # 1. A string: "my_package.labellers:InterestLabeller"
            # 2. A dict: {"my_package.labellers:InterestLabeller": {"config": "value"}}
            
            if isinstance(labeller_spec, str):
                module_path = labeller_spec
                config = {}
            elif isinstance(labeller_spec, dict):
                # Get the first (and should be only) key-value pair
                if len(labeller_spec) != 1:
                    logger.warning(
                        f"Invalid labeller spec for '{labeller_name}': "
                        f"expected single module path with optional config"
                    )
                    continue
                module_path, config = list(labeller_spec.items())[0]
                if config is None:
                    config = {}
            else:
                logger.warning(
                    f"Invalid labeller spec for '{labeller_name}': "
                    f"expected string or dict, got {type(labeller_spec)}"
                )
                continue
            
            # Parse module path (e.g., "my_package.labellers:InterestLabeller")
            if ":" not in module_path:
                logger.warning(
                    f"Invalid module path for labeller '{labeller_name}': "
                    f"expected 'module.path:ClassName', got '{module_path}'"
                )
                continue
            
            module_name, class_name = module_path.rsplit(":", 1)
            
            # Import the labeller class
            import importlib
            module = importlib.import_module(module_name)
            labeller_class = getattr(module, class_name)
            
            # Instantiate with config if it's a class
            if isinstance(labeller_class, type):
                if config:
                    labeller = labeller_class(**config)
                else:
                    labeller = labeller_class()
            else:
                labeller = labeller_class
            
            # Register the labeller
            register_labeller(labeller)
            logger.info(
                f"Loaded and registered labeller '{labeller_name}' "
                f"from ledger configuration"
            )
            
        except Exception as e:
            logger.warning(
                f"Failed to load labeller '{labeller_name}' from configuration: {e}"
            )


def _apply(target, context, kind):
    """Run the labellers which label ``kind`` ("analysis" or "subject") on ``target``."""
    all_labels = {}

    if not hasattr(target, 'meta'):
        target.meta = {}
    if not isinstance(target.meta.get('labels'), dict):
        target.meta['labels'] = {}

    for labeller_name, labeller in LABELLER_REGISTRY.items():
        if kind not in getattr(labeller, "targets", ("analysis",)):
            continue
        try:
            should, make = (
                (labeller.should_label, labeller.label)
                if kind == "analysis"
                else (labeller.should_label_subject, labeller.label_subject)
            )
            if not should(target, context):
                logger.debug(f"Labeller '{labeller_name}' skipped for {target.name}")
                continue

            labels = make(target, context)

            if labels:
                logger.debug(
                    f"Labeller '{labeller_name}' returned labels for {target.name}: {labels}"
                )
                manual = target.meta.get('manual labels', [])
                for key, value in labels.items():
                    if key in manual:
                        # Set by hand: it stays until it is removed.
                        continue
                    target.meta['labels'][key] = value
                    all_labels[key] = value

        except Exception as e:
            logger.warning(
                f"Error applying labeller '{labeller_name}' to {target.name}: {e}"
            )

    return all_labels


def apply_labellers(analysis, context=None):
    """
    Apply all registered labellers to an analysis.
    
    This function runs all registered labellers on the given analysis
    and stores the labels in analysis.meta['labels'] dictionary.
    
    Labels are stored as key-value pairs where the key is the label name
    and the value can be any JSON-serializable value (int, str, bool, etc.).
    
    Parameters
    ----------
    analysis : Analysis
        The analysis to label.
    context : MonitorContext, optional
        The monitoring context.
        
    Returns
    -------
    dict
        Dictionary of all labels applied to the analysis.
        
    Examples
    --------
    Apply labellers during monitoring:
    
    >>> labels = apply_labellers(analysis, context)
    >>> if labels.get("interesting"):
    ...     print(f"Analysis {analysis.name} is interesting!")
    
    Access labels from analysis:
    
    >>> if analysis.meta.get('labels', {}).get('interesting'):
    ...     print("This analysis is labelled as interesting")
    """
    return _apply(analysis, context, "analysis")


def apply_subject_labellers(subject, context=None):
    """
    Apply the labellers which label subjects to a subject.

    Labels go in ``subject.meta['labels']`` (read them as ``subject.labels``)
    and aren't inherited by the subject's analyses. Labels set by hand stay.

    Returns
    -------
    dict
        The labels which were applied.
    """
    return _apply(subject, context, "subject")


def get_labellers():
    """
    Get all registered labellers.
    
    Returns
    -------
    dict
        Dictionary mapping labeller names to labeller instances.
    """
    return LABELLER_REGISTRY.copy()
