"""
Tests for how EventRepo opens and manages git repositories.
"""

import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from asimov import config

try:
    import git
    from asimov.git import EventRepo
except ImportError:  # pragma: no cover
    git = None
    EventRepo = None


@unittest.skipIf(git is None, "GitPython is not installed")
class TestEventRepoGit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.location = os.path.join(self.tmp, "GW150914")
        self.source = os.path.join(self.tmp, "file.txt")
        with open(self.source, "w") as f:
            f.write("content")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _disable_git(self):
        old = config.get("general", "event_git", fallback=None)
        config.set("general", "event_git", "false")

        def restore():
            if old is None:
                config.remove_option("general", "event_git")
            else:
                config.set("general", "event_git", old)

        self.addCleanup(restore)

    def test_create_is_lazy(self):
        repo = EventRepo.create(self.location)
        self.assertTrue(os.path.isdir(self.location))
        self.assertFalse(os.path.exists(os.path.join(self.location, ".git")))

        # First real use initialises the repository.
        repo.get_default_branch()
        self.assertTrue(os.path.isdir(os.path.join(self.location, ".git")))
        self.assertTrue(
            os.path.exists(
                os.path.join(
                    self.location,
                    config.get("general", "calibration_directory"),
                    ".gitkeep",
                )
            )
        )
        repo.close()

    def test_repo_rebuilt_from_directory_in_a_later_process(self):
        # `apply` creates the directory; a later command only has the stored path.
        EventRepo.create(self.location)
        later = EventRepo(self.location)
        later.get_default_branch()
        self.assertTrue(os.path.isdir(os.path.join(self.location, ".git")))
        later.close()

    def test_url_backed_repo_is_not_silently_initialised(self):
        os.makedirs(self.location)
        repo = EventRepo(self.location, url="git@example.org:group/event.git")
        with self.assertRaises(git.exc.InvalidGitRepositoryError):
            repo.repo

    def test_internal_operations_close_their_handles(self):
        repo = EventRepo.create(self.location)
        with patch.object(git.Repo, "close", autospec=True, side_effect=git.Repo.close) as close:
            repo.add_file(self.source, "analyses/file.txt")
            repo.get_default_branch()
        # One handle for add_file and one for get_default_branch.
        self.assertGreaterEqual(close.call_count, 2)
        self.assertIsNone(repo._repo)

    def test_add_file_commits(self):
        repo = EventRepo.create(self.location)
        repo.add_file(self.source, "analyses/file.txt", commit_message="hello")
        with repo._git() as handle:
            self.assertEqual(handle.head.commit.message.strip(), "hello")
        self.assertTrue(os.path.exists(os.path.join(self.location, "analyses", "file.txt")))

    def test_long_lived_handle_is_reused_and_closed(self):
        repo = EventRepo.create(self.location)
        handle = repo.repo
        with repo._git() as inner:
            self.assertIs(inner, handle)
        repo.close()
        self.assertIsNone(repo._repo)

    def test_event_git_disabled_skips_git(self):
        self._disable_git()
        repo = EventRepo.create(self.location)
        repo.add_file(self.source, "analyses/file.txt")
        repo.update()
        self.assertTrue(os.path.exists(os.path.join(self.location, "analyses", "file.txt")))
        self.assertFalse(os.path.exists(os.path.join(self.location, ".git")))

    def test_find_prods_does_not_pull_by_default(self):
        repo = EventRepo.create(self.location)
        calls = []

        def fake_update(self, *args, **kwargs):
            calls.append(1)
            self._updated = True

        with patch.object(EventRepo, "update", fake_update):
            repo.find_prods("Prod0")
            repo.find_prods("Prod1")
        self.assertEqual(calls, [])

    def test_find_prods_pulls_once_when_asked(self):
        repo = EventRepo.create(self.location)
        calls = []

        def fake_update(self, *args, **kwargs):
            calls.append(1)
            self._updated = True

        with patch.object(EventRepo, "update", fake_update):
            repo.find_prods("Prod0", update=True)
            repo.find_prods("Prod1", update=True)
            repo.find_prods("Prod2", update=True)
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
