"""
A plugin strategy can add to its group when one of its analyses finishes (#232).

The monitor calls ``Strategy.extend`` for each analysis of a group which has
just finished. What it returns is checked as ``expand`` is, applied to the same
group, and bounded.
"""
import unittest
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from asimov.cli import manage, monitor as monitor_cli, report
from asimov.ledger import YAMLLedger
from asimov.strategies import Strategy, extend_group, read_group

from tests.test_strategy_groups import GroupsCase, provided_by, Scan


class Rounds(Strategy):
    """Fit round 1; each round which finishes starts the next, up to a limit."""

    calls = []
    fail = False
    extra = None

    def expand(self, blueprint, context):
        return [{"kind": "analysis", "name": "fit-1", "event": "Base",
                 "pipeline": "simpletestpipeline", "status": "ready"}]

    def extend(self, analysis, context):
        type(self).calls.append((analysis.name, context.event, context.group["type"]))
        if type(self).fail:
            raise RuntimeError("boom")
        if type(self).extra is not None:
            return type(self).extra(analysis, context)
        number = int(analysis.name.split("-")[1])
        if number >= 3:
            return []
        return [{"kind": "analysis", "name": f"fit-{number + 1}", "pipeline": "simpletestpipeline",
                 "status": "ready", "needs": [analysis.name]}]


BLUEPRINT = """kind: analysis
name: rounds
pipeline: simpletestpipeline
strategy:
  type: scan
"""


def provided(strategy=Rounds, version="1.0"):
    import types
    from tests.test_plugin_strategies import FakeEntryPoint
    entry = FakeEntryPoint("scan", strategy)
    entry.dist = types.SimpleNamespace(name="demo", version=version)
    return patch("asimov.strategies.entry_points", return_value=[entry])


class ExtendCase(GroupsCase):
    def setUp(self):
        super().setUp()
        Rounds.calls = []
        Rounds.fail = False
        Rounds.extra = None
        self.write("blueprint.yaml", BLUEPRINT)
        with provided():
            from asimov.cli.application import apply_page
            apply_page("blueprint.yaml", ledger=self.ledger)

    def names(self, subject="Base"):
        fresh = self.reopen()
        return sorted(a.name for a in fresh.get_event(subject)[0].productions)

    def analysis(self, name, subject="Base"):
        fresh = self.reopen()
        return next(a for a in fresh.get_event(subject)[0].productions if a.name == name)

    def finish_and_extend(self, name="fit-1", version="1.0"):
        ledger = self.reopen()
        analysis = self.analysis(name)
        with provided(version=version):
            return extend_group(ledger, analysis), ledger


class ExtendTests(ExtendCase):
    def test_a_stamped_analysis_can_be_found(self):
        self.assertEqual(self.analysis("fit-1").meta["strategy"], {"type": "scan", "id": "rounds"})

    def test_it_adds_what_the_strategy_returns(self):
        added, _ = self.finish_and_extend()
        self.assertEqual(added, 1)
        self.assertEqual(self.names(), ["fit-1", "fit-2"])
        self.assertEqual(self.analysis("fit-2").meta["strategy"], {"type": "scan", "id": "rounds"})
        self.assertEqual(self.analysis("fit-2").dependencies, ["fit-1"])

    def test_the_strategy_is_given_the_analysis_the_subject_and_the_group(self):
        self.finish_and_extend()
        self.assertEqual(Rounds.calls, [("fit-1", "Base", "scan")])

    def test_doing_it_twice_adds_nothing_more(self):
        self.finish_and_extend()
        added, _ = self.finish_and_extend()
        self.assertEqual(added, 0)
        self.assertEqual(self.names(), ["fit-1", "fit-2"])

    def test_the_record_notes_who_extended_the_group(self):
        self.finish_and_extend(version="2.0")
        group = read_group(self.reopen(), "rounds")
        self.assertEqual(group["plugin"]["version"], "1.0")
        self.assertEqual(group["last extended with"], {"name": "demo", "version": "2.0"})

    def test_nothing_new_leaves_the_record_alone(self):
        self.finish_and_extend()
        before = read_group(self.reopen(), "rounds")
        self.finish_and_extend(version="3.0")
        self.assertEqual(read_group(self.reopen(), "rounds"), before)

    def test_a_strategy_which_adds_nothing_changes_nothing(self):
        Rounds.extra = lambda analysis, context: []
        added, _ = self.finish_and_extend()
        self.assertEqual(added, 0)
        self.assertEqual(self.names(), ["fit-1"])

    def test_a_strategy_which_does_not_override_extend_is_not_asked(self):
        with provided(Scan):
            self.assertEqual(extend_group(self.reopen(), self.analysis("fit-1")), 0)

    def test_an_analysis_which_no_strategy_made_is_ignored(self):
        ledger = self.reopen()
        plain = MagicMock()
        plain.meta = {}
        with provided():
            self.assertEqual(extend_group(ledger, plain), 0)
        self.assertEqual(Rounds.calls, [])


class FailureTests(ExtendCase):
    def test_a_strategy_which_raises_is_reported_and_adds_nothing(self):
        Rounds.fail = True
        added, _ = self.finish_and_extend()
        self.assertEqual(added, 0)
        self.assertEqual(self.names(), ["fit-1"])

    def test_a_bad_document_applies_nothing(self):
        Rounds.extra = lambda a, c: [
            {"kind": "analysis", "name": "ok", "pipeline": "simpletestpipeline"},
            {"kind": "analysis", "name": "bad"},  # no pipeline
        ]
        added, _ = self.finish_and_extend()
        self.assertEqual(added, 0)
        self.assertEqual(self.names(), ["fit-1"])

    def test_an_analysis_for_a_subject_which_does_not_exist_applies_nothing(self):
        Rounds.extra = lambda a, c: [
            {"kind": "analysis", "name": "x", "event": "Nowhere", "pipeline": "simpletestpipeline"},
        ]
        added, _ = self.finish_and_extend()
        self.assertEqual(added, 0)
        self.assertEqual(self.names(), ["fit-1"])

    def test_a_group_cannot_grow_beyond_the_limit(self):
        Rounds.extra = lambda a, c: [
            {"kind": "analysis", "name": f"more-{n}", "pipeline": "simpletestpipeline"}
            for n in range(5)
        ]
        with patch("asimov.strategies._max_group_analyses", return_value=3):
            added, _ = self.finish_and_extend()
        self.assertEqual(added, 0)
        self.assertEqual(self.names(), ["fit-1"])

    def test_up_to_the_limit_is_allowed(self):
        Rounds.extra = lambda a, c: [
            {"kind": "analysis", "name": f"more-{n}", "pipeline": "simpletestpipeline"}
            for n in range(2)
        ]
        with patch("asimov.strategies._max_group_analyses", return_value=3):
            added, _ = self.finish_and_extend()
        self.assertEqual(added, 2)


class OtherKindTests(ExtendCase):
    def test_it_can_add_a_subject_with_an_analysis(self):
        Rounds.extra = lambda a, c: [
            {"kind": "subject", "name": "Fresh", "interferometers": ["H1"]},
            {"kind": "analysis", "name": "first", "event": "Fresh", "pipeline": "simpletestpipeline"},
        ]
        added, _ = self.finish_and_extend()
        self.assertEqual(added, 2)
        self.assertEqual(self.names("Fresh"), ["first"])
        self.assertEqual(read_group(self.reopen(), "rounds")["subjects"], ["Fresh"])


class MonitorTests(ExtendCase):
    """The monitor calls it for what finishes, and what is added starts in the pass."""

    def run_monitor(self, *args):
        def fake_monitor(analysis, **kwargs):
            if analysis.status == "running":
                analysis.status = "finished"
            return True

        def fake_submit(**kwargs):
            started = 0
            led = monitor_cli.ledger
            for subject in led.get_event(kwargs.get("event")):
                for production in subject.get_all_latest():
                    if production.status == "ready":
                        production.status = "running"
                        started += 1
                led.update_event(subject)
            return started

        with provided(), \
             patch("asimov.current_ledger", new=YAMLLedger(".asimov/ledger.yml")), \
             patch.object(manage.build, "callback", lambda **k: None), \
             patch.object(manage.submit, "callback", fake_submit), \
             patch.object(report.html, "callback", MagicMock()), \
             patch.object(monitor_cli, "get_job_list", return_value=MagicMock()), \
             patch.object(monitor_cli, "monitor_analysis", fake_monitor), \
             patch.object(monitor_cli, "per_pass_limit", return_value=None):
            return CliRunner().invoke(monitor_cli.monitor, ["--chain", *args])

    def set_running(self, name):
        ledger = self.reopen()
        subject = ledger.get_event("Base")[0]
        for production in subject.productions:
            if production.name == name:
                production.status = "running"
        ledger.update_event(subject)

    def test_the_monitor_extends_a_group_when_an_analysis_finishes(self):
        self.set_running("fit-1")
        result = self.run_monitor()
        self.assertEqual(result.exception, None, result.output)
        self.assertEqual(self.names(), ["fit-1", "fit-2"])
        # and fit-2 was started in the same pass
        self.assertEqual(self.analysis("fit-2").status, "running")

    def test_a_dry_run_extends_nothing(self):
        self.set_running("fit-1")
        result = self.run_monitor("--dry-run")
        self.assertEqual(result.exception, None, result.output)
        self.assertEqual(self.names(), ["fit-1"])


if __name__ == "__main__":
    unittest.main()
