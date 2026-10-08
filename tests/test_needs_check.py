"""
Applying reports what is wrong with the ``needs`` it leaves behind (#231): a
cycle, or a need which names an analysis that is not there. It is a report, not
a refusal.
"""
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from click.testing import CliRunner

from asimov.cli.application import apply, apply_page
from asimov.cli.project import make_project
from asimov.ledger import YAMLLedger
from asimov.needs_check import check_needs


def event(name):
    return f"kind: event\nname: {name}\ninterferometers: [H1]\n"


def analysis(name, needs=(), extra=""):
    text = f"kind: analysis\nname: {name}\npipeline: simpletestpipeline\nstatus: ready\n"
    if needs:
        text += "needs:\n" + "".join(f"  - {need}\n" for need in needs)
    return text + extra


class NeedsCheckCase(unittest.TestCase):
    def setUp(self):
        self.cwd = os.getcwd()
        self.root = tempfile.mkdtemp()
        os.chdir(self.root)
        make_project(name="Test project", root=self.root, engine="yamlfile")
        self.ledger = YAMLLedger(".asimov/ledger.yml")
        for name in ("EvA", "EvB"):
            self.apply(event(name))

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.root, ignore_errors=True)

    def apply(self, *documents, subject=None, **kwargs):
        with open("blueprint.yaml", "w") as handle:
            handle.write("---\n".join(documents))
        return apply_page("blueprint.yaml", event=subject, ledger=self.ledger, **kwargs)

    def messages(self, plan, level=None):
        return [p.message for p in plan.problems if level in (None, p.level)]

    def names(self, subject):
        return sorted(a.name for a in YAMLLedger(".asimov/ledger.yml").get_event(subject)[0].productions)


class CycleTests(NeedsCheckCase):
    def test_a_graph_without_a_cycle_has_no_problems(self):
        plan = self.apply(analysis("a"), analysis("b", ["a"]), subject="EvA")
        self.assertEqual(plan.problems, [])

    def test_a_cycle_in_a_subject_is_an_error(self):
        plan = self.apply(analysis("a", ["b"]), analysis("b", ["a"]), subject="EvA")
        errors = self.messages(plan, "error")
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("cycle", errors[0])
        self.assertIn("EvA/a", errors[0])
        self.assertIn("EvA/b", errors[0])

    def test_it_is_still_applied(self):
        self.apply(analysis("a", ["b"]), analysis("b", ["a"]), subject="EvA")
        self.assertEqual(self.names("EvA"), ["a", "b"])

    def test_a_cycle_through_other_subjects_is_found(self):
        self.apply(analysis("a", ["EvB/b"]), subject="EvA")
        plan = self.apply(analysis("b", ["EvA/a"]), subject="EvB")
        errors = self.messages(plan, "error")
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("EvA/a", errors[0])
        self.assertIn("EvB/b", errors[0])

    def test_a_chain_across_subjects_is_not_a_cycle(self):
        self.apply(analysis("a"), subject="EvA")
        plan = self.apply(analysis("b", ["EvA/a"]), subject="EvB")
        self.assertEqual(plan.problems, [])

    def test_a_longer_cycle_is_reported_once(self):
        plan = self.apply(
            analysis("a", ["c"]), analysis("b", ["a"]), analysis("c", ["b"]), subject="EvA"
        )
        self.assertEqual(len(self.messages(plan, "error")), 1)


class DanglingTests(NeedsCheckCase):
    def test_a_name_which_the_subject_does_not_have_is_an_error(self):
        plan = self.apply(analysis("a", ["EvB/typo"]), subject="EvA")
        errors = self.messages(plan, "error")
        self.assertEqual(len(errors), 1, plan.problems)
        self.assertIn("'EvB' has no analysis named 'typo'", errors[0])

    def test_a_subject_which_does_not_exist_is_a_warning(self):
        plan = self.apply(analysis("a", ["Later/fit"]), subject="EvA")
        self.assertEqual(self.messages(plan, "error"), [])
        warnings = self.messages(plan, "warning")
        self.assertEqual(len(warnings), 1)
        self.assertIn("no subject 'Later'", warnings[0])

    def test_one_which_is_there_is_not_reported(self):
        self.apply(analysis("fit"), subject="EvB")
        plan = self.apply(analysis("a", ["EvB/fit"]), subject="EvA")
        self.assertEqual(plan.problems, [])

    def test_an_optional_need_is_not_reported(self):
        plan = self.apply(
            "kind: analysis\nname: a\npipeline: simpletestpipeline\nstatus: ready\n"
            "needs:\n  - name: EvB/typo\n    optional: true\n",
            subject="EvA",
        )
        self.assertEqual(plan.problems, [])

    def test_a_plain_name_which_is_missing_is_not_this_checks_business(self):
        plan = self.apply(analysis("a", ["typo"]), subject="EvA")
        self.assertEqual(plan.problems, [])

    def test_it_is_still_applied(self):
        self.apply(analysis("a", ["EvB/typo"]), subject="EvA")
        self.assertEqual(self.names("EvA"), ["a"])


class WhereItLooksTests(NeedsCheckCase):
    def test_only_the_subjects_which_were_changed_are_read(self):
        self.apply(analysis("a"), subject="EvA")
        read = []
        original = YAMLLedger.get_event

        def spy(ledger, event=None):
            read.append(event)
            return original(ledger, event)

        with patch.object(YAMLLedger, "get_event", spy):
            check_needs(self.ledger, ["EvB"])
        self.assertNotIn("EvA", read)

    def test_a_blueprint_which_changes_no_analysis_checks_nothing(self):
        for document in (event("EvC"), "kind: configuration\n"):
            with patch("asimov.cli.application.check_needs") as check:
                self.apply(document)
            check.assert_not_called()

    def test_a_subject_which_brings_analyses_is_checked(self):
        from asimov.cli.application import _has_analyses

        self.assertTrue(_has_analyses({"productions": [{"a": {}}]}))
        self.assertTrue(_has_analyses({"analyses": [{"a": {}}]}))
        self.assertFalse(_has_analyses({"name": "EvC"}))
        self.assertFalse(_has_analyses(None))

    def test_the_events_loaded_while_applying_are_reused(self):
        with patch.object(self.ledger, "get_event", wraps=self.ledger.get_event) as get_event:
            self.apply(analysis("a"), analysis("b", ["a"]), subject="EvA")
        self.assertEqual(get_event.call_count, 1)

    def test_a_check_which_fails_does_not_fail_the_apply(self):
        with patch("asimov.cli.application.check_needs", side_effect=RuntimeError("boom")):
            plan = self.apply(analysis("a"), subject="EvA")
        self.assertEqual(plan.problems, [])
        self.assertEqual(self.names("EvA"), ["a"])


class ReportingTests(NeedsCheckCase):
    def test_a_dry_run_reports_it_and_writes_nothing(self):
        plan = self.apply(analysis("a", ["b"]), analysis("b", ["a"]), subject="EvA", dry_run=True)
        self.assertEqual(len(self.messages(plan, "error")), 1)
        self.assertEqual(self.names("EvA"), [])
        self.assertTrue(any("cycle" in line for line in plan.render()))
        self.assertEqual(plan.to_dict()["problems"][0]["level"], "error")

    def test_a_plan_without_problems_still_says_so(self):
        plan = self.apply(analysis("a"), subject="EvA", dry_run=True)
        self.assertEqual(plan.to_dict()["problems"], [])

    def test_the_command_says_it(self):
        with open("blueprint.yaml", "w") as handle:
            handle.write(analysis("a", ["EvB/typo"]))
        with patch("asimov.cli.application.get_ledger", return_value=self.ledger):
            result = CliRunner().invoke(apply, ["-f", "blueprint.yaml", "-e", "EvA"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("'EvB' has no analysis named 'typo'", result.output)


if __name__ == "__main__":
    unittest.main()
