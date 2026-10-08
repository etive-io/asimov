"""
Tests for the MCP server serving several projects (#184).
"""

import asyncio
import os
import shutil
import tempfile
import unittest

try:
    from mcp import Client
except ImportError:  # pragma: no cover - the mcp extra is optional
    raise unittest.SkipTest("the mcp package is not installed")

from asimov import access, jobs
from asimov.cli.application import apply_page
from asimov.cli.project import make_project
from asimov.context import ProjectContext
from asimov.mcp_server import create_server
from asimov.registry import FileRegistry, ProjectEntry

DATA = os.path.join(os.path.dirname(__file__), "test_data")
ANALYSIS = "kind: analysis\nname: a1\npipeline: simpletestpipeline\nstatus: ready\n"
CONFIGURATION = "kind: configuration\nquality:\n  minimum frequency:\n    H1: 20\n"


class McpProjectsTestCase(unittest.TestCase):
    engine = "yamlfile"
    seed = ("one", "two")

    def setUp(self):
        self.origin = os.getcwd()
        self.addCleanup(os.chdir, self.origin)
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.registry = FileRegistry(os.path.join(self.dir, "registry.yaml"))
        self.roots = {}
        for name in self.seed:
            root = os.path.join(self.dir, name)
            make_project(name=name, root=root, engine=self.engine)
            os.chdir(self.origin)
            self.roots[name] = root
            self.registry.add(ProjectEntry(name=name, root=root, groups=[f"{name}-group"]))
        # the first project has a subject
        first = self.roots[self.seed[0]]
        context = ProjectContext.from_directory(first)
        with context.activate():
            apply_page(os.path.join(DATA, "testing_pe.yaml"), ledger=context.ledger)
            apply_page(os.path.join(DATA, "test_event.yaml"), ledger=context.ledger)
        context.reload_ledger()

    def set_policy(self, policy):
        previous = access.set_policy(policy)
        self.addCleanup(access.set_policy, previous)

    def call(self, name, source=None, read_only=False, **arguments):
        async def go():
            server = create_server(source or self.registry, read_only=read_only)
            async with Client(server) as client:
                return await client.call_tool(name, arguments)

        return asyncio.run(go())

    def data(self, name, **arguments):
        result = self.call(name, **arguments)
        self.assertFalse(result.is_error, result)
        return result.structured_content

    def tools(self, source=None, read_only=False):
        async def go():
            async with Client(create_server(source or self.registry, read_only=read_only)) as client:
                return await client.list_tools()

        return {t.name: t for t in asyncio.run(go()).tools}

    def error(self, name, **arguments):
        result = self.call(name, **arguments)
        self.assertTrue(result.is_error, result)
        return result.content[0].text

    def subject(self):
        return self.data("list_subjects", project="one")["subjects"][0]["name"]


class TestSeveralProjects(McpProjectsTestCase):
    def test_every_tool_takes_an_optional_project(self):
        for name, tool in self.tools().items():
            if name == "list_projects":
                continue
            schema = tool.input_schema if hasattr(tool, "input_schema") else tool.inputSchema
            self.assertIn("project", schema["properties"], name)
            self.assertNotIn("project", schema.get("required", []), name)

    def test_the_project_has_to_be_named_when_there_are_several(self):
        message = self.error("list_subjects")
        self.assertIn("Say which project", message)
        self.assertIn("one, two", message)

    def test_projects_are_separate(self):
        self.assertEqual(self.data("list_subjects", project="one")["total"], 1)
        self.assertEqual(self.data("list_subjects", project="two")["total"], 0)

    def test_changes_go_to_the_project_named_and_are_audited_there(self):
        self.data("apply_blueprint", project="two", blueprint=CONFIGURATION)
        counts = {}
        for name in ("one", "two"):
            context = ProjectContext.from_directory(self.roots[name])
            with context.activate():
                counts[name] = len(context.ledger.audit_log(principal="mcp"))
            context.reload_ledger()
        self.assertEqual(counts["one"], 0)
        self.assertEqual(counts["two"], 1)

    def test_an_unknown_project_is_an_error_which_says_which_there_are(self):
        message = self.error("list_subjects", project="nope")
        self.assertIn("no project called 'nope'", message)
        self.assertIn("one, two", message)
        self.assertTrue(self.call("list_subjects", project="ONE").is_error)

    def test_list_projects(self):
        listed = self.data("list_projects")["projects"]
        self.assertEqual(listed, [
            {"name": "one", "groups": ["one-group"]},
            {"name": "two", "groups": ["two-group"]},
        ])
        self.assertNotIn(self.dir, str(listed))

    def test_jobs_belong_to_their_project(self):
        started = self.data("trigger_build", project="two", dryrun=True)
        deadline_jobs = jobs.list_jobs(self.roots["two"])
        self.assertEqual([j.id for j in deadline_jobs], [started["id"]])
        self.assertEqual(jobs.list_jobs(self.roots["one"]), [])
        self.assertIn("no job", self.error("get_job", project="one", job_id=started["id"]))
        self.assertEqual(self.data("get_job", project="two", job_id=started["id"])["id"], started["id"])
        self.assertEqual(len(self.data("list_jobs", project="one")["jobs"]), 0)
        # wait for the worker so it doesn't outlive the test
        import time
        for _ in range(300):
            if not jobs.get_job(self.roots["two"], started["id"]).active:
                break
            time.sleep(0.1)

    def test_reading_one_project_does_not_wait_for_another(self):
        # a call holds its project's lock only
        import threading

        order = []
        real = ProjectEntry.context
        gate = threading.Event()

        def slow(entry):
            if entry.name == "one":
                order.append("one waiting")
                gate.wait(5)
            return real(entry)

        from unittest.mock import patch

        async def go():
            server = create_server(self.registry)
            async with Client(server) as client:
                first = asyncio.ensure_future(client.call_tool("list_subjects", {"project": "one"}))
                await asyncio.sleep(0.3)
                second = await client.call_tool("list_subjects", {"project": "two"})
                order.append("two done")
                gate.set()
                await first
                return second

        with patch.object(ProjectEntry, "context", slow):
            result = asyncio.run(go())
        self.assertFalse(result.is_error)
        self.assertEqual(order, ["one waiting", "two done"])


class TestAccessThroughMcp(McpProjectsTestCase):
    def test_a_project_which_may_not_be_read_looks_like_one_which_does_not_exist(self):
        class OnlyTwo(access.Policy):
            def allows(self, principal, entry, action):
                return entry.name == "two"

        self.set_policy(OnlyTwo())
        denied = self.error("list_subjects", project="one")
        missing = self.error("list_subjects", project="nope")
        self.assertEqual(denied.replace("'one'", "X"), missing.replace("'nope'", "X"))
        self.assertNotIn("one", denied.split("The projects are:")[1])
        self.assertEqual(self.data("list_subjects", project="two")["total"], 0)
        self.assertEqual([p["name"] for p in self.data("list_projects")["projects"]], ["two"])

    def test_the_actions_asked_for_are_read_write_and_execute(self):
        seen = []

        class Spy(access.Policy):
            def allows(self, principal, entry, action):
                seen.append((principal.kind, principal.on_behalf_of.kind, entry.name, action))
                return True

        self.set_policy(Spy())
        subject = self.subject()
        seen.clear()
        self.data("list_subjects", project="one")
        self.data("preview_blueprint", project="one", blueprint=CONFIGURATION)
        self.data("apply_blueprint", project="one", blueprint=ANALYSIS, subject=subject)
        self.data("add_comment", project="one", subject=subject, analysis="a1", comment="hi")
        started = self.data("trigger_build", project="one", dryrun=True)
        actions_seen = [a for _, _, _, a in seen if a != "read"]
        self.assertEqual(actions_seen, ["write", "write", "execute"])
        self.assertEqual(seen[0][:2], ("agent", "person"))
        import time
        for _ in range(300):
            if not jobs.get_job(self.roots["one"], started["id"]).active:
                break
            time.sleep(0.1)

    def test_read_without_write_cannot_change_anything(self):
        class ReadOnly(access.Policy):
            def allows(self, principal, entry, action):
                return action == access.READ

        self.set_policy(ReadOnly())
        subject = self.subject()
        self.assertEqual(self.data("list_subjects", project="one")["total"], 1)
        for name, arguments in (
            ("apply_blueprint", {"blueprint": CONFIGURATION}),
            ("trigger_submit", {"dryrun": True}),
            ("add_comment", {"subject": subject, "analysis": "a1", "comment": "x"}),
        ):
            message = self.error(name, project="one", **arguments)
            self.assertIn("may not", message, name)
        # previewing is reading
        self.assertTrue(self.data("preview_blueprint", project="one", blueprint=CONFIGURATION)["dry_run"])


class TestOneProject(McpProjectsTestCase):
    seed = ("only",)

    def test_the_project_may_be_left_out(self):
        self.assertEqual(self.data("list_subjects")["total"], 1)
        self.assertEqual(self.data("list_subjects", project="only")["total"], 1)

    def test_a_directory_works_as_before_and_is_named_from_its_configuration(self):
        root = self.roots["only"]
        self.assertEqual(self.data("list_subjects", source=root)["total"], 1)
        listed = self.data("list_projects", source=root)["projects"]
        self.assertEqual([p["name"] for p in listed], ["only"])
        self.assertEqual(self.data("list_subjects", source=root, project="only")["total"], 1)

    def test_a_directory_which_is_not_a_project_is_refused_at_once(self):
        from asimov.context import NoProjectError

        with self.assertRaises(NoProjectError):
            create_server(self.dir)

    def test_an_unopenable_project_is_reported_not_crashed(self):
        self.registry.add(ProjectEntry(name="broken", root=os.path.join(self.dir, "nothing-here")))
        message = self.error("list_subjects", project="broken")
        self.assertIn("could not be opened", message)


class TestSqlite(TestSeveralProjects, TestAccessThroughMcp):
    engine = "sqlite"


if __name__ == "__main__":
    unittest.main()
