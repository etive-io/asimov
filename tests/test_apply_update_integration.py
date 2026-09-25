"""
Integration tests for `asimov apply --update` (the -U / update_page flag).

The correct behaviour is:
  - When an event already exists in the ledger and is re-applied with --update,
    any analysis that has already been built must NOT receive the new event-level
    settings.  Instead, the old event-level settings must be "frozen" into each
    existing analysis as analysis-specific overrides *before* the event is
    updated, so that the historical configuration is preserved.
  - Analyses that are added *after* the update are free to inherit the new
    event-level settings as normal.

Two test classes are provided:

  ApplyUpdateDirectTests  – call apply_page() directly, exercising the core
                            logic with the temporary YAMLLedger created by
                            AsimovTestCase.

  ApplyUpdateCLITests     – invoke the `asimov apply` CLI via subprocess so
                            that the full command-line path (including the
                            global ledger reload on each invocation) is tested.
                            These tests rely on `asimov` being installed in the
                            active environment, which is satisfied by the
                            `pip install .` step that precedes the test run in
                            GitLab CI.
"""

import os
import subprocess
import unittest
import yaml

from asimov.cli.application import apply_page
from asimov.ledger import YAMLLedger
from asimov.testing import AsimovTestCase


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _prod_data(event_dict, prod_name):
    """Return the settings dict for a named production inside an event dict."""
    for prod in event_dict.get("productions", []):
        if isinstance(prod, dict):
            if prod_name in prod:
                return prod[prod_name]
            # Flat dict with 'name' key
            if prod.get("name") == prod_name:
                return {k: v for k, v in prod.items() if k != "name"}
    return None


# ---------------------------------------------------------------------------
# Direct (unit-level integration) tests
# ---------------------------------------------------------------------------

class ApplyUpdateDirectTests(AsimovTestCase):
    """
    Tests that call apply_page() directly with an explicit ledger.

    These exercise the same code path as the CLI but without the subprocess
    overhead, making them fast enough to run on every push.
    """

    @property
    def event_v1(self):
        return f"{self.cwd}/tests/test_data/test_event.yaml"

    @property
    def event_v2(self):
        return f"{self.cwd}/tests/test_data/test_event_update.yaml"

    @property
    def analysis_first(self):
        return f"{self.cwd}/tests/test_data/test_analysis_S000000.yaml"

    @property
    def analysis_second(self):
        return f"{self.cwd}/tests/test_data/test_analysis_S000000_second.yaml"

    @property
    def analysis_with_override(self):
        return f"{self.cwd}/tests/test_data/test_analysis_S000000_with_prior_override.yaml"

    # ------------------------------------------------------------------
    # Core freeze behaviour
    # ------------------------------------------------------------------

    def test_existing_analysis_scalar_setting_frozen_on_update(self):
        """
        After --update the existing analysis must carry the *old* event time
        as an analysis-specific override, not the new one.
        """
        apply_page(self.event_v1, ledger=self.ledger)
        apply_page(self.analysis_first, ledger=self.ledger)

        # Sanity-check: analysis has no own 'event time' before the update
        before = _prod_data(self.ledger.events["S000000"], "bilby-IMRPhenomXPHM-QuickTest")
        self.assertNotIn("event time", before)

        apply_page(self.event_v2, ledger=self.ledger, update_page=True)

        event = self.ledger.events["S000000"]
        prod = _prod_data(event, "bilby-IMRPhenomXPHM-QuickTest")
        self.assertIsNotNone(prod, "Production not found in ledger after update")

        # Old event time must be frozen into the analysis
        self.assertEqual(
            prod["event time"],
            900,
            "Existing analysis should have the OLD event time (900) frozen in",
        )
        # Event level must now carry the NEW value
        self.assertEqual(
            event["event time"],
            909,
            "Event level should reflect the new event time (909) after update",
        )

    def test_existing_analysis_nested_setting_frozen_on_update(self):
        """
        Nested settings (e.g. priors) from the old event must be frozen into
        existing analyses; they must not be overwritten by the updated values.
        """
        apply_page(self.event_v1, ledger=self.ledger)
        apply_page(self.analysis_first, ledger=self.ledger)
        apply_page(self.event_v2, ledger=self.ledger, update_page=True)

        event = self.ledger.events["S000000"]
        prod = _prod_data(event, "bilby-IMRPhenomXPHM-QuickTest")

        # Old luminosity distance maximum (1000) frozen into analysis
        self.assertEqual(
            prod["priors"]["luminosity distance"]["maximum"],
            1000,
            "Existing analysis should have OLD prior maximum (1000) frozen in",
        )
        # Event level now carries the new prior
        self.assertEqual(
            event["priors"]["luminosity distance"]["maximum"],
            1010,
            "Event level should have new prior maximum (1010) after update",
        )

    def test_analysis_waveform_settings_survive_freeze(self):
        """
        Analysis-specific settings (e.g. waveform approximant) must not be
        lost when the old event settings are frozen in.
        """
        apply_page(self.event_v1, ledger=self.ledger)
        apply_page(self.analysis_first, ledger=self.ledger)
        apply_page(self.event_v2, ledger=self.ledger, update_page=True)

        prod = _prod_data(
            self.ledger.events["S000000"], "bilby-IMRPhenomXPHM-QuickTest"
        )
        self.assertEqual(
            prod.get("waveform", {}).get("approximant"),
            "IMRPhenomXPHM",
            "Analysis-specific waveform approximant must survive the freeze",
        )

    def test_analysis_specific_prior_takes_priority_over_frozen_event_setting(self):
        """
        When an analysis already has its own value for a key that is also
        present at the event level, the analysis-specific value must survive
        the freeze — the event-level default must not overwrite it.

        This verifies the merge direction: effective settings are
        merge(old_event_defaults, analysis_specific) where analysis wins.
        """
        apply_page(self.event_v1, ledger=self.ledger)
        apply_page(self.analysis_with_override, ledger=self.ledger)
        apply_page(self.event_v2, ledger=self.ledger, update_page=True)

        prod = _prod_data(
            self.ledger.events["S000000"], "bilby-IMRPhenomXPHM-WithOverride"
        )
        # The analysis set its own luminosity distance max to 500, which is
        # different from both the old event value (1000) and the new one (1010).
        # After the freeze, the analysis-specific value (500) must be preserved.
        self.assertEqual(
            prod["priors"]["luminosity distance"]["maximum"],
            500,
            "Analysis-specific prior override (500) must take priority over "
            "the old event-level default (1000) during the freeze",
        )

    def test_multiple_existing_analyses_all_get_frozen_settings(self):
        """
        All analyses that exist before the update must have the old event
        settings frozen independently.
        """
        apply_page(self.event_v1, ledger=self.ledger)
        apply_page(self.analysis_first, ledger=self.ledger)
        apply_page(self.analysis_second, ledger=self.ledger)
        apply_page(self.event_v2, ledger=self.ledger, update_page=True)

        event = self.ledger.events["S000000"]
        self.assertEqual(len(event["productions"]), 2)

        for prod_dict in event["productions"]:
            prod_name = next(iter(prod_dict))
            prod = prod_dict[prod_name]
            self.assertEqual(
                prod["event time"],
                900,
                f"Analysis {prod_name} should have OLD event time (900) frozen in",
            )
            self.assertEqual(
                prod["priors"]["luminosity distance"]["maximum"],
                1000,
                f"Analysis {prod_name} should have OLD prior maximum (1000) frozen in",
            )

    # ------------------------------------------------------------------
    # New-analysis behaviour after an update
    # ------------------------------------------------------------------

    def test_new_analysis_does_not_carry_frozen_old_settings(self):
        """
        An analysis added *after* the update must not have analysis-specific
        overrides for the old values — it inherits fresh from the event.
        """
        apply_page(self.event_v1, ledger=self.ledger)
        apply_page(self.analysis_first, ledger=self.ledger)
        apply_page(self.event_v2, ledger=self.ledger, update_page=True)
        apply_page(self.analysis_second, ledger=self.ledger)

        event = self.ledger.events["S000000"]
        new_prod = _prod_data(event, "bilby-IMRPhenomXPHM-HighSpin")
        self.assertIsNotNone(new_prod, "New analysis not found after update")

        # The new analysis must NOT have a frozen 'event time' override
        self.assertNotIn(
            "event time",
            new_prod,
            "New analysis should not carry a frozen 'event time' — "
            "it should inherit the current event-level value",
        )

    def test_new_analysis_inherits_updated_event_level_settings(self):
        """
        The event level must expose the *new* settings so that any analysis
        added after the update will see them.
        """
        apply_page(self.event_v1, ledger=self.ledger)
        apply_page(self.analysis_first, ledger=self.ledger)
        apply_page(self.event_v2, ledger=self.ledger, update_page=True)
        apply_page(self.analysis_second, ledger=self.ledger)

        event = self.ledger.events["S000000"]

        # Event-level settings carry new values
        self.assertEqual(
            event["event time"],
            909,
            "Event-level 'event time' should be 909 after update",
        )
        self.assertEqual(
            event["priors"]["luminosity distance"]["maximum"],
            1010,
            "Event-level prior max should be 1010 after update",
        )

    def test_analysis_count_unchanged_after_update(self):
        """
        The --update flag must not add or remove analyses — only re-decorate
        existing ones with frozen settings.
        """
        apply_page(self.event_v1, ledger=self.ledger)
        apply_page(self.analysis_first, ledger=self.ledger)
        apply_page(self.analysis_second, ledger=self.ledger)

        count_before = len(self.ledger.events["S000000"]["productions"])

        apply_page(self.event_v2, ledger=self.ledger, update_page=True)

        count_after = len(self.ledger.events["S000000"]["productions"])
        self.assertEqual(
            count_before,
            count_after,
            "--update must preserve the number of existing analyses",
        )

    def test_history_records_old_event_settings(self):
        """
        The ledger's history section must record the previous event-level
        settings (not the analysis-level overrides) for audit purposes.
        """
        apply_page(self.event_v1, ledger=self.ledger)
        apply_page(self.analysis_first, ledger=self.ledger)
        apply_page(self.event_v2, ledger=self.ledger, update_page=True)

        history = self.ledger.data.get("history", {}).get("S000000", {})
        self.assertIn(
            "version-1",
            history,
            "History must contain 'version-1' after first update",
        )
        self.assertEqual(
            history["version-1"]["event time"],
            900,
            "History must record old event time (900)",
        )
        self.assertEqual(
            history["version-1"]["priors"]["luminosity distance"]["maximum"],
            1000,
            "History must record old prior max (1000)",
        )
        self.assertIn(
            "date changed",
            history["version-1"],
            "History entry must include a 'date changed' timestamp",
        )


# ---------------------------------------------------------------------------
# CLI integration tests (subprocess)
# ---------------------------------------------------------------------------

class ApplyUpdateCLITests(AsimovTestCase):
    """
    Tests that invoke the `asimov` CLI via subprocess.

    These run the full executable path that a user or CI pipeline would
    follow.  They require that `asimov` is installed in the active Python
    environment (`pip install .`).
    """

    @property
    def event_v1(self):
        return f"{self.cwd}/tests/test_data/test_event.yaml"

    @property
    def event_v2(self):
        return f"{self.cwd}/tests/test_data/test_event_update.yaml"

    @property
    def analysis_first(self):
        return f"{self.cwd}/tests/test_data/test_analysis_S000000.yaml"

    @property
    def analysis_second(self):
        return f"{self.cwd}/tests/test_data/test_analysis_S000000_second.yaml"

    @property
    def analysis_with_override(self):
        return f"{self.cwd}/tests/test_data/test_analysis_S000000_with_prior_override.yaml"

    def _asimov(self, *args):
        """Run `asimov <args>` in the temp project directory and return result."""
        result = subprocess.run(
            ["asimov"] + list(args),
            capture_output=True,
            text=True,
        )
        return result

    def _read_ledger(self):
        """Re-read the ledger YAML from disk."""
        return YAMLLedger(".asimov/ledger.yml")

    def test_cli_apply_adds_event(self):
        """Basic smoke test: `asimov apply -f` should add an event."""
        result = self._asimov("apply", "-f", self.event_v1)
        self.assertEqual(result.returncode, 0, result.stderr)
        ledger = self._read_ledger()
        self.assertIn("S000000", ledger.events)

    def test_cli_update_flag_freezes_settings_in_existing_analysis(self):
        """
        Running `asimov apply -U` via the CLI must freeze old event settings
        into existing analyses and apply the new event-level settings.
        """
        self._asimov("apply", "-f", self.event_v1)
        self._asimov("apply", "-f", self.analysis_first)
        result = self._asimov("apply", "-U", "-f", self.event_v2)
        self.assertEqual(result.returncode, 0, result.stderr)

        ledger = self._read_ledger()
        event = ledger.events["S000000"]

        prod = _prod_data(event, "bilby-IMRPhenomXPHM-QuickTest")
        self.assertIsNotNone(prod)

        # Old event time frozen into existing analysis
        self.assertEqual(
            prod["event time"],
            900,
            "CLI --update must freeze old event time (900) into existing analysis",
        )
        # Event level now has new value
        self.assertEqual(
            event["event time"],
            909,
            "CLI --update must apply new event time (909) at event level",
        )

    def test_cli_update_nested_priors_frozen(self):
        """
        Nested prior settings must be frozen correctly via the CLI path.
        """
        self._asimov("apply", "-f", self.event_v1)
        self._asimov("apply", "-f", self.analysis_first)
        result = self._asimov("apply", "-U", "-f", self.event_v2)
        self.assertEqual(result.returncode, 0, result.stderr)

        ledger = self._read_ledger()
        event = ledger.events["S000000"]
        prod = _prod_data(event, "bilby-IMRPhenomXPHM-QuickTest")

        self.assertEqual(
            prod["priors"]["luminosity distance"]["maximum"],
            1000,
            "CLI --update must freeze old prior max (1000) into existing analysis",
        )
        self.assertEqual(
            event["priors"]["luminosity distance"]["maximum"],
            1010,
            "CLI --update must set new prior max (1010) at event level",
        )

    def test_cli_new_analysis_after_update_inherits_new_settings(self):
        """
        An analysis applied after `asimov apply -U` must inherit the *new*
        event-level settings and must not carry any frozen old values.
        """
        self._asimov("apply", "-f", self.event_v1)
        self._asimov("apply", "-f", self.analysis_first)
        self._asimov("apply", "-U", "-f", self.event_v2)
        self._asimov("apply", "-f", self.analysis_second)

        ledger = self._read_ledger()
        event = ledger.events["S000000"]

        new_prod = _prod_data(event, "bilby-IMRPhenomXPHM-HighSpin")
        self.assertIsNotNone(new_prod, "New analysis not found after CLI update")

        # New analysis must not have its own frozen 'event time'
        self.assertNotIn(
            "event time",
            new_prod,
            "New analysis added via CLI after --update must not carry frozen old 'event time'",
        )
        # Event level carries new values — visible to any future analysis
        self.assertEqual(
            event["event time"],
            909,
        )
        self.assertEqual(
            event["priors"]["luminosity distance"]["maximum"],
            1010,
        )

    def test_cli_update_without_flag_does_not_modify_existing_event(self):
        """
        Calling `asimov apply` *without* -U on an already-present event must
        leave the event unchanged (no settings overwritten, no analyses frozen).
        """
        self._asimov("apply", "-f", self.event_v1)
        self._asimov("apply", "-f", self.analysis_first)
        self._asimov("apply", "-f", self.event_v2)   # no -U flag

        ledger = self._read_ledger()
        event = ledger.events["S000000"]

        # Event must still have original settings
        self.assertEqual(
            event["event time"],
            900,
            "Without -U the event should not be changed",
        )
        prod = _prod_data(event, "bilby-IMRPhenomXPHM-QuickTest")
        # Analysis must not have a frozen 'event time'
        self.assertNotIn(
            "event time",
            prod,
            "Without -U no freeze should have happened",
        )

    def test_cli_update_nonexistent_event_reports_error(self):
        """
        Attempting to update an event that does not exist in the ledger must
        report a human-readable error.

        Note: `asimov apply` currently reports all errors via click.echo and
        always exits with code 0.  This test documents that behaviour.  The
        ledger must remain empty (no spurious event added).
        """
        result = self._asimov("apply", "-U", "-f", self.event_v2)
        self.assertEqual(result.returncode, 0, result.stderr)
        # Error message must mention that the event cannot be updated
        self.assertIn("cannot be updated", result.stdout)
        # The event must NOT have been silently added to the ledger
        ledger = self._read_ledger()
        self.assertNotIn(
            "S000000",
            ledger.events,
            "A non-existent event must not be silently added by --update",
        )


if __name__ == "__main__":
    unittest.main()
