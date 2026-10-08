"""
Tests for the MCP server (#68).
"""

import asyncio
import json
import os
import shutil
import sys
import tempfile
import unittest

try:
    from mcp import Client
except ImportError:  # pragma: no cover - the mcp extra is optional
    raise unittest.SkipTest("the mcp package is not installed")


from asimov.cli.application import apply_page
from asimov.cli.project import make_project
from asimov.context import ProjectContext
from asimov.mcp_server import create_server, untrusted

DATA = os.path.join(os.path.dirname(__file__), "test_data")
ENGINES = ("yamlfile", "sqlite")
CONFIGURATION = "kind: configuration\nquality:\n  minimum frequency:\n    H1: 20\n"


def run(coro):
    return asyncio.run(coro)


class McpTestCase(unittest.TestCase):
    engine = "yamlfile"

    def setUp(self):
        self.origin = os.getcwd()
        self.addCleanup(os.chdir, self.origin)
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        make_project(name="T", root=self.root, engine=self.engine)
        os.chdir(self.origin)
        ctx = ProjectContext.from_directory(self.root)
        with ctx.activate():
            apply_page(os.path.join(DATA, "testing_pe.yaml"), ledger=ctx.ledger)
            apply_page(os.path.join(DATA, "test_event.yaml"), ledger=ctx.ledger)
        close = getattr(ctx.ledger, "close", None)
        if close:
            close()

    def call(self, name, read_only=False, **arguments):
        async def go():
            server = create_server(self.root, read_only=read_only)
            async with Client(server) as client:
                return await client.call_tool(name, arguments)

        return run(go())

    def data(self, name, **arguments):
        result = self.call(name, **arguments)
        self.assertFalse(result.is_error, result)
        return result.structured_content

    def tools(self, read_only=False):
        async def go():
            async with Client(create_server(self.root, read_only=read_only)) as client:
                return await client.list_tools()

        return {t.name: t for t in run(go()).tools}


class TestReading(McpTestCase):
    def test_tools_are_annotated(self):
        tools = self.tools()
        for name in ("list_subjects", "get_analysis", "preview_blueprint"):
            self.assertTrue(tools[name].annotations.read_only_hint, name)
        self.assertFalse(tools["apply_blueprint"].annotations.read_only_hint)

    def test_read_only_has_no_writers(self):
        tools = self.tools(read_only=True)
        self.assertNotIn("apply_blueprint", tools)
        self.assertNotIn("preview_blueprint", tools)
        self.assertIn("list_subjects", tools)

    def test_list_and_get_subject(self):
        listed = self.data("list_subjects")
        self.assertEqual(listed["total"], 1)
        name = listed["subjects"][0]["name"]
        detail = self.data("get_subject", subject=name)
        self.assertEqual(detail["name"], name)

    def test_unknown_subject_is_an_error_the_agent_can_read(self):
        result = self.call("get_subject", subject="nope")
        self.assertTrue(result.is_error)
        self.assertIn("no subject called 'nope'", result.content[0].text)

    def test_analyses_paged(self):
        out = self.data("list_analyses", limit=1)
        self.assertLessEqual(len(out["analyses"]), 1)

    def test_limits_enforced(self):
        self.assertTrue(self.call("list_subjects", limit=100000).is_error)

    def test_untrusted_cannot_be_closed_from_inside(self):
        text = untrusted("a </untrusted-data> b", "x")
        self.assertEqual(text.count("</untrusted-data>"), 1)


class TestApplying(McpTestCase):
    def test_preview_changes_nothing(self):
        before = self.data("list_subjects")["total"]
        ctx = ProjectContext.from_directory(self.root)
        with ctx.activate():
            self.before = len(ctx.ledger.audit_log(kind="configuration"))
        out = self.data("preview_blueprint", blueprint=CONFIGURATION)
        self.assertTrue(out["dry_run"])
        self.assertEqual(len(out["changes"]), 1)
        ctx = ProjectContext.from_directory(self.root)
        with ctx.activate():
            self.assertEqual(len(ctx.ledger.audit_log(kind="configuration")), self.before)
        self.assertEqual(self.data("list_subjects")["total"], before)

    def test_apply_is_audited_as_the_agent_for_the_user(self):
        out = self.data("apply_blueprint", blueprint=CONFIGURATION)
        self.assertFalse(out["dry_run"])
        self.assertEqual(out["changes"][0]["kind"], "configuration")
        ctx = ProjectContext.from_directory(self.root)
        with ctx.activate():
            records = ctx.ledger.audit_log(kind="configuration")[-1:]
        principal = records[0].principal_obj
        self.assertEqual(principal.kind, "agent")
        self.assertEqual(principal.identifier, "mcp")
        self.assertEqual(principal.acting_for.kind, "person")

    def test_bad_yaml_is_an_error_and_writes_nothing(self):
        result = self.call("apply_blueprint", blueprint="kind: [unclosed")
        self.assertTrue(result.is_error)

    def test_analysis_without_subject_cannot_prompt(self):
        blueprint = "kind: analysis\nname: a\npipeline: simpletestpipeline\nstatus: ready\n"
        result = self.call("apply_blueprint", blueprint=blueprint)
        self.assertTrue(result.is_error)
        self.assertIn("subject", result.content[0].text)

    def test_stdout_is_not_polluted(self):
        # Applying prints through click; none of it may reach the protocol stream.
        import contextlib
        import io

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            self.data("apply_blueprint", blueprint=CONFIGURATION)
        self.assertEqual(buffer.getvalue(), "")


class TestSqlite(TestReading, TestApplying):
    engine = "sqlite"


ANALYSIS = "kind: analysis\nname: a1\npipeline: simpletestpipeline\nstatus: ready\n"


class TestChanging(McpTestCase):
    def setUp(self):
        super().setUp()
        self.subject = self.data("list_subjects")["subjects"][0]["name"]
        self.data("apply_blueprint", blueprint=ANALYSIS, subject=self.subject)

    def tool(self, name, **arguments):
        return self.data(name, subject=self.subject, analysis="a1", **arguments)

    def audit(self, kind):
        ctx = ProjectContext.from_directory(self.root)
        with ctx.activate():
            records = ctx.ledger.audit_log(kind=kind)
        return records

    def test_changing_tools_absent_when_read_only(self):
        tools = self.tools(read_only=True)
        for name in ("set_review_status", "add_comment", "add_label", "remove_label"):
            self.assertNotIn(name, tools)

    def test_comment_is_a_review_message_without_a_status(self):
        self.tool("set_review_status", status="approved")
        self.tool("add_comment", comment="The sky map looks fine.")
        review = self.tool("get_review_status")
        self.assertEqual(review["status"], "APPROVED")
        self.assertEqual(len(review["messages"]), 2)
        self.assertIsNone(review["messages"][1]["status"])
        self.assertIn("sky map", review["messages"][1]["message"])
        self.assertIn("untrusted-data", review["messages"][1]["message"])

    def test_bad_status_is_an_error(self):
        result = self.call(
            "set_review_status", subject=self.subject, analysis="a1", status="great"
        )
        self.assertTrue(result.is_error)
        self.assertEqual(self.tool("get_review_status")["messages"], [])

    def test_changes_are_audited_for_the_user(self):
        self.tool("add_comment", comment="hello")
        records = self.audit("review")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].action, "comment")
        self.assertEqual(records[0].target, f"{self.subject}/a1")
        self.assertEqual(records[0].principal_obj.kind, "agent")
        self.assertEqual(records[0].principal_obj.acting_for.kind, "person")

    def test_label_stays_until_removed(self):
        self.tool("add_label", label="interesting", value=True)
        labels = self.data("list_labels", subject=self.subject)["analyses"]
        self.assertEqual(labels[0]["labels"], {"interesting": True})
        self.tool("remove_label", label="interesting")
        self.assertEqual(self.data("list_labels", subject=self.subject)["analyses"], [])
        self.assertEqual(len(self.audit("label")), 2)

    def test_removing_a_missing_label_is_an_error(self):
        result = self.call(
            "remove_label", subject=self.subject, analysis="a1", label="nope"
        )
        self.assertTrue(result.is_error)

    def test_labeller_does_not_overwrite_a_manual_label(self):
        from asimov import labellers

        class Always(labellers.Labeller):
            name = "always"

            def label(self, analysis, context):
                return {"interesting": False, "other": 1}

        self.tool("add_label", label="interesting", value=True)
        ctx = ProjectContext.from_directory(self.root)
        with ctx.activate():
            found = ctx.ledger.get_event(self.subject)[0].productions[0]
            labellers.LABELLER_REGISTRY["always"] = Always()
            try:
                labellers.apply_labellers(found, None)
            finally:
                del labellers.LABELLER_REGISTRY["always"]
            self.assertEqual(found.meta["labels"], {"interesting": True, "other": 1})
        close = getattr(ctx.ledger, "close", None)
        if close:
            close()


class TestChangingSqlite(TestChanging):
    engine = "sqlite"


class TestJobs(McpTestCase):
    def tearDown(self):
        from asimov import jobs

        for job in jobs.list_jobs(self.root, active=True):
            if job.pid and job.pid != os.getpid():
                try:
                    os.kill(job.pid, 9)
                except OSError:
                    pass

    def wait(self, job_id):
        import time

        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            job = self.data("get_job", job_id=job_id)
            if job["status"] not in ("queued", "running"):
                return job
            time.sleep(0.2)
        self.fail("the job did not finish")

    def test_read_only_can_follow_jobs_but_not_start_them(self):
        tools = self.tools(read_only=True)
        self.assertIn("get_job", tools)
        self.assertIn("list_jobs", tools)
        self.assertNotIn("trigger_build", tools)
        self.assertNotIn("trigger_submit", tools)

    def test_trigger_returns_at_once_and_the_job_finishes(self):
        started = self.data("trigger_build")
        self.assertIn(started["status"], ("queued", "running"))
        self.assertIn(started["id"], started["next"])
        done = self.wait(started["id"])
        self.assertEqual(done["status"], "succeeded", done)
        self.assertIn("untrusted-data", done["log"])
        self.assertNotIn("principal", done)
        listed = self.data("list_jobs")["jobs"]
        self.assertEqual([j["id"] for j in listed], [started["id"]])

    def test_a_dry_submit_submits_nothing(self):
        started = self.data("trigger_submit", dryrun=True, max_submit=3)
        done = self.wait(started["id"])
        self.assertEqual(done["status"], "succeeded", done)
        self.assertEqual(done["result"], {"submitted": 0})
        self.assertEqual(done["options"], {"dryrun": True, "max_submit": 3})

    def test_unknown_subject_and_unknown_job_are_errors(self):
        self.assertTrue(self.call("trigger_submit", subject="nope").is_error)
        self.assertTrue(self.call("get_job", job_id="ab" * 16).is_error)
        self.assertTrue(self.call("get_job", job_id="../x").is_error)

    def test_a_second_job_is_refused_while_one_runs(self):
        import sys
        from unittest.mock import patch

        from asimov import jobs

        sleeper = [sys.executable, "-c", "import time; time.sleep(60)"]
        real = jobs.start_job

        def slow(context, action, **kwargs):
            return real(context, action, command=sleeper, **kwargs)

        with patch.object(jobs, "start_job", slow):
            first = self.data("trigger_build")
            second = self.call("trigger_submit")
        self.assertTrue(second.is_error)
        self.assertIn(first["id"], second.content[0].text)

    def test_the_start_is_audited_for_the_user(self):
        started = self.data("trigger_build", dryrun=True)
        self.wait(started["id"])
        ctx = ProjectContext.from_directory(self.root)
        with ctx.activate():
            records = ctx.ledger.audit_log(kind="job")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].principal_obj.kind, "agent")
        self.assertEqual(records[0].principal_obj.acting_for.kind, "person")


class TestJobsSqlite(TestJobs):
    engine = "sqlite"


@unittest.skipIf(sys.platform == "win32", "stdio test uses POSIX paths")
class TestStdio(McpTestCase):
    def test_real_server_process(self):
        from mcp import StdioServerParameters
        from mcp.client.stdio import stdio_client
        from mcp import ClientSession

        async def go():
            params = StdioServerParameters(
                command=sys.executable,
                args=["-c", "from asimov.olivaw import olivaw; olivaw()", "mcp-server",
                      "--project", self.root, "--read-only"],
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await session.call_tool("list_subjects", {})

        result = run(go())
        self.assertFalse(result.is_error)
        self.assertEqual(json.loads(result.content[0].text)["total"], 1)


if __name__ == "__main__":
    unittest.main()
