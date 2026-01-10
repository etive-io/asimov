"""
Utility functions for the API.
"""

from flask import g
from asimov import config
from asimov.ledger import YAMLLedger


def get_ledger():
    """
    Get request-scoped ledger instance with proper cleanup.

    Returns
    -------
    YAMLLedger
        The ledger instance for the current request.
    """
    if 'ledger' not in g:
        ledger_path = config.get("ledger", "location")
        g.ledger = YAMLLedger(ledger_path)
    return g.ledger
