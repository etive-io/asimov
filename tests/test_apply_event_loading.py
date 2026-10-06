"""
Applying a blueprint of many analyses loads each event once (#242).

Loading an event builds every analysis in it, and ``apply_page`` used to do that
once per analysis applied, which made applying a large blueprint quadratic.  The
event is now loaded once and each analysis is added to it as it is applied.  These
tests check that, and that the result is the same as before.
"""
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from asimov.cli.application import apply_page
from asimov.cli.project import make_project
from asimov.ledger import DatabaseLedger, YAMLLedger

CHAIN = "".join(
    f"""---
kind: analysis
name: a{n}
event: S000000
pipeline: simpletestpipeline
status: ready
{"needs: [a%d]" % (n - 1) if n else ""}
"""
    for n in range(6)
)[4:]

FILTERED = """
kind: analysis
name: all-upstream
event: S000000
pipeline: simpletestpipelineb
status: ready
needs:
  - pipeline: simpletestpipeline
"""

DUPLICATE = """
kind: analysis
name: dup
event: S000000
pipeline: simpletestpipeline
status: ready
---
kind: analysis
name: dup
event: S000000
pipeline: simpletestpipeline
status: ready
"""


class ApplyEventLoadingTests:
    """The tests, run against each ledger engine by the subclasses below."""

    def make_ledger(self):
        raise NotImplementedError

    def setUp(self):
        self.cwd = os.getcwd()
        self.data = f"{self.cwd}/tests/test_data"
        self.test_dir = tempfile.mkdtemp()
        self.ledger = self.make_ledger()
        apply_page(f"{self.data}/test_event.yaml", event="S000000", ledger=self.ledger)

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def blueprint(self, text):
        path = os.path.join(self.test_dir, "blueprint.yaml")
        with open(path, "w") as handle:
            handle.write(text)
        return path

    def event(self):
        return self.ledger.get_event("S000000")[0]

    def test_event_is_loaded_once_for_many_analyses(self):
        with patch.object(self.ledger, "get_event", wraps=self.ledger.get_event) as get_event:
            apply_page(self.blueprint(CHAIN), ledger=self.ledger)
        self.assertEqual(get_event.call_count, 1)
        self.assertEqual(len(self.event().productions), 6)

    def test_analyses_applied_in_one_file_resolve_each_other(self):
        apply_page(self.blueprint(CHAIN), ledger=self.ledger)
        productions = {p.name: p for p in self.event().productions}
        self.assertEqual(productions["a0"].dependencies, [])
        for n in range(1, 6):
            self.assertEqual(productions[f"a{n}"].dependencies, [f"a{n - 1}"])

    def test_filter_dependencies_see_every_earlier_analysis(self):
        apply_page(self.blueprint(CHAIN + "---" + FILTERED), ledger=self.ledger)
        productions = {p.name: p for p in self.event().productions}
        self.assertEqual(
            productions["all-upstream"].dependencies, [f"a{n}" for n in range(6)]
        )

    def test_strategy_expansion_applies_every_analysis(self):
        apply_page(f"{self.data}/test_strategy_matrix.yaml", ledger=self.ledger)
        names = sorted(p.name for p in self.event().productions)
        self.assertEqual(len(names), 4)
        self.assertEqual(len(set(names)), 4)

    def test_a_duplicate_name_is_reported_and_not_added(self):
        with patch("asimov.cli.application.click.echo") as echo:
            apply_page(self.blueprint(DUPLICATE), ledger=self.ledger)
        messages = " ".join(str(call.args[0]) for call in echo.call_args_list if call.args)
        self.assertIn("Successfully applied dup", messages)
        self.assertIn("an analysis already exists with this name", messages)
        self.assertEqual([p.name for p in self.event().productions].count("dup"), 1)

    def test_separate_applies_see_each_others_analyses(self):
        apply_page(self.blueprint(CHAIN), ledger=self.ledger)
        apply_page(self.blueprint(FILTERED), ledger=self.ledger)
        productions = {p.name: p for p in self.event().productions}
        self.assertEqual(len(productions["all-upstream"].dependencies), 6)

    def test_an_event_document_in_the_file_is_not_hidden_by_the_cache(self):
        second = """
kind: event
name: S000001
event time: 901
---
kind: analysis
name: b0
event: S000001
pipeline: simpletestpipeline
status: ready
"""
        apply_page(self.blueprint(CHAIN + "---" + second), ledger=self.ledger)
        self.assertEqual(len(self.event().productions), 6)
        self.assertEqual(
            [p.name for p in self.ledger.get_event("S000001")[0].productions], ["b0"]
        )


class YAMLLedgerApplyTests(ApplyEventLoadingTests, unittest.TestCase):
    def make_ledger(self):
        os.chdir(self.test_dir)
        make_project(name="Test project", root=self.test_dir, engine="yamlfile")
        return YAMLLedger(".asimov/ledger.yml")


class DatabaseLedgerApplyTests(ApplyEventLoadingTests, unittest.TestCase):
    def make_ledger(self):
        db_path = os.path.join(self.test_dir, "ledger.db")
        self.config_patcher = patch("asimov.database.config")
        mock_config = self.config_patcher.start()
        mock_config.get.side_effect = lambda section, key, fallback=None: {
            ("ledger", "engine"): "sqlalchemy",
            ("ledger", "location"): db_path,
        }.get((section, key), fallback or db_path)
        ledger = DatabaseLedger(engine="sqlalchemy")
        ledger.db.create_tables()
        return ledger

    def tearDown(self):
        self.config_patcher.stop()
        super().tearDown()

    def test_adding_subjects_does_not_build_the_existing_ones(self):
        subjects = "".join(
            f"---\nkind: subject\nname: new{n}\nevent time: {900 + n}\n" for n in range(5)
        )[4:]
        with patch.object(
            self.ledger, "_event_from_dict", wraps=self.ledger._event_from_dict
        ) as build:
            apply_page(self.blueprint(subjects), ledger=self.ledger)
        self.assertEqual(build.call_count, 0)
        names = {e.name for e in self.ledger.events}
        self.assertEqual(names, {"S000000"} | {f"new{n}" for n in range(5)})

    def test_an_existing_subject_is_still_recognised(self):
        with patch("asimov.cli.application.click.echo") as echo:
            apply_page(f"{self.data}/test_event.yaml", event="S000000", ledger=self.ledger)
        messages = " ".join(str(call.args[0]) for call in echo.call_args_list if call.args)
        self.assertIn("already exists in this project", messages)


if __name__ == "__main__":
    unittest.main()
