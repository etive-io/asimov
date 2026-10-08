"""
``asimov monitor --chain --until-idle`` keeps running passes in the foreground
until nothing is running or can start (#233, part 2).

It reuses the fakes of the chain re-run tests: a scheduler which is not there,
a submit which starts what is ready, and a monitor step which finishes the
analyses it is told to.
"""
import unittest
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from asimov.cli import manage, monitor as monitor_cli, report
from asimov.ledger import YAMLLedger
from tests.test_monitor_chain_rerun import ChainRerunCase, analysis


class UntilIdleTests(ChainRerunCase):
    finishes = {"A", "B", "C"}

    def fake_submit(self, **kwargs):
        """Like the real submit, start only what is ready and not waiting."""
        self.submit_calls.append(kwargs)
        started = 0
        ledger = monitor_cli.ledger
        for subject in ledger.get_event(kwargs.get("event")):
            for production in subject.get_all_latest():
                if production.status == "ready":
                    production.status = "running"
                    started += 1
            ledger.update_event(subject)
        return started

    def set_status(self, name, status):
        fresh = YAMLLedger(".asimov/ledger.yml")
        subject = fresh.get_event("EvA")[0]
        for production in subject.productions:
            if production.name == name:
                production.status = status
        fresh.update_event(subject)

    def run_until_idle(self, *args):
        self.sleeps = []
        runner = CliRunner()
        with patch("asimov.current_ledger", new=YAMLLedger(".asimov/ledger.yml")), \
             patch.object(manage.build, "callback", self.fake_build), \
             patch.object(manage.submit, "callback", self.fake_submit), \
             patch.object(report.html, "callback", MagicMock()), \
             patch.object(monitor_cli, "get_job_list", return_value=MagicMock()), \
             patch.object(monitor_cli, "monitor_analysis", self.fake_monitor_analysis), \
             patch.object(monitor_cli, "per_pass_limit", return_value=None), \
             patch.object(monitor_cli.time, "sleep", self.sleeps.append):
            return runner.invoke(
                monitor_cli.monitor, ["--chain", "--until-idle", *args]
            )

    def test_it_runs_until_everything_has_finished(self):
        result = self.run_until_idle("--interval", "5")
        self.assertEqual(result.exit_code, monitor_cli.EXIT_IDLE_COMPLETE, result.output)
        self.assertEqual(self.statuses(), {"A": "finished", "B": "finished", "C": "finished"})
        self.assertIn("everything finished", result.output)

    def test_it_waits_the_interval_between_passes(self):
        self.run_until_idle("--interval", "5")
        self.assertTrue(self.sleeps)
        self.assertEqual(set(self.sleeps), {5.0})

    def test_it_does_not_wait_after_the_last_pass(self):
        result = self.run_until_idle("--interval", "5")
        passes = result.output.count("Pass ")
        self.assertEqual(len(self.sleeps), passes - 1)

    def test_blocked_work_is_idle_but_incomplete(self):
        """A is stuck, so B can never start: nothing more will happen."""
        self.set_status("A", "stuck")
        result = self.run_until_idle()
        self.assertEqual(result.exit_code, monitor_cli.EXIT_IDLE_INCOMPLETE, result.output)
        self.assertIn("not everything finished", result.output)
        self.assertEqual(self.statuses()["B"], "ready")

    def test_it_gives_up_after_max_passes(self):
        self.finishes = set()  # A runs for ever
        result = self.run_until_idle("--max-passes", "3")
        self.assertEqual(result.exit_code, monitor_cli.EXIT_GAVE_UP, result.output)
        self.assertEqual(result.output.count("Pass "), 3)

    def test_it_gives_up_after_the_timeout(self):
        self.finishes = set()
        result = self.run_until_idle("--timeout", "0", "--interval", "1")
        self.assertEqual(result.exit_code, monitor_cli.EXIT_GAVE_UP, result.output)
        self.assertEqual(result.output.count("Pass "), 1)

    def test_a_dry_run_makes_one_pass(self):
        result = self.run_until_idle("--dry-run")
        self.assertEqual(result.output.count("Pass "), 1)
        self.assertEqual(self.sleeps, [])

    def test_a_scheduler_which_cannot_be_queried_is_reported(self):
        with patch.object(monitor_cli, "get_job_list", side_effect=RuntimeError("down")):
            runner = CliRunner()
            with patch("asimov.current_ledger", new=YAMLLedger(".asimov/ledger.yml")), \
                 patch.object(manage.build, "callback", self.fake_build), \
                 patch.object(manage.submit, "callback", self.fake_submit):
                result = runner.invoke(monitor_cli.monitor, ["--chain", "--until-idle"])
        self.assertEqual(result.exit_code, monitor_cli.EXIT_NO_SCHEDULER, result.output)

    def test_it_needs_chain(self):
        result = CliRunner().invoke(monitor_cli.monitor, ["--until-idle"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("--until-idle needs --chain", result.output)

    def test_a_single_pass_is_unchanged(self):
        """Without --until-idle one pass is made, as before."""
        runner = CliRunner()
        self.finishes = {"A"}
        with patch("asimov.current_ledger", new=YAMLLedger(".asimov/ledger.yml")), \
             patch.object(manage.build, "callback", self.fake_build), \
             patch.object(manage.submit, "callback", self.fake_submit), \
             patch.object(report.html, "callback", MagicMock()), \
             patch.object(monitor_cli, "get_job_list", return_value=MagicMock()), \
             patch.object(monitor_cli, "monitor_analysis", self.fake_monitor_analysis), \
             patch.object(monitor_cli, "per_pass_limit", return_value=None):
            result = runner.invoke(monitor_cli.monitor, ["--chain"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertNotIn("Pass ", result.output)


if __name__ == "__main__":
    unittest.main()
