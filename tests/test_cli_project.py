import unittest
import os
import shutil
from click.testing import CliRunner
from asimov.cli import project

class TestCLI_Projects(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cwd = os.getcwd()

    
    def setUp(self):
        os.makedirs(f"{self.cwd}/tests/tmp/project")
        os.chdir(f"{self.cwd}/tests/tmp/project")

    
    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(f"{self.cwd}/tests/tmp/")
        
    def test_project_creation(self):
        os.chdir(f"{self.cwd}/tests/tmp/project")
        runner = CliRunner()
        result = runner.invoke(project.init,
                               ['Test Project', '--root', f"{self.cwd}/tests/tmp/project"])
        assert result.exit_code == 0
        assert result.stdout == '● New project created successfully!\n'

    def test_project_creation_fails_missing_name(self):
        """Check that the command fails if no name is provided"""
        os.chdir(f"{self.cwd}/tests/tmp/project")
        runner = CliRunner()
        result = runner.invoke(project.init,
                               [ '--root', f"{self.cwd}/tests/tmp/project"])
        assert result.exit_code == 2
