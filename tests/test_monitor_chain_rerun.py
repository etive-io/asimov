"""
``asimov monitor --chain`` runs build and submit again in the same pass once
analyses have finished (#233, part 1).

The monitor step is what notices that an analysis has finished, and what needs
it was only submitted by the next pass, a whole period later. The scheduler
and the pipelines are replaced with small fakes here: a ``submit`` which starts
what ``get_all_latest`` says is ready (the real dependency logic), and a
monitor step which finishes the analyses it is told to.
"""
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from asimov.cli import manage, monitor as monitor_cli, report
from asimov.cli.application import apply_page
from asimov.cli.project import make_project
from asimov.ledger import YAMLLedger

EVENT = "kind: event\nname: EvA\ninterferometers: [H1]\n"


def analysis(name, status, needs=None):
    text = f"kind: analysis\nname: {name}\npipeline: simpletestpipeline\nstatus: {status}\n"
    if needs:
        text += "needs:\n" + "".join(f"  - {need}\n" for need in needs)
    return text


class ChainRerunCase(unittest.TestCase):
    #: Analyses which the (fake) monitor step finds to have finished.
    finishes = {"A"}
    #: Whether the (fake) submit also finishes what it starts, as some do.
    finishes_on_submit = False

    def setUp(self):
        self.cwd = os.getcwd()
        self.root = tempfile.mkdtemp()
        os.chdir(self.root)
        make_project(name="Test project", root=self.root, engine="yamlfile")
        self.ledger = YAMLLedger(".asimov/ledger.yml")
        with open("event.yaml", "w") as handle:
            handle.write(EVENT)
        apply_page("event.yaml", ledger=self.ledger)
        self.apply(
            analysis("A", "running"),
            analysis("B", "ready", needs=["A"]),
            analysis("C", "ready", needs=["B"]),
        )
        self.build_calls = []
        self.submit_calls = []

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.root, ignore_errors=True)

    def apply(self, *blueprints):
        with open("blueprint.yaml", "w") as handle:
            handle.write("---\n".join(blueprints))
        apply_page("blueprint.yaml", event="EvA", ledger=self.ledger)

    def statuses(self):
        fresh = YAMLLedger(".asimov/ledger.yml")
        return {a.name: a.status for a in fresh.get_event("EvA")[0].productions}

    def fake_build(self, **kwargs):
        self.build_calls.append(kwargs)

    def fake_submit(self, **kwargs):
        """Start what is ready and not waiting on anything."""
        self.submit_calls.append(kwargs)
        started = 0
        ledger = monitor_cli.ledger
        for subject in ledger.get_event(kwargs.get("event")):
            for production in subject.get_all_latest():
                production.status = "finished" if self.finishes_on_submit else "running"
                started += 1
            ledger.update_event(subject)
        return started

    def fake_monitor_analysis(self, analysis, **kwargs):
        if analysis.name in self.finishes and analysis.status == "running":
            analysis.status = "finished"
        return True

    def run_monitor(self, *args, per_pass_limit=None):
        runner = CliRunner()
        with patch("asimov.current_ledger", new=YAMLLedger(".asimov/ledger.yml")), \
             patch.object(manage.build, "callback", self.fake_build), \
             patch.object(manage.submit, "callback", self.fake_submit), \
             patch.object(report.html, "callback", MagicMock()), \
             patch.object(monitor_cli, "get_job_list", return_value=MagicMock()), \
             patch.object(monitor_cli, "monitor_analysis", self.fake_monitor_analysis), \
             patch.object(monitor_cli, "per_pass_limit", return_value=per_pass_limit):
            result = runner.invoke(monitor_cli.monitor, list(args))
        self.assertEqual(result.exception, None, result.output)
        return result


class RerunTests(ChainRerunCase):
    def test_what_needs_a_finished_analysis_starts_in_the_same_pass(self):
        result = self.run_monitor("--chain")
        self.assertEqual(self.statuses(), {"A": "finished", "B": "running", "C": "ready"})
        self.assertEqual((len(self.build_calls), len(self.submit_calls)), (2, 2))
        self.assertIn("1 finished in this pass: running build and submit again", result.output)

    def test_without_the_rerun_it_would_wait_for_the_next_pass(self):
        """What the rerun is for: one run of submit starts nothing, because
        nothing has been marked finished when it runs."""
        with patch.object(monitor_cli, "CHAIN_MAX_RERUNS", 0):
            self.run_monitor("--chain")
        self.assertEqual(self.statuses(), {"A": "finished", "B": "ready", "C": "ready"})

    def test_nothing_finishing_means_one_run_only(self):
        self.finishes = set()
        result = self.run_monitor("--chain")
        self.assertEqual((len(self.build_calls), len(self.submit_calls)), (1, 1))
        self.assertNotIn("running build and submit again", result.output)
        self.assertEqual(self.statuses(), {"A": "running", "B": "ready", "C": "ready"})

    def test_without_chain_neither_is_run(self):
        self.run_monitor()
        self.assertEqual((len(self.build_calls), len(self.submit_calls)), (0, 0))
        self.assertEqual(self.statuses()["B"], "ready")

    def test_a_dry_run_does_not_rerun(self):
        self.run_monitor("--chain", "--dry-run")
        self.assertEqual((len(self.build_calls), len(self.submit_calls)), (1, 1))

    def test_it_runs_again_while_running_them_finishes_more(self):
        """Some analyses finish as they are submitted, which frees the next."""
        self.finishes_on_submit = True
        self.run_monitor("--chain")
        self.assertEqual(self.statuses(), {"A": "finished", "B": "finished", "C": "finished"})
        # The first run, one for each of B and C, and one which finds nothing more.
        self.assertEqual(len(self.submit_calls), 4)

    def test_it_stops_when_running_them_again_finishes_nothing_more(self):
        self.run_monitor("--chain")
        # B is only running, so a second rerun would achieve nothing.
        self.assertEqual(len(self.submit_calls), 2)

    def test_the_number_of_reruns_is_bounded(self):
        self.finishes_on_submit = True
        self.apply(
            analysis("D", "ready", needs=["C"]),
            analysis("E", "ready", needs=["D"]),
            analysis("F", "ready", needs=["E"]),
        )
        with patch.object(monitor_cli, "CHAIN_MAX_RERUNS", 2):
            self.run_monitor("--chain")
        self.assertEqual(len(self.submit_calls), 1 + 2)
        self.assertEqual(self.statuses()["F"], "ready")

    def test_a_failing_build_does_not_stop_the_submit(self):
        def broken_build(**kwargs):
            self.build_calls.append(kwargs)
            raise RuntimeError("no build")

        self.fake_build = broken_build
        self.run_monitor("--chain")
        self.assertEqual(self.statuses()["B"], "running")


class SubmissionLimitTests(ChainRerunCase):
    def test_the_limit_for_the_pass_is_shared_by_the_runs(self):
        """With ``max_submit_per_pass = 2`` and one submitted in the first run,
        the second may submit one more."""
        submitted_first = iter([1])
        original = self.fake_submit

        def counting_submit(**kwargs):
            original(**kwargs)
            return next(submitted_first, 0)

        self.fake_submit = counting_submit
        self.run_monitor("--chain", per_pass_limit=2)
        # (An option which is not given is passed as its default, None.)
        self.assertIsNone(self.submit_calls[0]["max_submit"])
        self.assertEqual(self.submit_calls[1]["max_submit"], 1)

    def test_no_rerun_when_the_limit_has_been_reached(self):
        original = self.fake_submit
        self.fake_submit = lambda **kwargs: (original(**kwargs), 2)[1]
        result = self.run_monitor("--chain", per_pass_limit=2)
        self.assertEqual(len(self.submit_calls), 1)
        self.assertIn("The submission limit for this pass has been reached", result.output)
        self.assertEqual(self.statuses()["B"], "ready")

    def test_no_limit_means_none_is_passed(self):
        self.run_monitor("--chain", per_pass_limit=None)
        self.assertIsNone(self.submit_calls[1]["max_submit"])


if __name__ == "__main__":
    unittest.main()
