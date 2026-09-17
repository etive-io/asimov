"""
This file contains code to allow unittests to be written with
Asimov so that productions can be tested with minimal boilerplate.
This module contains the factory classes for other asimov tests.
"""

import os
import unittest
import shutil
import git
from asimov import current_ledger as ledger
from asimov.cli.project import make_project
from asimov.ledger import YAMLLedger


class AsimovTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cwd = os.getcwd()
        git.Repo.init(cls.cwd + "/tests/test_data/s000000xx/")

    def setUp(self):
        os.makedirs(f"{self.cwd}/tests/tmp/project")
        os.chdir(f"{self.cwd}/tests/tmp/project")
        make_project(
            name="Test project", root=f"{self.cwd}/tests/tmp/project", engine="yamlfile"
        )
        self.ledger = YAMLLedger(".asimov/ledger.yml")

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(f"{self.cwd}/tests/tmp/")


class AsimovTest(unittest.TestCase):
    """
    Overloads the unittest.TestCase code.
    Simply makes `self.events` available to the test case.
    """

    @classmethod
    def setUpClass(cls):
        cls.events = ledger.get_event()
