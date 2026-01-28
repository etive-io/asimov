"""
Utility functions for the API.
"""

from flask import g
from asimov import config
from asimov.ledger import YAMLLedger


def get_ledger():
    """
    Get request-scoped ledger instance with proper cleanup.

    Note: This creates a new YAMLLedger instance for each request, which loads
    the entire ledger from disk. In a multi-worker deployment, each worker will
    have its own ledger instance, and changes made by one worker won't be
    immediately visible to others until they reload. The FileLock mechanism
    ensures data consistency during concurrent writes.

    Returns
    -------
    YAMLLedger
        The ledger instance for the current request.
    """
    if 'ledger' not in g:
        ledger_path = config.get("ledger", "location")
        g.ledger = YAMLLedger(ledger_path)
    return g.ledger
