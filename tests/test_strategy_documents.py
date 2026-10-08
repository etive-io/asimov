"""
A plugin strategy can return documents of more than one kind (#232): subjects,
and the analyses which are in them, as well as project analyses.

The strategy is expanded where the documents of a blueprint are read, so what it
returns goes through the same handling as a hand-written blueprint of those
documents.
"""
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

import yaml

from asimov.cli.application import apply_page
from asimov.cli.project import make_project
from asimov.ledger import YAMLLedger
from asimov.strategies import Strategy, StrategyError

from tests.test_plugin_strategies import plugins

EVENT = "kind: event\nname: Base\ninterferometers: [H1]\n"

BLUEPRINT = """kind: analysis
name: scan
pipeline: simpletestpipeline
status: ready
strategy:
  type: scan
"""


def analysis(name, event, **extra):
    return {"kind": "analysis", "name": name, "pipeline": "simpletestpipeline",
            "status": "ready", "event": event, **extra}


def subject(name):
    return {"kind": "subject", "name": name, "interferometers": ["H1"]}


class Scan(Strategy):
    """Makes a subject for each stream, and an analysis in each."""

    produce = None

    def expand(self, blueprint, context):
        return type(self).produce(blueprint, context)


def streams(names=("S1", "S2")):
    def produce(blueprint, context):
        documents = []
        for name in names:
            documents.append(subject(name))
            documents.append(analysis(f"fit-{name}", name))
        documents.append(analysis("combine", names[0], needs=[f"fit-{names[0]}"]))
        return documents

    return produce


class DocumentsCase(unittest.TestCase):
    def setUp(self):
        self.cwd = os.getcwd()
        self.root = tempfile.mkdtemp()
        os.chdir(self.root)
        make_project(name="Test project", root=self.root, engine="yamlfile")
        self.ledger = YAMLLedger(".asimov/ledger.yml")
        self.write("event.yaml", EVENT)
        apply_page("event.yaml", ledger=self.ledger)
        Scan.produce = staticmethod(streams())

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, name, text):
        with open(name, "w") as handle:
            handle.write(text)

    def apply(self, text=BLUEPRINT, **kwargs):
        self.write("blueprint.yaml", text)
        with plugins(scan=Scan):
            return apply_page("blueprint.yaml", ledger=self.ledger, **kwargs)

    def subjects(self):
        return sorted(YAMLLedger(".asimov/ledger.yml").events)

    def analyses(self, event):
        fresh = YAMLLedger(".asimov/ledger.yml")
        return {a.name: a for a in fresh.get_event(event)[0].productions}


class SubjectsAndAnalysesTests(DocumentsCase):
    def test_the_subjects_are_made_and_the_analyses_are_in_them(self):
        self.apply()
        self.assertEqual(self.subjects(), ["Base", "S1", "S2"])
        self.assertEqual(sorted(self.analyses("S1")), ["combine", "fit-S1"])
        self.assertEqual(sorted(self.analyses("S2")), ["fit-S2"])
        self.assertEqual(self.analyses("Base"), {})

    def test_needs_between_the_analyses_are_kept(self):
        self.apply()
        self.assertEqual(self.analyses("S1")["combine"].dependencies, ["fit-S1"])

    def test_the_analyses_are_stamped_and_the_subjects_are_not(self):
        self.apply()
        for event in ("S1", "S2"):
            for made in self.analyses(event).values():
                self.assertEqual(made.meta["strategy"], {"type": "scan", "id": "scan"})
        meta = YAMLLedger(".asimov/ledger.yml").get_event("S1")[0].meta
        self.assertNotIn("strategy", meta)

    def test_a_subject_does_not_pass_a_stamp_on_to_other_analyses(self):
        self.apply()
        plain = "kind: analysis\nname: plain\npipeline: simpletestpipeline\nstatus: ready\n"
        self.write("plain.yaml", plain)
        apply_page("plain.yaml", event="S2", ledger=self.ledger)
        self.assertNotIn("strategy", self.analyses("S2")["plain"].meta)

    def test_applying_it_again_leaves_everything_as_it_was_and_says_so(self):
        self.apply()
        before = yaml.safe_load(open(".asimov/ledger.yml"))
        with patch("asimov.cli.application.click.echo") as echo:
            self.apply()
        self.assertEqual(yaml.safe_load(open(".asimov/ledger.yml")), before)
        text = " ".join(str(call.args[0]) for call in echo.call_args_list)
        self.assertIn("5 of 5 documents of 'scan' already existed", text)
        self.assertNotIn("already exists in this project", text)

    def test_a_new_stream_added_later_adds_only_what_is_new(self):
        self.apply()
        Scan.produce = staticmethod(streams(("S1", "S2", "S3")))
        self.apply()
        self.assertEqual(self.subjects(), ["Base", "S1", "S2", "S3"])
        self.assertEqual(sorted(self.analyses("S3")), ["fit-S3"])

    def test_an_existing_subject_is_not_updated(self):
        self.write("s1.yaml", "kind: event\nname: S1\ninterferometers: [L1]\n")
        apply_page("s1.yaml", ledger=self.ledger)
        self.apply()
        meta = YAMLLedger(".asimov/ledger.yml").get_event("S1")[0].meta
        self.assertEqual(meta["interferometers"], ["L1"])
        self.assertEqual(sorted(self.analyses("S1")), ["combine", "fit-S1"])


class WhichSubjectTests(DocumentsCase):
    def single(self, **extra):
        return lambda b, c: [{"kind": "analysis", "name": "a", "pipeline": "simpletestpipeline",
                              "status": "ready", **extra}]

    def test_an_analysis_with_no_subject_is_for_the_one_given_to_the_command(self):
        Scan.produce = staticmethod(self.single())
        self.apply(event="Base")
        self.assertEqual(sorted(self.analyses("Base")), ["a"])

    def test_it_is_for_the_subject_of_the_blueprint_if_there_is_one(self):
        Scan.produce = staticmethod(self.single())
        self.apply(BLUEPRINT + "event: Base\n")
        self.assertEqual(sorted(self.analyses("Base")), ["a"])

    def test_otherwise_the_user_is_asked_once_for_all_of_them(self):
        Scan.produce = staticmethod(
            lambda b, c: [{k: v for k, v in analysis(n, None).items() if k != "event"}
                          for n in ("a", "b")]
        )
        with patch("asimov.cli.application.click.prompt", return_value="Base") as prompt:
            self.apply()
        prompt.assert_called_once()
        self.assertEqual(sorted(self.analyses("Base")), ["a", "b"])

    def test_a_subject_the_strategy_names_wins_over_the_command(self):
        Scan.produce = staticmethod(streams(("S1",)))
        self.apply(event="Base")
        self.assertEqual(sorted(self.analyses("S1")), ["combine", "fit-S1"])
        self.assertEqual(self.analyses("Base"), {})

    def test_the_command_replaces_a_subject_the_strategy_copied_from_the_blueprint(self):
        Scan.produce = staticmethod(lambda b, c: [analysis("a", b.get("event"))])
        self.write("other.yaml", "kind: event\nname: Other\ninterferometers: [H1]\n")
        apply_page("other.yaml", ledger=self.ledger)
        self.apply(BLUEPRINT + "event: Base\n", event="Other")
        self.assertEqual(sorted(self.analyses("Other")), ["a"])
        self.assertEqual(self.analyses("Base"), {})


class CheckedBeforeAnythingIsAppliedTests(DocumentsCase):
    def refused(self, produce):
        Scan.produce = staticmethod(produce)
        with self.assertRaises(StrategyError) as error:
            self.apply()
        self.assertEqual(self.subjects(), ["Base"])
        return str(error.exception)

    def test_an_analysis_for_a_subject_which_does_not_exist_applies_nothing(self):
        message = self.refused(lambda b, c: [subject("S1"), analysis("a", "Nowhere")])
        self.assertIn("'Nowhere', which does not exist", message)

    def test_an_analysis_for_a_subject_made_later_is_refused(self):
        message = self.refused(lambda b, c: [analysis("a", "S1"), subject("S1")])
        self.assertIn("is not made before it", message)

    def test_a_kind_which_cannot_be_returned_is_refused(self):
        message = self.refused(lambda b, c: [{"kind": "configuration", "name": "x"}])
        self.assertIn("it can return", message)

    def test_the_same_name_in_one_subject_twice_is_refused(self):
        message = self.refused(lambda b, c: [subject("S3"), analysis("a", "S3"), analysis("a", "S3")])
        self.assertIn("more than one analysis named 'a'", message)

    def test_the_same_name_in_two_subjects_is_allowed(self):
        Scan.produce = staticmethod(
            lambda b, c: [subject("S1"), subject("S2"), analysis("a", "S1"), analysis("a", "S2")]
        )
        self.apply()
        self.assertEqual(sorted(self.analyses("S1")), ["a"])
        self.assertEqual(sorted(self.analyses("S2")), ["a"])

    def test_two_subjects_of_the_same_name_are_refused(self):
        message = self.refused(lambda b, c: [subject("S9"), subject("S9")])
        self.assertIn("more than one subject named 'S9'", message)

    def test_a_subject_does_not_need_a_pipeline(self):
        Scan.produce = staticmethod(lambda b, c: [subject("S5")])
        self.apply()
        self.assertEqual(self.subjects(), ["Base", "S5"])


class ProjectAnalysisTests(DocumentsCase):
    def project_analysis(self, name="pa"):
        return {"kind": "projectanalysis", "name": name, "pipeline": "projecttestpipeline",
                "subjects": ["Base"], "status": "ready"}

    def test_a_project_analysis_can_be_returned(self):
        Scan.produce = staticmethod(lambda b, c: [self.project_analysis()])
        self.apply()
        found = YAMLLedger(".asimov/ledger.yml").project_analyses
        self.assertEqual([p.name for p in found], ["pa"])

    def test_and_applying_it_again_leaves_it_be(self):
        Scan.produce = staticmethod(lambda b, c: [self.project_analysis()])
        self.apply()
        with patch("asimov.cli.application.click.echo") as echo:
            self.apply()
        found = YAMLLedger(".asimov/ledger.yml").project_analyses
        self.assertEqual([p.name for p in found], ["pa"])
        text = " ".join(str(call.args[0]) for call in echo.call_args_list)
        self.assertIn("1 of 1 documents of 'scan' already existed", text)


class DryRunTests(DocumentsCase):
    def test_a_dry_run_lists_what_would_be_made_and_makes_nothing(self):
        plan = self.apply(dry_run=True)
        self.assertEqual(self.subjects(), ["Base"])
        targets = [change.record.target for change in plan.changes]
        self.assertEqual(
            sorted(targets),
            sorted(["@project/scan", "S1", "S2", "S1/fit-S1", "S2/fit-S2", "S1/combine"]),
        )

    def test_a_dry_run_of_what_exists_is_noted_as_skipped(self):
        self.apply()
        plan = self.apply(dry_run=True)
        self.assertEqual(plan.changes, [])
        self.assertTrue(any("already existed" in r.message and r.level == "skipped"
                            for r in plan.refused))

    def test_a_dry_run_says_nothing_untrue(self):
        with patch("asimov.cli.application.click.echo") as echo:
            self.apply(dry_run=True)
        echo.assert_not_called()


if __name__ == "__main__":
    unittest.main()
