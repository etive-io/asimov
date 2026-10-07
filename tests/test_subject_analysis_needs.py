"""
A subject analysis has ``needs:`` as well as ``analyses:`` (#231).

``analyses:`` says what it combines: it starts once every analysis which
matches has finished, and is refreshed when another appears. ``needs:`` is an
ordinary dependency, in its own subject or another (``subject/name``), which
must have finished before it starts and is not input to it.
"""
import logging
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from asimov.analysis import SubjectAnalysis
from asimov.cli.application import apply_page
from asimov.cli.manage import report_unresolved_needs
from asimov.cli.project import make_project
from asimov.ledger import YAMLLedger

EVENT = "kind: event\nname: {name}\ninterferometers: [H1]\n"


def analysis(name, status="finished", needs=None, analyses=None, pipeline="simpletestpipeline"):
    text = f"kind: analysis\nname: {name}\npipeline: {pipeline}\nstatus: {status}\n"
    for key, entries in (("needs", needs), ("analyses", analyses)):
        if entries is not None:
            text += f"{key}:\n" + "".join(f"  - {entry}\n" for entry in entries)
    return text


def combine(name, status="ready", needs=None, analyses=("'pipeline: simpletestpipeline'",)):
    return analysis(name, status, needs, list(analyses), pipeline="subjecttestpipeline")


class SubjectNeedsCase(unittest.TestCase):
    def setUp(self):
        self.cwd = os.getcwd()
        self.root = tempfile.mkdtemp()
        os.chdir(self.root)
        make_project(name="Test project", root=self.root, engine="yamlfile")
        self.ledger = YAMLLedger(".asimov/ledger.yml")
        for name in ("central", "s1"):
            self.write("event.yaml", EVENT.format(name=name))
            apply_page("event.yaml", ledger=self.ledger)
        self.logger = logging.getLogger("test_subject_analysis_needs")

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, name, text):
        with open(name, "w") as handle:
            handle.write(text)

    def apply(self, event, *blueprints):
        self.write("blueprint.yaml", "---\n".join(blueprints))
        apply_page("blueprint.yaml", event=event, ledger=self.ledger)

    def event(self, name):
        return YAMLLedger(".asimov/ledger.yml").get_event(name)[0]

    def get(self, event, name):
        found = self.event(event).analysis_by_name(name)
        self.assertIsInstance(found, SubjectAnalysis)
        return found

    def ready(self, event):
        return {a.name for a in self.event(event).get_all_latest()}


class NeedsGateTests(SubjectNeedsCase):
    def test_it_waits_for_a_need_in_its_own_subject(self):
        self.apply("s1", analysis("fit"), analysis("prep", status="running"),
                   combine("combined", needs=["prep"]))
        self.assertEqual(self.get("s1", "combined").dependencies, ["prep"])
        self.assertNotIn("combined", self.ready("s1"))

    def test_it_runs_when_that_has_finished(self):
        self.apply("s1", analysis("fit"), analysis("prep"), combine("combined", needs=["prep"]))
        self.assertIn("combined", self.ready("s1"))

    def test_it_waits_for_a_need_in_another_subject(self):
        self.apply("central", analysis("prep", status="running"))
        self.apply("s1", analysis("fit"), combine("combined", needs=["central/prep"]))
        self.assertEqual(self.get("s1", "combined").dependencies, ["central/prep"])
        self.assertNotIn("combined", self.ready("s1"))

    def test_it_runs_when_that_has_finished_in_another_subject(self):
        self.apply("central", analysis("prep"))
        self.apply("s1", analysis("fit"), combine("combined", needs=["central/prep"]))
        self.assertIn("combined", self.ready("s1"))

    def test_a_need_is_not_something_it_combines(self):
        self.apply("s1", analysis("fit"), analysis("prep", pipeline="simpletestpipelineb"),
                   combine("combined", needs=["prep"], analyses=["'pipeline: simpletestpipeline'"]))
        combined = self.get("s1", "combined")
        self.assertEqual([a.name for a in combined.analyses], ["fit"])
        self.assertEqual(combined.dependencies, ["prep"])

    def test_an_unresolved_qualified_need_holds_it_back_and_says_so(self):
        self.apply("s1", analysis("fit"), combine("combined", needs=["central/typo"]))
        combined = self.get("s1", "combined")
        with patch("asimov.cli.manage.click.echo") as echo:
            held = report_unresolved_needs(combined, self.logger)
        self.assertTrue(held)
        self.assertIn("no analysis is named 'central/typo'", echo.call_args_list[0].args[0])

    def test_it_is_in_the_graph_after_what_it_needs(self):
        self.apply("s1", analysis("fit"), analysis("prep"), combine("combined", needs=["prep"]))
        edges = {(a.name, b.name) for a, b in self.event("s1").graph.edges}
        self.assertIn(("prep", "combined"), edges)

    def test_two_subject_analyses_which_need_each_other_do_not_hang(self):
        self.apply("central", analysis("c0"), combine("c", needs=["s1/s"]))
        self.apply("s1", analysis("s0"), combine("s", needs=["central/c"]))
        self.assertEqual(self.ready("central"), set())
        self.assertEqual(self.ready("s1"), set())


class CombinedAnalysesTests(SubjectNeedsCase):
    def test_it_combines_an_analysis_of_another_subject(self):
        self.apply("central", analysis("prep", status="running"))
        self.apply("s1", analysis("fit"), combine("combined", analyses=["fit", "central/prep"]))
        combined = self.get("s1", "combined")
        self.assertEqual(
            sorted((a.event.name, a.name) for a in combined.analyses),
            [("central", "prep"), ("s1", "fit")],
        )
        # ...and is not ready until that has finished too.
        self.assertFalse(combined.source_analyses_ready())

    def test_it_is_ready_once_all_of_them_have_finished(self):
        self.apply("central", analysis("prep"))
        self.apply("s1", analysis("fit"), combine("combined", analyses=["fit", "central/prep"]))
        self.assertTrue(self.get("s1", "combined").source_analyses_ready())

    def test_every_analysis_which_exists_must_have_finished_but_not_ones_which_do_not(self):
        self.apply("s1", analysis("a"), analysis("b", status="running"), combine("combined"))
        self.assertFalse(self.get("s1", "combined").source_analyses_ready())
        self.apply("s1", analysis("c"))
        # b is still running, and c has joined: not ready, and c is combined too.
        combined = self.get("s1", "combined")
        self.assertEqual(sorted(a.name for a in combined.analyses), ["a", "b", "c"])
        self.assertFalse(combined.source_analyses_ready())

    def test_one_which_has_not_been_added_yet_does_not_hold_it_up(self):
        self.apply("s1", analysis("a"), analysis("b"), combine("combined"))
        self.assertTrue(self.get("s1", "combined").source_analyses_ready())

    def test_it_is_stale_when_another_one_appears(self):
        self.apply("central", analysis("prep"))
        self.apply("s1", analysis("fit"),
                   combine("combined", analyses=["fit", "central/prep", "central/more"]))
        combined = self.get("s1", "combined")
        combined.resolved_dependencies = ["fit", "central/prep"]
        self.assertFalse(combined.is_stale)  # central/more does not exist yet
        self.apply("central", analysis("more"))
        combined = self.get("s1", "combined")
        combined.resolved_dependencies = ["fit", "central/prep"]
        self.assertTrue(combined.is_stale)
        combined.resolved_dependencies = ["fit", "central/prep", "central/more"]
        self.assertFalse(combined.is_stale)

    def test_a_bare_name_for_one_in_another_subject_is_not_the_same_dependency(self):
        self.apply("central", analysis("prep"))
        self.apply("s1", analysis("fit"), combine("combined", analyses=["fit", "central/prep"]))
        combined = self.get("s1", "combined")
        combined.resolved_dependencies = ["fit", "prep"]
        self.assertTrue(combined.is_stale)


class StoredFormTests(SubjectNeedsCase):
    def stored(self, name):
        import yaml
        with open(".asimov/ledger.yml") as handle:
            stored = yaml.safe_load(handle)
        for event in stored["events"]:
            for production in event.get("productions", []):
                if name in production:
                    return production[name]

    def test_needs_and_analyses_are_stored_as_written(self):
        self.apply("central", analysis("prep"))
        self.apply("s1", analysis("fit"),
                   combine("combined", needs=["central/prep"], analyses=["fit"]))
        ledger = YAMLLedger(".asimov/ledger.yml")
        ledger.update_event(ledger.get_event("s1")[0])
        stored = self.stored("combined")
        self.assertEqual(stored["needs"], ["central/prep"])
        self.assertEqual(stored["analyses"], ["fit"])

    def test_it_is_unchanged_by_loading_and_writing_again(self):
        self.apply("s1", analysis("fit"), combine("combined", needs=["fit"], analyses=["fit"]))
        for _ in range(2):
            ledger = YAMLLedger(".asimov/ledger.yml")
            ledger.update_event(ledger.get_event("s1")[0])
        stored = self.stored("combined")
        self.assertEqual((stored["needs"], stored["analyses"]), (["fit"], ["fit"]))

    def test_without_analyses_needs_is_still_what_it_combines(self):
        event = self.event("s1")
        self.apply("s1", analysis("fit"))
        event = self.event("s1")
        legacy = SubjectAnalysis.from_dict(
            {"name": "legacy", "pipeline": "subjecttestpipeline", "needs": ["fit"]},
            subject=event,
        )
        self.assertEqual([a.name for a in legacy.analyses], ["fit"])
        self.assertEqual(legacy.dependencies, [])


if __name__ == "__main__":
    unittest.main()
