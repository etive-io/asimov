"""
Utility functions for the API.
"""

from flask import g
from asimov import config


def get_ledger():
    """
    Get request-scoped ledger instance for the configured backend.

    Returns
    -------
    YAMLLedger or DatabaseLedger
        The ledger instance for the current request.
    """
    if 'ledger' not in g:
        engine = config.get("ledger", "engine", fallback="yamlfile")
        if engine == "yamlfile":
            from asimov.ledger import YAMLLedger
            g.ledger = YAMLLedger(config.get("ledger", "location"))
        else:
            from asimov.ledger import DatabaseLedger
            g.ledger = DatabaseLedger(engine=engine)
    return g.ledger
