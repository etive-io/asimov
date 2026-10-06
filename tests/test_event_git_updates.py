"""
Event repositories are only touched when they have to be (#242).

* ``manage build --dryrun`` must not create or update repositories.
* A repository with no remote has nothing to ``pull`` or ``git lfs fetch``.
"""
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from click.testing import CliRunner

from asimov import config
from asimov.cli import manage
from asimov.cli.application import apply_page
from asimov.cli.project import make_project
from asimov.ledger import YAMLLedger

try:
    import git
    from asimov.git import EventRepo
except ImportError:  # pragma: no cover
    git = None
    EventRepo = None

ANALYSIS = """
kind: analysis
name: Prod0
pipeline: simpletestpipeline
status: ready
"""


@unittest.skipIf(git is None, "GitPython is not installed")
class BuildDryRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cwd = os.getcwd()

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls.cwd)

    def setUp(self):
        self.root = f"{self.cwd}/tests/tmp/git_dryrun_project"
        os.makedirs(self.root)
        os.chdir(self.root)
        make_project(name="Test project", root=self.root, engine="yamlfile")
        self.ledger = YAMLLedger(".asimov/ledger.yml")
        apply_page(file=f"{self.cwd}/tests/test_data/testing_pe.yaml", event=None, ledger=self.ledger)
        apply_page(file=f"{self.cwd}/tests/test_data/events_blueprint.yaml", ledger=self.ledger)
        with open("blueprint.yaml", "w") as handle:
            handle.write(ANALYSIS)
        apply_page(file="blueprint.yaml", event="GW150914_095045", ledger=self.ledger)

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.root, ignore_errors=True)

    def build(self, *arguments):
        ledger = YAMLLedger(".asimov/ledger.yml")
        with patch("asimov.cli.manage.ledger", new=ledger), patch.object(
            EventRepo, "update"
        ) as update:
            result = CliRunner().invoke(manage.build, list(arguments))
        return result, update

    def test_a_dry_run_does_not_update_the_repository(self):
        result, update = self.build("--dryrun")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Prod0", result.output)
        update.assert_not_called()

    def test_a_real_build_still_looks_for_the_file_upstream(self):
        result, update = self.build()
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertTrue(update.called)


@unittest.skipIf(git is None, "GitPython is not installed")
class UpdateWithoutARemoteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.location = os.path.join(self.tmp, "GW150914")
        old = config.get("general", "event_git", fallback=None)
        config.set("general", "event_git", "true")

        def restore():
            if old is None:
                config.remove_option("general", "event_git")
            else:
                config.set("general", "event_git", old)

        self.addCleanup(restore)
        self.repo = EventRepo.create(self.location)
        self.repo.get_default_branch()  # initialises the repository
        self.addCleanup(self.repo.close)

    def commands_run_by_update(self):
        recorded = []

        def record(_git, command, *args, **kwargs):
            recorded.append([str(part) for part in command])
            return ""

        with patch("git.cmd.Git.execute", record):
            self.repo.update()
        return recorded

    def has(self, recorded, word):
        return any(word in command for command in recorded)

    def test_no_pull_or_lfs_fetch_without_a_remote(self):
        recorded = self.commands_run_by_update()
        self.assertTrue(self.has(recorded, "checkout"), recorded)
        self.assertFalse(self.has(recorded, "pull"), recorded)
        self.assertFalse(self.has(recorded, "lfs"), recorded)
        self.assertTrue(self.repo._updated)

    def test_pull_and_lfs_fetch_with_a_remote(self):
        git.Repo(self.location).create_remote("origin", os.path.join(self.tmp, "upstream"))
        recorded = self.commands_run_by_update()
        self.assertTrue(self.has(recorded, "checkout"), recorded)
        self.assertTrue(self.has(recorded, "pull"), recorded)
        self.assertTrue(self.has(recorded, "lfs"), recorded)


if __name__ == "__main__":
    unittest.main()
