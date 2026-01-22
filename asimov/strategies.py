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
