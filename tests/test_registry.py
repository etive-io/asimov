"""
Tests for the project registry and access hook (#184).
"""

import json
import os
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch

import yaml
from click.testing import CliRunner

from asimov import access, throttle
from asimov.cli import registry as registry_cli
from asimov.cli.application import apply_page
from asimov.cli.project import make_project
from asimov.principal import Principal
from asimov.registry import (
    AmbiguousProject,
    FileRegistry,
    ProjectEntry,
    ProjectExists,
    ReadOnlyRegistry,
    RegistryError,
    SingleProjectRegistry,
    UnknownProject,
    default_registry_path,
    mask_secrets,
)

DATA = os.path.join(os.path.dirname(__file__), "test_data")


class RegistryTestCase(unittest.TestCase):
    def setUp(self):
        self.origin = os.getcwd()
        self.addCleanup(os.chdir, self.origin)
        self.dirs = []
        self.scratch = self.make_dir()
        self.path = os.path.join(self.scratch, "registry.yaml")

    def make_dir(self):
        path = tempfile.mkdtemp()
        self.dirs.append(path)
        self.addCleanup(shutil.rmtree, path, True)
        return path

    def make_project(self, name="T", engine="yamlfile"):
        root = self.make_dir()
        make_project(name=name, root=root, engine=engine)
        os.chdir(self.origin)
        return root


class TestEntry(unittest.TestCase):
    def test_names(self):
        for good in ("gw-o4", "a", "o4.a_1", "0day"):
            ProjectEntry(name=good, root="/x")
        for bad in ("", "GW", "-a", "a b", "a/b", "../x", "x" * 65, ".hidden"):
            with self.assertRaises(RegistryError, msg=bad):
                ProjectEntry(name=bad, root="/x")

    def test_other_fields_are_checked(self):
        with self.assertRaises(RegistryError):
            ProjectEntry(name="a", root="/x", groups="cbc")
        with self.assertRaises(RegistryError):
            ProjectEntry(name="a", root="/x", ledger={"url": "x"})
        with self.assertRaises(RegistryError):
            ProjectEntry(name="a", root="/x", quotas={"max_queued": "many"})
        with self.assertRaises(RegistryError):
            ProjectEntry(name="a", root="/x", quotas={"max_queued": -1})
        with self.assertRaises(RegistryError):
            ProjectEntry(name="a", root="")

    def test_round_trip(self):
        entry = ProjectEntry(
            name="a",
            root="/x",
            groups=["g1"],
            ledger={"engine": "sqlite", "location": "sqlite:///l.db"},
            storage="/s",
            scheduler="slurm",
            quotas={"max_queued": 3, "other": "kept"},
        )
        again = ProjectEntry.from_dict("a", entry.to_dict())
        self.assertEqual(again, entry)

    def test_unknown_keys_are_refused(self):
        with self.assertRaises(RegistryError):
            ProjectEntry.from_dict("a", {"root": "/x", "colour": "red"})

    def test_passwords_are_masked_for_showing(self):
        entry = ProjectEntry(
            name="a",
            root="/x",
            ledger={"engine": "postgresql", "location": "postgresql://asimov:hunter2@db/asimov"},
        )
        shown = json.dumps(entry.to_dict(mask=True))
        self.assertNotIn("hunter2", shown)
        self.assertIn("asimov:***@db", shown)
        self.assertIn("hunter2", json.dumps(entry.to_dict()))
        self.assertEqual(mask_secrets("no secret here"), "no secret here")
        self.assertEqual(mask_secrets(["a://u:p@h"]), ["a://u:***@h"])


class TestFileRegistry(RegistryTestCase):
    def test_empty_when_there_is_no_file(self):
        self.assertEqual(FileRegistry(self.path).list(), [])

    def test_add_list_get_remove(self):
        registry = FileRegistry(self.path)
        registry.add(ProjectEntry(name="b", root="/b", groups=["g"]))
        registry.add(ProjectEntry(name="a", root="/a"))
        self.assertEqual(registry.names(), ["a", "b"])
        self.assertEqual(registry.get("b").groups, ["g"])
        registry.remove("a")
        self.assertEqual(registry.names(), ["b"])

    def test_duplicates_and_unknowns(self):
        registry = FileRegistry(self.path)
        registry.add(ProjectEntry(name="a", root="/a"))
        with self.assertRaises(ProjectExists):
            registry.add(ProjectEntry(name="a", root="/other"))
        with self.assertRaises(UnknownProject) as raised:
            registry.get("nope")
        self.assertEqual(raised.exception.known, ["a"])
        self.assertIn("a", str(raised.exception))
        with self.assertRaises(UnknownProject):
            registry.remove("nope")

    def test_a_project_may_be_left_unnamed_only_when_alone(self):
        registry = FileRegistry(self.path)
        with self.assertRaises(AmbiguousProject):
            registry.get()
        registry.add(ProjectEntry(name="a", root="/a"))
        self.assertEqual(registry.get().name, "a")
        registry.add(ProjectEntry(name="b", root="/b"))
        with self.assertRaises(AmbiguousProject) as raised:
            registry.get()
        self.assertIn("a, b", str(raised.exception))

    def test_relative_roots_are_relative_to_the_file(self):
        with open(self.path, "w") as handle:
            yaml.safe_dump({"projects": {"a": {"root": "proj/a"}}}, handle)
        self.assertEqual(FileRegistry(self.path).get("a").root, os.path.join(self.scratch, "proj/a"))

    def test_bad_files_are_errors_not_crashes(self):
        for text in ("projects: [1, 2]", "[1, 2]", "projects: {a: 3}", "a: [unclosed"):
            with open(self.path, "w") as handle:
                handle.write(text)
            with self.assertRaises(RegistryError, msg=text):
                FileRegistry(self.path).list()

    def test_changes_by_another_registry_object_are_seen(self):
        one, two = FileRegistry(self.path), FileRegistry(self.path)
        one.add(ProjectEntry(name="a", root="/a"))
        self.assertEqual(two.names(), ["a"])

    def test_adds_made_at_once_all_happen(self):
        def add(name):
            FileRegistry(self.path).add(ProjectEntry(name=name, root="/" + name))

        threads = [threading.Thread(target=add, args=(f"p{i}",)) for i in range(12)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(FileRegistry(self.path).names()), 12)

    def test_default_path(self):
        with patch.dict(os.environ, {"ASIMOV_REGISTRY": "/etc/r.yaml"}):
            self.assertEqual(default_registry_path(), "/etc/r.yaml")
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": "/cfg"}, clear=False):
            os.environ.pop("ASIMOV_REGISTRY", None)
            self.assertEqual(default_registry_path(), "/cfg/asimov/registry.yaml")


class TestSingleProjectRegistry(RegistryTestCase):
    def test_one_project_named_from_its_configuration(self):
        root = self.make_project(name="My Project")
        registry = SingleProjectRegistry(root)
        self.assertEqual(registry.names(), ["my-project"])
        self.assertEqual(registry.get().root, os.path.abspath(root))
        self.assertEqual(registry.get("my-project").name, "my-project")

    def test_it_can_be_given_a_name_and_cannot_be_changed(self):
        registry = SingleProjectRegistry(self.make_project(), name="x")
        self.assertEqual(registry.names(), ["x"])
        with self.assertRaises(ReadOnlyRegistry):
            registry.add(ProjectEntry(name="y", root="/y"))
        with self.assertRaises(ReadOnlyRegistry):
            registry.remove("x")
        with self.assertRaises(UnknownProject):
            registry.get("y")


class TestResolve(RegistryTestCase):
    engines = ("yamlfile", "sqlite")

    def test_projects_have_their_own_ledgers(self):
        for engine in self.engines:
            with self.subTest(engine=engine):
                one = self.make_project("one", engine)
                two = self.make_project("two", engine)
                registry = FileRegistry(os.path.join(self.make_dir(), "r.yaml"))
                registry.add(ProjectEntry(name="one", root=one))
                registry.add(ProjectEntry(name="two", root=two))

                first = registry.resolve("one")
                self.addCleanup(first.reload_ledger)
                with first.activate():
                    apply_page(os.path.join(DATA, "testing_pe.yaml"), ledger=first.ledger)
                    apply_page(os.path.join(DATA, "test_event.yaml"), ledger=first.ledger)
                second = registry.resolve("two")
                self.addCleanup(second.reload_ledger)
                with second.activate():
                    self.assertEqual(second.ledger.get_event(), [])
                with first.activate():
                    self.assertEqual(len(first.ledger.get_event()), 1)

    def test_each_resolve_is_a_new_context(self):
        registry = SingleProjectRegistry(self.make_project())
        self.assertIsNot(registry.resolve(), registry.resolve())

    def test_a_directory_which_is_not_a_project_is_an_error(self):
        from asimov.context import NoProjectError

        registry = FileRegistry(self.path)
        registry.add(ProjectEntry(name="a", root=self.make_dir()))
        with self.assertRaises(NoProjectError):
            registry.resolve("a")

    def test_the_ledger_can_be_somewhere_else(self):
        root = self.make_project("p", "sqlite")
        elsewhere = os.path.join(self.make_dir(), "other.db")
        entry = ProjectEntry(
            name="p", root=root, ledger={"engine": "sqlite", "location": f"sqlite:///{elsewhere}"}
        )
        context = entry.context()
        self.addCleanup(context.reload_ledger)
        with context.activate():
            context.ledger.get_event()
        self.assertTrue(os.path.exists(elsewhere))

    def test_ledger_location_may_use_environment_variables(self):
        root = self.make_project("p", "sqlite")
        elsewhere = os.path.join(self.make_dir(), "env.db")
        entry = ProjectEntry(
            name="p", root=root, ledger={"location": "sqlite:///$ASIMOV_TEST_DB"}
        )
        with patch.dict(os.environ, {"ASIMOV_TEST_DB": elsewhere}):
            context = entry.context()
        self.addCleanup(context.reload_ledger)
        with context.activate():
            context.ledger.get_event()
        self.assertTrue(os.path.exists(elsewhere))

    def test_storage_scheduler_and_quotas_are_applied(self):
        root = self.make_project()
        entry = ProjectEntry(
            name="p",
            root=root,
            storage="/results/p",
            scheduler="local",
            quotas={"max_queued": 7, "max_submit_per_pass": 2, "unrelated": 1},
        )
        context = entry.context()
        self.assertEqual(context.results_dir, "/results/p")
        self.assertEqual(context.config.get("scheduler", "type"), "local")
        self.assertEqual(context.config.get("scheduler", "max_queued"), "7")
        self.assertFalse(context.config.has_option("scheduler", "unrelated"))
        # the limits the throttle reads
        with context.activate():
            self.assertEqual(throttle.per_pass_limit(), 2)
        with SingleProjectRegistry(root).resolve().activate():
            self.assertIsNone(throttle.per_pass_limit())

    def test_one_projects_quotas_dont_leak_into_another(self):
        a = ProjectEntry(name="a", root=self.make_project(), quotas={"max_submit_per_pass": 1})
        b = ProjectEntry(name="b", root=self.make_project())
        ca, cb = a.context(), b.context()
        with ca.activate():
            self.assertEqual(throttle.per_pass_limit(), 1)
            with cb.activate():
                self.assertIsNone(throttle.per_pass_limit())
            self.assertEqual(throttle.per_pass_limit(), 1)


class TestAccess(unittest.TestCase):
    def setUp(self):
        self.entry = ProjectEntry(name="p", root="/p", groups=["g"])
        self.principal = Principal.person("dw")

    def test_everything_is_allowed_to_start_with(self):
        self.assertIsInstance(access.get_policy(), access.AllowAll)
        for action in access.ACTIONS:
            access.authorize(self.principal, self.entry, action)

    def test_a_policy_can_refuse(self):
        class ReadOnly(access.Policy):
            def allows(self, principal, entry, action):
                return action == access.READ

        previous = access.set_policy(ReadOnly())
        self.addCleanup(access.set_policy, previous)
        access.authorize(self.principal, self.entry, access.READ)
        with self.assertRaises(access.AccessDenied) as raised:
            access.authorize(self.principal, self.entry, access.WRITE)
        self.assertEqual(str(raised.exception), "dw may not write the project 'p'.")
        self.assertIsInstance(raised.exception, PermissionError)

    def test_unknown_actions_are_errors(self):
        with self.assertRaises(ValueError):
            access.authorize(self.principal, self.entry, "delete")

    def test_the_policy_is_given_what_it_needs(self):
        seen = []

        class Spy(access.Policy):
            def allows(self, principal, entry, action):
                seen.append((principal.identifier, entry.groups, action))
                return True

        previous = access.set_policy(Spy())
        self.addCleanup(access.set_policy, previous)
        access.authorize(self.principal, self.entry, access.EXECUTE)
        self.assertEqual(seen, [("dw", ["g"], "execute")])


class TestCli(RegistryTestCase):
    def run_cli(self, *args):
        return CliRunner().invoke(registry_cli.registry, ["--registry", self.path, *args])

    def test_add_list_show_remove(self):
        root = self.make_project()
        result = self.run_cli(
            "add", "gw-o4", root, "-g", "cbc", "-g", "burst", "--quota", "max_queued=10",
            "--scheduler", "htcondor",
        )
        self.assertEqual(result.exit_code, 0, result.output)
        entry = FileRegistry(self.path).get("gw-o4")
        self.assertEqual(entry.groups, ["cbc", "burst"])
        self.assertEqual(entry.quotas, {"max_queued": 10})
        self.assertIn("gw-o4", self.run_cli("list").output)
        shown = json.loads(self.run_cli("show", "gw-o4").output)
        self.assertEqual(shown["gw-o4"]["scheduler"], "htcondor")
        listed = json.loads(self.run_cli("list", "--format", "json").output)
        self.assertEqual(list(listed), ["gw-o4"])
        self.assertEqual(self.run_cli("remove", "gw-o4").exit_code, 0)
        self.assertIn("No projects", self.run_cli("list").output)

    def test_passwords_are_not_shown(self):
        root = self.make_project()
        self.run_cli(
            "add", "p", root, "--ledger-engine", "postgresql",
            "--ledger-location", "postgresql://u:hunter2@db/x",
        )
        for args in (("show", "p"), ("list", "--format", "json")):
            self.assertNotIn("hunter2", self.run_cli(*args).output)
        self.assertIn("hunter2", open(self.path).read())

    def test_errors_are_messages(self):
        root = self.make_project()
        self.run_cli("add", "p", root)
        for args, text in (
            (("add", "p", root), "already a project"),
            (("add", "BAD NAME", root), "not a project name"),
            (("show", "nope"), "no project called 'nope'"),
            (("remove", "nope"), "no project called 'nope'"),
            (("add", "q", root, "--quota", "max_queued"), "NAME=VALUE"),
            (("add", "q", root, "--quota", "max_queued=lots"), "must be a number"),
        ):
            result = self.run_cli(*args)
            self.assertNotEqual(result.exit_code, 0, args)
            self.assertIn(text, result.output, args)
            self.assertNotIn("Traceback", result.output)

    def test_it_works_outside_a_project(self):
        from asimov.olivaw import olivaw

        os.chdir(self.make_dir())
        result = CliRunner().invoke(olivaw, ["registry", "--registry", self.path, "list"])
        self.assertEqual(result.exit_code, 0, result.output)


if __name__ == "__main__":
    unittest.main()
