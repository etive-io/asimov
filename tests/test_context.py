"""
Tests for ProjectContext, and the transaction scope it owns (issues #180, #212).
"""

import os
import shutil
import tempfile
import threading
import unittest

import asimov
from asimov.cli.project import make_project
from asimov.context import (
    ConfigProxy,
    NoProjectError,
    ProjectContext,
    current_context,
    get_active_context,
)
from asimov.database import AsimovSQLDatabase
from asimov.event import Event
from asimov.project import Project


def make_project_in(root, name, engine):
    """Create a project, leaving the working directory where it was."""
    origin = os.getcwd()
    try:
        make_project(name=name, root=root, engine=engine)
    finally:
        os.chdir(origin)
    return root


class ProjectsTestCase(unittest.TestCase):
    """Makes temporary projects, and removes them."""

    def setUp(self):
        self._dirs = []
        self._origin = os.getcwd()

    def tearDown(self):
        os.chdir(self._origin)
        for path in self._dirs:
            shutil.rmtree(path, ignore_errors=True)

    def project(self, name="Test", engine="sqlite"):
        root = tempfile.mkdtemp()
        self._dirs.append(root)
        return make_project_in(root, name, engine)

    def event_names(self, root):
        ctx = ProjectContext.from_directory(root)
        try:
            return sorted(e.name for e in ctx.ledger.get_event())
        finally:
            close = getattr(ctx.ledger, "close", None)
            if close:
                close()


class TestTransactionRollback(ProjectsTestCase):
    """What a ``with project:`` block which raises leaves behind (#212)."""

    def _fails(self, root, name="GW150914"):
        project = Project.load(root)
        with self.assertRaises(ValueError):
            with project:
                project.add_subject(name=name)
                raise ValueError("boom")
        return project

    def test_nothing_persisted_on_exception(self):
        for engine in ("sqlite", "yamlfile"):
            with self.subTest(engine=engine):
                root = self.project(engine=engine)
                self._fails(root)
                self.assertEqual(self.event_names(root), [])

    def test_success_is_persisted(self):
        for engine in ("sqlite", "yamlfile"):
            with self.subTest(engine=engine):
                root = self.project(engine=engine)
                project = Project.load(root)
                with project:
                    project.add_subject(name="GW150914")
                self.assertEqual(self.event_names(root), ["GW150914"])

    def test_earlier_commits_survive_a_later_failure(self):
        for engine in ("sqlite", "yamlfile"):
            with self.subTest(engine=engine):
                root = self.project(engine=engine)
                project = Project.load(root)
                with project:
                    project.add_subject(name="GW150914")
                self._fails(root, name="GW170817")
                self.assertEqual(self.event_names(root), ["GW150914"])

    def test_project_reads_stored_state_after_rollback(self):
        """The failed block's in-memory writes are not left visible."""
        for engine in ("sqlite", "yamlfile"):
            with self.subTest(engine=engine):
                root = self.project(engine=engine)
                project = self._fails(root)
                self.assertEqual(project.get_event(), [])

    def test_writes_are_visible_inside_the_block(self):
        root = self.project()
        project = Project.load(root)
        with project:
            project.add_subject(name="GW150914")
            self.assertEqual([e.name for e in project.ledger.get_event()], ["GW150914"])

    def test_writes_by_get_ledger_roll_back_too(self):
        from asimov.cli.application import get_ledger

        root = self.project()
        project = Project.load(root)
        with self.assertRaises(ValueError):
            with project:
                ledger = get_ledger()
                ledger.add_event(Event(name="GW170817", ledger=ledger))
                raise ValueError("boom")
        self.assertEqual(self.event_names(root), [])

    def test_nested_blocks_join_the_outer_transaction(self):
        root = self.project()
        project = Project.load(root)
        with self.assertRaises(ValueError):
            with project:
                project.add_subject(name="GW150914")
                with project:
                    project.add_subject(name="GW170817")
                raise ValueError("boom")
        self.assertEqual(self.event_names(root), [])

    def test_nested_blocks_commit_once_together(self):
        root = self.project()
        project = Project.load(root)
        with project:
            project.add_subject(name="GW150914")
            with project:
                project.add_subject(name="GW170817")
            # The inner block ending has not committed: that is the outer's job.
            self.assertTrue(project._in_context)
        self.assertEqual(self.event_names(root), ["GW150914", "GW170817"])

    def test_nested_projects_roll_back_independently(self):
        outer_root, inner_root = self.project("Outer"), self.project("Inner")
        outer, inner = Project.load(outer_root), Project.load(inner_root)
        with outer:
            outer.add_subject(name="GW150914")
            with self.assertRaises(ValueError):
                with inner:
                    inner.add_subject(name="GW170817")
                    raise ValueError("boom")
        self.assertEqual(self.event_names(outer_root), ["GW150914"])
        self.assertEqual(self.event_names(inner_root), [])


class TestDatabaseTransaction(ProjectsTestCase):
    """The database's transaction scope, below the ledger."""

    def setUp(self):
        super().setUp()
        self.root = tempfile.mkdtemp()
        self._dirs.append(self.root)
        self.db = AsimovSQLDatabase(
            database_url=f"sqlite:///{os.path.join(self.root, 'x.db')}"
        )
        self.addCleanup(self.db.close)

    def names(self):
        return sorted(e["name"] for e in self.db.query("event"))

    def test_commits_when_the_block_ends(self):
        with self.db.transaction():
            self.db.insert("event", {"name": "A"})
        self.assertEqual(self.names(), ["A"])

    def test_rolls_back_when_the_block_raises(self):
        with self.assertRaises(KeyError):
            with self.db.transaction():
                self.db.insert("event", {"name": "A"})
                raise KeyError
        self.assertEqual(self.names(), [])

    def test_a_write_is_seen_by_a_read_in_the_block(self):
        with self.db.transaction():
            self.db.insert("event", {"name": "A"})
            self.assertEqual(self.names(), ["A"])

    def test_without_a_block_each_write_commits_by_itself(self):
        self.db.insert("event", {"name": "A"})
        with self.assertRaises(KeyError):
            with self.db.get_session():
                raise KeyError
        self.assertEqual(self.names(), ["A"])

    def test_another_thread_does_not_join_the_transaction(self):
        """A transaction belongs to the thread which opened it."""
        seen = {}
        with self.db.transaction():
            self.db.insert("event", {"name": "A"})

            def other():
                with self.db.get_session() as session:
                    seen["shared"] = session

            worker = threading.Thread(target=other)
            worker.start()
            worker.join()
            with self.db.get_session() as mine:
                self.assertIsNot(seen["shared"], mine)


class TestProjectContext(ProjectsTestCase):
    def test_paths_are_resolved_against_the_root(self):
        root = self.project()
        ctx = ProjectContext.from_directory(root)
        self.assertEqual(ctx.root, os.path.abspath(root))
        self.assertEqual(ctx.working_dir, os.path.join(ctx.root, "working"))
        self.assertEqual(ctx.checkouts_dir, os.path.join(ctx.root, "checkouts"))
        self.assertEqual(ctx.results_dir, os.path.join(ctx.root, "results"))
        self.assertEqual(ctx.log_dir, os.path.join(ctx.root, "logs"))
        self.assertTrue(ctx.webdir.startswith(ctx.root))
        self.assertEqual(ctx.config.get("project", "root"), ctx.root)

    def test_an_absolute_path_is_left_alone(self):
        root = self.project()
        ctx = ProjectContext.from_directory(root)
        ctx.config.set("logging", "location", "/var/log/asimov")
        self.assertEqual(ctx.log_dir, "/var/log/asimov")

    def test_from_directory_needs_a_project(self):
        empty = tempfile.mkdtemp()
        self._dirs.append(empty)
        with self.assertRaises(NoProjectError):
            ProjectContext.from_directory(empty)

    def test_ledger_and_storage_belong_to_the_project(self):
        root = self.project()
        ctx = ProjectContext.from_directory(root)
        self.assertEqual(ctx.ledger.get_event(), [])
        self.assertIs(ctx.ledger, ctx.ledger)
        self.assertEqual(ctx.storage.root, ctx.results_dir)
        ctx.ledger.close()

    def test_the_ledger_is_opened_without_changing_directory(self):
        root = self.project(engine="yamlfile")
        before = os.getcwd()
        ctx = ProjectContext.from_directory(root)
        ctx.ledger.get_event()
        self.assertEqual(os.getcwd(), before)

    def test_scheduler_reads_the_project_configuration(self):
        root = self.project()
        ctx = ProjectContext.from_directory(root)
        ctx.config.set("scheduler", "type", "local")
        from asimov.scheduler import LocalProcessScheduler

        self.assertIsInstance(ctx.scheduler, LocalProcessScheduler)
        ctx.ledger.close()

    def test_activate_nests_and_restores(self):
        a = ProjectContext.from_directory(self.project("A"))
        b = ProjectContext.from_directory(self.project("B"))
        self.assertIsNone(get_active_context())
        with a.activate():
            self.assertIs(get_active_context(), a)
            with b.activate():
                self.assertIs(current_context(), b)
            self.assertIs(current_context(), a)
        self.assertIsNone(get_active_context())
        self.assertIsNot(current_context(), a)

    def test_activate_restores_when_the_block_raises(self):
        ctx = ProjectContext.from_directory(self.project())
        with self.assertRaises(ValueError):
            with ctx.activate():
                raise ValueError
        self.assertIsNone(get_active_context())

    def test_the_ambient_context_follows_the_working_directory(self):
        ambient = current_context()
        root = self.project()
        os.chdir(root)
        self.assertEqual(os.path.realpath(ambient.root), os.path.realpath(root))


class TestShims(ProjectsTestCase):
    def test_config_is_a_proxy(self):
        self.assertIsInstance(asimov.config, ConfigProxy)

    def test_config_follows_the_active_context(self):
        root = self.project("Named project")
        ctx = ProjectContext.from_directory(root)
        outside = asimov.config.get("project", "root", fallback=None)
        with ctx.activate():
            self.assertEqual(asimov.config.get("project", "name"), "Named project")
            self.assertEqual(asimov.config.get("project", "root"), ctx.root)
            self.assertTrue(asimov.config.has_section("ledger"))
            self.assertEqual(asimov.config["project"]["name"], "Named project")
        self.assertEqual(asimov.config.get("project", "root", fallback=None), outside)

    def test_current_ledger_follows_the_active_context(self):
        ctx = ProjectContext.from_directory(self.project())
        with ctx.activate():
            self.assertIs(asimov.current_ledger, ctx.ledger)
        ctx.ledger.close()

    def test_unknown_attributes_still_raise(self):
        with self.assertRaises(AttributeError):
            asimov.no_such_thing

    def test_application_get_ledger_uses_the_active_context(self):
        from asimov.cli.application import get_ledger

        ctx = ProjectContext.from_directory(self.project())
        with ctx.activate():
            self.assertIs(get_ledger(), ctx.ledger)
        ctx.ledger.close()


class TestTwoProjectsAtOnce(ProjectsTestCase):
    """The point of #180: one process serving two projects, without chdir."""

    def test_threads_each_see_their_own_project(self):
        roots = {"alpha": self.project("alpha"), "beta": self.project("beta")}
        cwd = os.getcwd()
        both_active = threading.Barrier(2)
        seen, errors = {}, []

        def serve(name):
            try:
                ctx = ProjectContext.from_directory(roots[name])
                with ctx.activate(), ctx.transaction():
                    ctx.ledger.add_event(Event(name=f"event-{name}", ledger=ctx.ledger))
                    both_active.wait(timeout=10)  # now both are mid-request
                    seen[name] = (
                        asimov.config.get("project", "name"),
                        [e.name for e in ctx.ledger.get_event()],
                    )
                ctx.ledger.close()
            except BaseException as exc:  # pragma: no cover - reported below
                errors.append(exc)
                both_active.abort()

        threads = [threading.Thread(target=serve, args=(n,)) for n in roots]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        self.assertEqual(seen["alpha"], ("alpha", ["event-alpha"]))
        self.assertEqual(seen["beta"], ("beta", ["event-beta"]))
        self.assertEqual(os.getcwd(), cwd)
        self.assertEqual(self.event_names(roots["alpha"]), ["event-alpha"])
        self.assertEqual(self.event_names(roots["beta"]), ["event-beta"])


if __name__ == "__main__":
    unittest.main()
