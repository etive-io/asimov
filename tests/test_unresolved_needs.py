"""
Tests for ``needs`` entries which match no analysis (#244).

Such an entry contributes no dependency, so the analysis used to be treated as
having no dependency on it.  It is now reported, and held back when it sets
``strict needs``.
"""
import logging
import os
import shutil
import unittest
from unittest import mock

from asimov.cli.application import apply_page
from asimov.cli.manage import report_unresolved_needs
from asimov.cli.project import make_project
from asimov.ledger import YAMLLedger

EVENT = "GW150914_095045"


class UnresolvedNeedsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cwd = os.getcwd()

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls.cwd)

    def setUp(self):
        self.root = f"{self.cwd}/tests/tmp/unresolved_needs_project"
        os.makedirs(self.root)
        os.chdir(self.root)
        make_project(name="Test project", root=self.root, engine="yamlfile")
        self.ledger = YAMLLedger(".asimov/ledger.yml")
        apply_page(file=f"{self.cwd}/tests/test_data/testing_pe.yaml", event=None, ledger=self.ledger)
        apply_page(file=f"{self.cwd}/tests/test_data/events_blueprint.yaml", ledger=self.ledger)
        self.logger = logging.getLogger("test_unresolved_needs")

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.root, ignore_errors=True)

    def analysis(self, blueprint, name):
        with open("blueprint.yaml", "w") as handle:
            handle.write(blueprint)
        apply_page(file="blueprint.yaml", event=EVENT, ledger=self.ledger)
        event = self.ledger.get_event(EVENT)[0]
        return [p for p in event.productions if p.name == name][0]

    def test_misspelt_name_is_reported(self):
        prod = self.analysis(
            """
kind: analysis
name: Prod0
pipeline: simpletestpipeline
status: finished
---
kind: analysis
name: Prod1
pipeline: simpletestpipelineb
needs:
  - Prod0-typo
""",
            "Prod1",
        )
        self.assertEqual(prod.dependencies, [])
        self.assertEqual(prod.unresolved_needs, ["no analysis is named 'Prod0-typo'"])
        self.assertFalse(prod.has_required_dependencies_satisfied)

    def test_resolved_name_is_not_reported(self):
        prod = self.analysis(
            """
kind: analysis
name: Prod0
pipeline: simpletestpipeline
status: finished
---
kind: analysis
name: Prod1
pipeline: simpletestpipelineb
needs:
  - Prod0
""",
            "Prod1",
        )
        self.assertEqual(prod.unresolved_needs, [])
        self.assertTrue(prod.has_required_dependencies_satisfied)

    def test_filter_which_matches_nothing_is_worded_differently(self):
        prod = self.analysis(
            """
kind: analysis
name: Prod1
pipeline: simpletestpipelineb
needs:
  - pipeline: simpletestpipeline
""",
            "Prod1",
        )
        self.assertEqual(
            prod.unresolved_needs, ["no analysis matches pipeline = simpletestpipeline"]
        )

    def test_and_group_which_matches_nothing(self):
        prod = self.analysis(
            """
kind: analysis
name: Prod0
pipeline: simpletestpipeline
status: finished
---
kind: analysis
name: Prod1
pipeline: simpletestpipelineb
needs:
  - - pipeline: simpletestpipeline
    - status: ready
""",
            "Prod1",
        )
        self.assertEqual(
            prod.unresolved_needs,
            ["no analysis matches pipeline = simpletestpipeline and status = ready"],
        )

    def test_optional_entry_is_not_reported(self):
        prod = self.analysis(
            """
kind: analysis
name: Prod1
pipeline: simpletestpipelineb
needs:
  - optional: true
    pipeline: simpletestpipeline
""",
            "Prod1",
        )
        self.assertEqual(prod.unresolved_needs, [])

    def test_only_unresolved_entries_are_reported(self):
        prod = self.analysis(
            """
kind: analysis
name: Prod0
pipeline: simpletestpipeline
status: finished
---
kind: analysis
name: Prod1
pipeline: simpletestpipelineb
needs:
  - Prod0
  - missing
""",
            "Prod1",
        )
        self.assertEqual(prod.unresolved_needs, ["no analysis is named 'missing'"])

    def test_no_needs(self):
        prod = self.analysis(
            """
kind: analysis
name: Prod1
pipeline: simpletestpipelineb
""",
            "Prod1",
        )
        self.assertEqual(prod.unresolved_needs, [])

    def test_strict_needs_defaults_to_false(self):
        prod = self.analysis(
            """
kind: analysis
name: Prod1
pipeline: simpletestpipelineb
needs:
  - missing
""",
            "Prod1",
        )
        self.assertFalse(prod.strict_needs)

    def test_strict_needs_can_be_set(self):
        prod = self.analysis(
            """
kind: analysis
name: Prod1
pipeline: simpletestpipelineb
strict needs: true
needs:
  - missing
""",
            "Prod1",
        )
        self.assertTrue(prod.strict_needs)

    def test_report_warns_but_does_not_hold_by_default(self):
        prod = self.analysis(
            """
kind: analysis
name: Prod1
pipeline: simpletestpipelineb
needs:
  - missing
""",
            "Prod1",
        )
        with mock.patch("asimov.cli.manage.click.echo") as echo:
            hold = report_unresolved_needs(prod, self.logger)
        self.assertFalse(hold)
        self.assertIn("no analysis is named 'missing'", echo.call_args[0][0])

    def test_report_holds_a_strict_analysis(self):
        prod = self.analysis(
            """
kind: analysis
name: Prod1
pipeline: simpletestpipelineb
strict needs: true
needs:
  - missing
""",
            "Prod1",
        )
        with mock.patch("asimov.cli.manage.click.echo") as echo:
            hold = report_unresolved_needs(prod, self.logger)
        self.assertTrue(hold)
        self.assertIn("strict needs", echo.call_args[0][0])

    def test_report_is_silent_when_everything_resolves(self):
        prod = self.analysis(
            """
kind: analysis
name: Prod0
pipeline: simpletestpipeline
status: finished
---
kind: analysis
name: Prod1
pipeline: simpletestpipelineb
strict needs: true
needs:
  - Prod0
""",
            "Prod1",
        )
        with mock.patch("asimov.cli.manage.click.echo") as echo:
            hold = report_unresolved_needs(prod, self.logger)
        self.assertFalse(hold)
        echo.assert_not_called()


if __name__ == "__main__":
    unittest.main()
