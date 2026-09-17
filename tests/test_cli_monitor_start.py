"""
Regression tests for `asimov.cli.monitor._start_htcondor_monitor`.

Before this fix, the submit_description dict literal called
`config.get("asimov start", "accounting")` unconditionally while building
itself. If that section/option wasn't configured, this raised uncaught --
so the "warn and continue without accounting info" fallback a few lines
below was unreachable dead code. That went unnoticed because
`asimov monitor start` wasn't exercised anywhere in the existing suite.

Separately, the cron job's `getenv = "true"` is rejected outright by a
real LIGO Data Grid pool once it sets SUBMIT_ALLOW_GETENV = False, so it
must be an explicit variable list instead.
"""

import configparser
import unittest
from unittest.mock import MagicMock, patch

from asimov.cli import monitor as monitor_cli


class StartHTCondorMonitorTests(unittest.TestCase):
    def setUp(self):
        self.test_config = configparser.ConfigParser()
        config_patcher = patch.object(monitor_cli, "config", self.test_config)
        config_patcher.start()
        self.addCleanup(config_patcher.stop)

        mock_ledger = MagicMock()
        mock_ledger.data = {"project": {"name": "TestProject"}}
        ledger_patcher = patch.object(monitor_cli, "ledger", mock_ledger)
        ledger_patcher.start()
        self.addCleanup(ledger_patcher.stop)

        which_patcher = patch.object(
            monitor_cli.shutil, "which", return_value="/usr/bin/asimov"
        )
        which_patcher.start()
        self.addCleanup(which_patcher.stop)

    def _submit_and_capture(self):
        captured = {}

        def fake_submit_job(description):
            captured.update(description)
            return 42

        with patch.object(
            monitor_cli.condor, "submit_job", side_effect=fake_submit_job
        ):
            monitor_cli._start_htcondor_monitor(
                dry_run=False, use_scheduler_api=False
            )
        return captured

    def test_missing_accounting_config_does_not_crash(self):
        """No [asimov start] or [condor] accounting configured at all."""
        description = self._submit_and_capture()
        self.assertNotIn("accounting_group", description)
        self.assertNotIn("accounting_group_user", description)

    def test_accounting_from_asimov_start_section(self):
        self.test_config["asimov start"] = {
            "accounting": "ligo.dev.o4.cbc.test.test"
        }
        self.test_config["condor"] = {"user": "submituser"}
        description = self._submit_and_capture()
        self.assertEqual(
            description["accounting_group"], "ligo.dev.o4.cbc.test.test"
        )
        self.assertEqual(description["accounting_group_user"], "submituser")

    def test_accounting_falls_back_to_condor_section(self):
        self.test_config["condor"] = {
            "accounting": "ligo.dev.o4.cbc.test.test",
            "user": "submituser",
        }
        description = self._submit_and_capture()
        self.assertEqual(
            description["accounting_group"], "ligo.dev.o4.cbc.test.test"
        )

    def test_getenv_is_not_blanket_true(self):
        description = self._submit_and_capture()
        self.assertNotEqual(description["getenv"], "true")
        self.assertIn("PATH", description["getenv"])

    def test_monitor_getenv_is_configurable(self):
        self.test_config["condor"] = {"monitor_getenv": "PATH,FOO"}
        description = self._submit_and_capture()
        self.assertEqual(description["getenv"], "PATH,FOO")


if __name__ == "__main__":
    unittest.main()
