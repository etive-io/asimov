"""
These tests are designed to verify that specific events produce specific
outputs for each pipeline.

There are two test classes:
- TestGravitationalWaveEventsLocal: Uses local copies of the blueprints (must pass).
- TestGravitationalWaveEventsExternal: Uses blueprints fetched from the external 
  asimov-data repository (allowed to fail in CI as external data may lag behind 
  code changes). This class is run as a separate CI job from
  ``external_blueprint_compat.py``.
"""
import os

from asimov.cli.application import apply_page
from asimov.testing import AsimovTestCase

pipelines = {"bayeswave", "bilby", "rift"}
EVENTS = {"GW150914_095045", "GW190924_021846", "GW190929_012149", "GW191109_010717"}

EXTERNAL_DEFAULTS_URL = "https://git.ligo.org/asimov/data/-/raw/main/defaults/production-pe.yaml"
EXTERNAL_TESTS_BASE_URL = "https://git.ligo.org/asimov/data/-/raw/main/tests"

# Absolute path to the local blueprint data directory, computed from this file's
# location so that the tests are not sensitive to the current working directory.
_BLUEPRINTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_data", "blueprints")


class _GravitationalWaveEventsBase:
    """Base class (mixin) providing the fiducial event test logic.
    
    Not a TestCase itself - used as a mixin with AsimovTestCase in the
    concrete test classes to prevent auto-discovery running it directly.
    The setUp/tearDown/setUpClass lifecycle is inherited from AsimovTestCase.
    """

    def _apply_defaults(self):
        raise NotImplementedError

    def _get_event_blueprint(self, event):
        raise NotImplementedError

    def _get_pipeline_blueprint(self, pipeline):
        raise NotImplementedError

    def test_fiducial_events(self):
        self._apply_defaults()
        for event in EVENTS:
            for pipeline in pipelines:
                with self.subTest(event=event, pipeline=pipeline):
                    apply_page(
                        file=self._get_event_blueprint(event),
                        event=None,
                        ledger=self.ledger,
                    )
                    apply_page(
                        file=self._get_pipeline_blueprint(pipeline),
                        event=event,
                        ledger=self.ledger,
                    )
                    event_o = self.ledger.get_event(event)[0]
                    production = event_o.productions[0]
                    production.make_config(f"{self.cwd}/tests/tmp/test_config.ini")


class TestGravitationalWaveEventsLocal(_GravitationalWaveEventsBase, AsimovTestCase):
    """
    Tests using local copies of blueprints updated to conform to the v0.7
    requirement that minimum frequency lives in the 'waveform' section.
    These tests must always pass.
    """

    def _apply_defaults(self):
        apply_page(
            file=os.path.join(_BLUEPRINTS_DIR, "production-pe.yaml"),
            event=None,
            ledger=self.ledger,
        )

    def _get_event_blueprint(self, event):
        return os.path.join(_BLUEPRINTS_DIR, f"{event}.yaml")

    def _get_pipeline_blueprint(self, pipeline):
        return os.path.join(_BLUEPRINTS_DIR, f"{pipeline}.yaml")
