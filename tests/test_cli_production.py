"""
Test the production functions from the CLI
"""

from importlib import reload
import unittest
from unittest.mock import patch

import os
import shutil

from click.testing import CliRunner
import asimov
from asimov.cli.application import apply_page
from asimov.cli import production, project
from asimov.ledger import YAMLLedger
from tests.blueprints import DEFAULTS_PE, DEFAULTS_PE_PRIORS, EVENTS as BLUEPRINT_EVENTS, PIPELINES

EVENT = "GW150914_095045"


class TestProductionSet(unittest.TestCase):
    """
    Test the `asimov production set` command.
    """

    @classmethod
    def setUpClass(cls):
        cls.cwd = os.getcwd()

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(f"{self.cwd}/tests/tmp/")

    def setUp(self):
        os.makedirs(f"{self.cwd}/tests/tmp/project")
        os.chdir(f"{self.cwd}/tests/tmp/project")
        runner = CliRunner()
        result = runner.invoke(
            project.init,
            [
                "Test Project",
                "--root",
                f"{self.cwd}/tests/tmp/project",
                "--engine",
                "yamlfile",
            ],
        )
        assert result.exit_code == 0
        self.ledger = YAMLLedger(".asimov/ledger.yml")

        apply_page(file=DEFAULTS_PE, event=None, ledger=self.ledger)
        apply_page(file=DEFAULTS_PE_PRIORS, event=None, ledger=self.ledger)
        apply_page(file=BLUEPRINT_EVENTS[EVENT], event=None, ledger=self.ledger)
        apply_page(file=PIPELINES["bilby"], event=EVENT, ledger=self.ledger)

    def test_set_status_persists_to_ledger(self):
        """Check that `production set -s <status>` is written back to the ledger file."""
        with patch("asimov.current_ledger", new=YAMLLedger(".asimov/ledger.yml")):
            reload(asimov)
            reload(production)
            runner = CliRunner()

            result = runner.invoke(
                production.production, ["set", "-s", "stop", EVENT, "Prod1"]
            )
            self.assertEqual(result.exit_code, 0)
            self.assertTrue("status updated to stop" in result.output)

        reloaded_ledger = YAMLLedger(".asimov/ledger.yml")
        event = reloaded_ledger.get_event(EVENT)[0]
        production_o = [
            production_i
            for production_i in event.productions
            if production_i.name == "Prod1"
        ][0]
        self.assertEqual(production_o.status, "stop")
