"""
A ledger records the features it depends on (#231), so that the person applying
is told that an older asimov will misread it. It only warns.
"""
import logging
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

import asimov
from asimov import features
from asimov.cli.application import apply_page
from asimov.cli.project import make_project
from asimov.context import ProjectContext
from asimov.ledger import DatabaseLedger, YAMLLedger

from tests.test_subject_analysis_needs import EVENT, analysis, combine


class FeatureCase(unittest.TestCase):
    def setUp(self):
        self.cwd = os.getcwd()
        self.root = tempfile.mkdtemp()
        os.chdir(self.root)
        self.ledger = self.make_ledger()
        for name in ("EvA", "EvB"):
            self.write("event.yaml", EVENT.format(name=name))
            apply_page("event.yaml", ledger=self.ledger)

    def make_ledger(self):
        make_project(name="Test project", root=self.root, engine="yamlfile")
        return YAMLLedger(".asimov/ledger.yml")

    def reopen(self):
        return YAMLLedger(".asimov/ledger.yml")

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, name, text):
        with open(name, "w") as handle:
            handle.write(text)

    def apply(self, event, *blueprints, **kwargs):
        self.write("blueprint.yaml", "---\n".join(blueprints))
        return apply_page("blueprint.yaml", event=event, ledger=self.ledger, **kwargs)

    def messages(self, plan):
        return [p.message for p in plan.problems if p.level == "warning"]


class RecordingTests(FeatureCase):
    def test_a_ledger_starts_with_none(self):
        self.assertEqual(features.recorded(self.reopen()), {})

    def test_a_need_on_another_subject_records_the_feature(self):
        plan = self.apply("EvA", analysis("a", "ready", needs=["EvB/fit"]))
        self.assertEqual(
            features.recorded(self.reopen()), {"cross-subject-needs": asimov.__version__}
        )
        self.assertTrue(any("cross-subject" in m or "another subject" in m for m in self.messages(plan)))

    def test_so_does_a_subject_filter(self):
        self.apply("EvA", analysis("a", "ready", needs=["'subject: EvB'"]))
        self.assertIn("cross-subject-needs", features.recorded(self.reopen()))

    def test_so_does_an_optional_need(self):
        self.write("blueprint.yaml", (
            "kind: analysis\nname: a\npipeline: simpletestpipeline\nstatus: ready\n"
            "needs:\n  - name: EvB/fit\n    optional: true\n"
        ))
        apply_page("blueprint.yaml", event="EvA", ledger=self.ledger)
        self.assertIn("cross-subject-needs", features.recorded(self.reopen()))

    def test_a_need_in_its_own_subject_does_not(self):
        plan = self.apply("EvA", analysis("a", "finished"), analysis("b", "ready", needs=["a"]))
        self.assertEqual(features.recorded(self.reopen()), {})
        self.assertEqual(self.messages(plan), [])

    def test_a_subject_analysis_with_analyses_and_needs_records_its_feature(self):
        self.apply("EvA", analysis("a", "finished"), combine("c", needs=["a"]))
        self.assertIn("subject-analysis-needs", features.recorded(self.reopen()))

    def test_one_with_only_analyses_does_not(self):
        """Older versions read that as it is meant."""
        plan = self.apply("EvA", analysis("a", "finished"), combine("c"))
        self.assertEqual(features.recorded(self.reopen()), {})
        self.assertEqual(self.messages(plan), [])

    def test_one_in_the_old_form_does_not(self):
        """``needs:`` alone is what it combines, as it always was."""
        plan = self.apply(
            "EvA", analysis("a", "finished"),
            analysis("c", "ready", needs=["'pipeline: simpletestpipeline'"], pipeline="subjecttestpipeline"),
        )
        self.assertEqual(features.recorded(self.reopen()), {})

    def test_it_is_said_once(self):
        first = self.apply("EvA", analysis("a", "ready", needs=["EvB/fit"]))
        second = self.apply("EvA", analysis("b", "ready", needs=["EvB/fit"]))
        self.assertEqual(len(self.messages(first)), 1)
        self.assertEqual(self.messages(second), [])

    def test_the_first_recording_is_kept(self):
        self.apply("EvA", analysis("a", "ready", needs=["EvB/fit"]))
        with patch.object(asimov, "__version__", "9.9.9"):
            self.apply("EvA", analysis("b", "ready", needs=["EvB/fit"]))
            self.apply("EvA", combine("c", needs=["a"]))
        recorded = features.recorded(self.reopen())
        self.assertEqual(recorded["cross-subject-needs"], asimov.__version__)
        self.assertEqual(recorded["subject-analysis-needs"], "9.9.9")

    def test_a_dry_run_says_it_and_records_nothing(self):
        plan = self.apply("EvA", analysis("a", "ready", needs=["EvB/fit"]), dry_run=True)
        self.assertEqual(len(self.messages(plan)), 1)
        self.assertEqual(features.recorded(self.reopen()), {})

    def test_it_is_only_a_warning(self):
        plan = self.apply("EvA", analysis("a", "ready", needs=["EvB/fit"]))
        self.assertEqual([p for p in plan.problems if p.level == "error" and "feature" in p.message], [])
        names = [a.name for a in self.reopen().get_event("EvA")[0].productions]
        self.assertEqual(names, ["a"])

    def test_failing_to_record_does_not_fail_the_apply(self):
        with patch("asimov.features.record", side_effect=RuntimeError("boom")):
            self.apply("EvA", analysis("a", "ready", needs=["EvB/fit"]))
        names = [a.name for a in self.reopen().get_event("EvA")[0].productions]
        self.assertEqual(names, ["a"])


class ReadingTests(FeatureCase):
    def record(self, names):
        self.ledger.data.setdefault("asimov", {})["features"] = {n: "99.0" for n in names}
        self.ledger.save()

    def test_known_features_are_not_remarked_on(self):
        self.record(["cross-subject-needs"])
        with self.assertNoLogs("asimov.features", level="WARNING"):
            features.warn_unknown(self.reopen())

    def test_one_from_a_newer_version_is_warned_about(self):
        self.record(["cross-subject-needs", "from-the-future"])
        with self.assertLogs("asimov.features", level="WARNING") as logs:
            names = features.warn_unknown(self.reopen())
        self.assertEqual(names, ["from-the-future"])
        self.assertIn("from-the-future", logs.output[0])
        self.assertIn("upgrade", logs.output[0])

    def test_opening_the_project_warns_once(self):
        self.record(["from-the-future"])
        context = ProjectContext.from_directory(self.root)
        with self.assertLogs("asimov.features", level="WARNING") as logs:
            context.ledger
            context.ledger
        self.assertEqual(len(logs.output), 1)

    def test_a_ledger_which_cannot_be_read_does_not_fail(self):
        class Broken:
            @property
            def data(self):
                raise RuntimeError("no")

        self.assertEqual(features.warn_unknown(Broken()), [])

    def test_a_ledger_with_a_malformed_record_does_not_fail(self):
        self.ledger.data["asimov"] = {"features": ["a", "list"]}
        self.assertEqual(features.recorded(self.ledger), {})
        self.ledger.data["asimov"] = None
        self.assertEqual(features.recorded(self.ledger), {})


class DatabaseLedgerTests(FeatureCase):
    def make_ledger(self):
        make_project(name="Test project", root=self.root, engine="yamlfile")
        self.location = f"sqlite:///{self.root}/ledger.db"
        ledger = DatabaseLedger(engine="sqlalchemy", location=self.location)
        ledger.db.create_tables()
        return ledger

    def reopen(self):
        return DatabaseLedger(engine="sqlalchemy", location=self.location)

    def test_the_record_is_kept_and_not_repeated(self):
        first = self.apply("EvA", analysis("a", "ready", needs=["EvB/fit"]))
        self.assertEqual(len(self.messages(first)), 1)
        self.assertIn("cross-subject-needs", features.recorded(self.reopen()))
        second = self.apply("EvA", analysis("b", "ready", needs=["EvB/fit"]))
        self.assertEqual(self.messages(second), [])


class RegistryTests(unittest.TestCase):
    def test_every_feature_says_what_an_older_version_does(self):
        for name, text in features.FEATURES.items():
            self.assertTrue(text, name)
            self.assertEqual(features.describe(name), text)

    def test_an_unknown_name_is_described_by_itself(self):
        self.assertEqual(features.describe("nothing"), "nothing")


if __name__ == "__main__":
    unittest.main()
