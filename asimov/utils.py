import collections
import os
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import itertools

from asimov import logger


@contextmanager
def set_directory(path: (Path, str)):
    """
    Change to a different directory for the duration of the context.

    Args:
        path (Path): The path to the cwd

    Yields:
        None
    """

    origin = Path().absolute()
    try:
        logger.info(f"Working temporarily in {path}")
        os.chdir(path)
        yield
    finally:
        os.chdir(origin)
        logger.info(f"Now working in {origin} again")


def update(d, u, inplace=True):
    """Recursively update a dictionary."""
    if not inplace:
        d = deepcopy(d)
        u = deepcopy(u)
    for k, v in u.items():
        if isinstance(v, collections.abc.Mapping):
            d[k] = update(d.get(k, {}), v)
        else:
            d[k] = v
    return d


# The following function adapted from https://stackoverflow.com/a/69908295
def diff_dict(d1, d2):
    d1_keys = set(d1.keys())
    d2_keys = set(d2.keys())
    shared_keys = d1_keys.intersection(d2_keys)
    shared_deltas = {o: (d1[o], d2[o]) for o in shared_keys if d1[o] != d2[o]}
    added_keys = d2_keys - d1_keys
    added_deltas = {o: (None, d2[o]) for o in added_keys}
    deltas = {**shared_deltas, **added_deltas}
    return parse_deltas(deltas)


# The following function adapted from https://stackoverflow.com/a/69908295
def parse_deltas(deltas: dict):
    res = {}
    for k, v in deltas.items():
        if isinstance(v[0], dict):
            tmp = diff_dict(v[0], v[1])
            if tmp:
                res[k] = tmp
        else:
            res[k] = v[1]
    return res


def set_nested_value(d, path, value):
    """
    Set a value in a nested dictionary using a dot-separated path.
    
    Parameters
    ----------
    d : dict
        The dictionary to update
    path : str
        Dot-separated path (e.g., "waveform.approximant")
    value : any
        The value to set
    """
    keys = path.split('.')
    current = d
    for key in keys[:-1]:
        if key not in current:
            current[key] = {}
        current = current[key]
    current[keys[-1]] = value


def expand_strategy(production_dict):
    """
    Expand a production definition with a matrix strategy into multiple productions.
    
    This function implements matrix strategy expansion similar to GitHub Actions,
    allowing users to define multiple similar analyses with parameter variations.
    
    Parameters
    ----------
    production_dict : dict
        A production dictionary that may contain a 'strategy' field with a 'matrix'.
        
    Returns
    -------
    list
        A list of production dictionaries. If no strategy is defined, returns a
        single-element list containing the original production. If a strategy is
        defined, returns multiple productions, one for each combination of matrix
        parameters.
        
    Examples
    --------
    >>> production = {
    ...     'name': 'Prod',
    ...     'pipeline': 'bilby',
    ...     'strategy': {
    ...         'matrix': {
    ...             'waveform.approximant': ['IMRPhenomXPHM', 'SEOBNRv4PHM'],
    ...             'sampler.sampler': ['dynesty', 'nestle']
    ...         }
    ...     }
    ... }
    >>> expanded = expand_strategy(production)
    >>> len(expanded)
    4
    >>> expanded[0]['name']
    'Prod-0'
    >>> expanded[0]['waveform']['approximant']
    'IMRPhenomXPHM'
    """
    if 'strategy' not in production_dict:
        return [production_dict]
    
    strategy = production_dict.pop('strategy')
    
    if 'matrix' not in strategy:
        logger.warning("Strategy defined but no matrix found. Ignoring strategy.")
        return [production_dict]
    
    matrix = strategy['matrix']
    
    # Get all combinations of matrix values
    param_names = list(matrix.keys())
    param_values = [matrix[name] if isinstance(matrix[name], list) else [matrix[name]]
                    for name in param_names]
    
    combinations = list(itertools.product(*param_values))
    
    productions = []
    base_name = production_dict.get('name', 'Production')
    
    for idx, combination in enumerate(combinations):
        # Create a deep copy of the base production
        new_production = deepcopy(production_dict)
        
        # Update the name to include the index
        new_production['name'] = f"{base_name}-{idx}"
        
        # Apply each parameter from the matrix
        for param_name, param_value in zip(param_names, combination):
            set_nested_value(new_production, param_name, param_value)
        
        productions.append(new_production)
    
    return productions
