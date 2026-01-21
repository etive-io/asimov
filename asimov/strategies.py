"""
Strategy expansion for asimov blueprints.

This module provides functionality to expand strategy definitions in blueprints
into multiple analyses, similar to GitHub Actions matrix strategies.
"""

from copy import deepcopy
from typing import Any, Dict, List
import itertools


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
    """
    keys = path.split(".")
    current = dictionary
    
    for key in keys[:-1]:
        if key not in current:
            current[key] = {}
        current = current[key]
    
    current[keys[-1]] = value


def expand_strategy(blueprint: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Expand a blueprint with a strategy into multiple blueprints.
    
    A strategy allows you to create multiple similar analyses by specifying
    parameter variations. This is similar to GitHub Actions matrix strategies.
    
    Parameters
    ----------
    blueprint : dict
        The blueprint document, which may contain a 'strategy' field
        
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
    ...     'name': 'bilby-{waveform}',
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
      where parameter_name is the last component of the dot notation path
    - Multiple strategy parameters create a cross-product (matrix)
    """
    if "strategy" not in blueprint:
        return [blueprint]
    
    strategy = blueprint.pop("strategy")
    
    # Get all parameter combinations
    param_names = list(strategy.keys())
    param_values = list(strategy.values())
    
    # Create all combinations (cross product)
    combinations = list(itertools.product(*param_values))
    
    expanded_blueprints = []
    
    for combination in combinations:
        # Create a copy of the blueprint for this combination
        new_blueprint = deepcopy(blueprint)
        
        # Build a context for name formatting
        # The context uses the last component of the parameter path as the key
        context = {}
        for param_name, value in zip(param_names, combination):
            # Extract the last component for use in name templates
            key = param_name.split(".")[-1]
            context[key] = value
        
        # Apply the parameter values to the blueprint
        for param_name, value in zip(param_names, combination):
            set_nested_value(new_blueprint, param_name, value)
        
        # Expand the name template if it contains placeholders
        if "name" in new_blueprint and isinstance(new_blueprint["name"], str):
            try:
                new_blueprint["name"] = new_blueprint["name"].format(**context)
            except KeyError:
                # If formatting fails, keep the original name
                # This allows names without templates to work
                pass
        
        expanded_blueprints.append(new_blueprint)
    
    return expanded_blueprints
