"""
``Analysis.dependencies`` resolves ``needs`` against every analysis in the
subject each time it is read, so code which needs it more than once in a call
should read it once (#242).
"""
import os
import shutil
import unittest
from unittest.mock import PropertyMock, patch

from asimov.analysis import Analysis
from asimov.cli.application import apply_page
from asimov.cli.project import make_project
from asimov.ledger import YAMLLedger

BLUEPRINT = """
kind: analysis
name: Prod0
pipeline: simpletestpipeline
status: finished
---
kind: analysis
name: Prod1
pipeline: simpletestpipeline
status: ready
needs: [Prod0]
"""


class DependencyReadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cwd = os.getcwd()

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls.cwd)

    def setUp(self):
        self.root = f"{self.cwd}/tests/tmp/dependency_reads_project"
        os.makedirs(self.root)
        os.chdir(self.root)
        make_project(name="Test project", root=self.root, engine="yamlfile")
        self.ledger = YAMLLedger(".asimov/ledger.yml")
        apply_page(file=f"{self.cwd}/tests/test_data/testing_pe.yaml", event=None, ledger=self.ledger)
        apply_page(file=f"{self.cwd}/tests/test_data/events_blueprint.yaml", ledger=self.ledger)
        with open("blueprint.yaml", "w") as handle:
            handle.write(BLUEPRINT)
        apply_page(file="blueprint.yaml", event="GW150914_095045", ledger=self.ledger)
        event = self.ledger.get_event("GW150914_095045")[0]
        self.prod1 = [p for p in event.productions if p.name == "Prod1"][0]

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.root, ignore_errors=True)

    def reads(self, call):
        with patch.object(
            Analysis, "dependencies", new_callable=PropertyMock, return_value=["Prod0"]
        ) as dependencies:
            call()
        return dependencies.call_count

    def test_collecting_psds_reads_dependencies_once(self):
        self.assertEqual(self.reads(self.prod1._collect_psds), 1)

    def test_collecting_xml_psds_reads_dependencies_once(self):
        self.assertEqual(self.reads(lambda: self.prod1._collect_psds(format="xml")), 1)

    def test_previous_assets_reads_dependencies_once(self):
        self.assertEqual(self.reads(self.prod1._previous_assets), 1)

    def test_an_analysis_with_no_needs_is_unchanged(self):
        prod0 = [p for p in self.prod1.event.productions if p.name == "Prod0"][0]
        self.assertEqual(prod0._previous_assets(), {})
        self.assertEqual(prod0.dependencies, [])
        self.assertEqual(self.prod1.dependencies, ["Prod0"])


if __name__ == "__main__":
    unittest.main()
