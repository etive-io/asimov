"""
External blueprint compatibility tests.

These tests verify that asimov is compatible with the upstream asimov-data
blueprints. They are intentionally in a file that does NOT match the default
unittest discovery pattern (``test*.py``) so that ``python -m unittest discover
tests/`` does **not** run them automatically.

They are run in a separate CI job (``test-external-blueprints``) that has
``continue-on-error: true`` to allow this job to fail if the external data lags
behind code changes.

To run these tests manually::

    python -m unittest tests.external_blueprint_compat
"""
import unittest

from asimov.cli.application import apply_page
from asimov.testing import AsimovTestCase
from tests.test_specific_events import (
    EXTERNAL_DEFAULTS_URL,
    EXTERNAL_TESTS_BASE_URL,
    _GravitationalWaveEventsBase,
)


class TestGravitationalWaveEventsExternal(_GravitationalWaveEventsBase, AsimovTestCase):
    """
    Tests using blueprints fetched directly from the external asimov-data
    repository.  These tests verify compatibility with the upstream data, but
    are allowed to fail in CI because external data may lag behind code changes.
    Run via the ``test-external-blueprints`` CI job with
    ``continue-on-error: true``.
    """

    def _apply_defaults(self):
        apply_page(
            file=EXTERNAL_DEFAULTS_URL,
            event=None,
            ledger=self.ledger,
        )

    def _get_event_blueprint(self, event):
        return f"{EXTERNAL_TESTS_BASE_URL}/{event}.yaml"

    def _get_pipeline_blueprint(self, pipeline):
        return f"{EXTERNAL_TESTS_BASE_URL}/{pipeline}.yaml"


if __name__ == "__main__":
    unittest.main()
