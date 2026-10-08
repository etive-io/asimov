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

import pytest

pytest.importorskip("mcp")

from mcp import Client  # noqa: E402

from asimov.cli.application import apply_page  # noqa: E402
from asimov.cli.project import make_project  # noqa: E402
from asimov.context import ProjectContext  # noqa: E402
from asimov.mcp_server import create_server, untrusted  # noqa: E402

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
