"""Tests for the Bilby interface."""

import unittest
import shutil
import os
import git

from click.testing import CliRunner
from asimov.pipelines.bilby import Bilby
from asimov.event import Event
from asimov.pipeline import PipelineException
from asimov import config
from asimov.cli import project
from asimov.cli import configuration
from asimov.cli import manage
from asimov.cli.application import apply_page
from asimov.ledger import YAMLLedger
import io
import contextlib
from tests.blueprints import DEFAULTS_PE, DEFAULTS_PE_PRIORS, EVENTS as BLUEPRINT_EVENTS, PIPELINES

class BilbyTests(unittest.TestCase):
    """Test bilby interface"""

    @classmethod
    def setUpClass(cls):
        cls.cwd = os.getcwd()

    def setUp(self):
        os.makedirs(f"{self.cwd}/tests/tmp/project")
        os.chdir(f"{self.cwd}/tests/tmp/project")
        runner = CliRunner()
        result = runner.invoke(project.init,
                               ['Test Project', '--root', f"{self.cwd}/tests/tmp/project"])
        assert result.exit_code == 0
        assert result.output == '● New project created successfully!\n'
        self.ledger = YAMLLedger(f".asimov/ledger.yml")

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(f"{self.cwd}/tests/tmp/project/")

    @unittest.skip("I need to get this to work properly.")
    def test_build_cli(self):
        """Check that a bilby config file can be built."""
        apply_page(file=DEFAULTS_PE, event=None, ledger=self.ledger)
        apply_page(file=DEFAULTS_PE_PRIORS, event=None, ledger=self.ledger)
        event = "GW150914_095045"
        pipeline = "bilby"
        apply_page(file=BLUEPRINT_EVENTS[event], event=None, ledger=self.ledger)
        apply_page(file=PIPELINES[pipeline], event=event, ledger=self.ledger)

        runner = CliRunner()
        result = runner.invoke(manage.build, "--dryrun")
        self.assertTrue("bilby_pipe" in result.output)

    def test_build_api(self):
        """Check that a bilby config file can be built."""
        apply_page(file=DEFAULTS_PE, event=None, ledger=self.ledger)
        apply_page(file=DEFAULTS_PE_PRIORS, event=None, ledger=self.ledger)
        event = "GW150914_095045"
        pipeline = "bilby"
        apply_page(file=BLUEPRINT_EVENTS[event], event=None, ledger=self.ledger)
        apply_page(file=PIPELINES[pipeline], event=event, ledger=self.ledger)

        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            self.ledger.get_event(event)[0].productions[0].pipeline.build_dag(dryrun=True)
            print(f.getvalue())
            self.assertTrue("bilby_pipe" in f.getvalue())
        
    def test_read_ini(self):
        """Check that a bilby ini file can be read correctly."""
        apply_page(file=DEFAULTS_PE, event=None, ledger=self.ledger)
        apply_page(file=DEFAULTS_PE_PRIORS, event=None, ledger=self.ledger)
        event = "GW150914_095045"
        pipeline = "bilby"
        apply_page(file=BLUEPRINT_EVENTS[event], event=None, ledger=self.ledger)
        apply_page(file=PIPELINES[pipeline], event=event, ledger=self.ledger)

        if not config.has_section("scheduler"):
            config.add_section("scheduler")
        if not config.has_section("slurm"):
            config.add_section("slurm")

        config.set("scheduler", "type", "slurm")
        config.set("slurm", "user", "slurmtest")

        config_path = os.path.join(self.cwd, "tests", "tmp", "project", "bilby-test.ini")
        self.ledger.get_event(event)[0].productions[0].make_config(config_path)

        bilby_config = Bilby.read_ini(config_path)
        self.assertEqual(bilby_config.get("root", "scheduler"), "slurm")
        self.assertEqual(bilby_config.get("root", "accounting_user"), "slurmtest")
