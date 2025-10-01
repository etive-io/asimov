import collections
import os
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

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
