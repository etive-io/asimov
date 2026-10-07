"""
Utility functions for the API.
"""

from flask import g

from asimov import config
from asimov.context import get_active_context


def get_ledger():
    """
    Get request-scoped ledger instance for the configured backend.

    If a ``ProjectContext`` is active, its ledger is used, so a request
    handled for a particular project operates on that project. Otherwise
    the ledger is opened from the configuration, as it always has been.

    Returns
    -------
    YAMLLedger or DatabaseLedger
        The ledger instance for the current request.
    """
    active = get_active_context()
    if active is not None:
        return active.ledger

    if 'ledger' not in g:
        engine = config.get("ledger", "engine", fallback="sqlite")
        if engine == "yamlfile":
            from asimov.ledger import YAMLLedger
            g.ledger = YAMLLedger(config.get("ledger", "location"))
        else:
            from asimov.ledger import DatabaseLedger
            g.ledger = DatabaseLedger(engine=engine)
    return g.ledger
