"""
The per-subject report shows what an analysis needs in other subjects (#231):
a dashed node for each, with an edge to the analysis which needs it. They are
not part of the subject, so they are not counted, and they are only drawn for
what needs them.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

from asimov.cli.application import apply_page
from asimov.cli.project import make_project
from asimov.event import Event
from asimov.ledger import YAMLLedger

NODE = shutil.which("node")


def event(name):
    return f"kind: event\nname: {name}\ninterferometers: [H1]\n"


def analysis(name, needs=(), status="ready"):
    text = f"kind: analysis\nname: {name}\npipeline: simpletestpipeline\nstatus: {status}\n"
    if needs:
        text += "needs:\n" + "".join(f"  - {need}\n" for need in needs)
    return text


class ReportCase(unittest.TestCase):
    def setUp(self):
        self.cwd = os.getcwd()
        self.root = tempfile.mkdtemp()
        os.chdir(self.root)
        make_project(name="Test project", root=self.root, engine="yamlfile")
        self.ledger = YAMLLedger(".asimov/ledger.yml")
        for name in ("EvA", "EvB", "EvC"):
            self.apply(event(name))

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.root, ignore_errors=True)

    def apply(self, *documents, subject=None):
        with open("blueprint.yaml", "w") as handle:
            handle.write("---\n".join(documents))
        apply_page("blueprint.yaml", event=subject, ledger=self.ledger)

    def graph(self, subject):
        """The nodes and edges which the report gives the graph of a subject."""
        fresh = YAMLLedger(".asimov/ledger.yml")
        text = fresh.get_event(subject)[0].html()
        match = re.search(r"nodes: (\[.*?\]),\n  edges: (\[.*?\])\n}", text, re.S)
        self.assertIsNotNone(match, "no graph in the report")
        return json.loads(match.group(1)), json.loads(match.group(2))


class ForeignNodeTests(ReportCase):
    def test_what_a_subject_needs_elsewhere_is_a_node(self):
        self.apply(analysis("fit", status="finished"), subject="EvB")
        self.apply(analysis("combine", ["EvB/fit"]), subject="EvA")
        nodes, edges = self.graph("EvA")
        foreign = [n for n in nodes if n.get("foreign")]
        self.assertEqual(len(foreign), 1)
        self.assertIn("EvB/fit", foreign[0]["label"])
        self.assertEqual(foreign[0]["status"], "finished")
        self.assertEqual(foreign[0]["dataId"], "")
        combine = next(n for n in nodes if not n.get("foreign"))
        self.assertEqual(edges, [{"from": foreign[0]["id"], "to": combine["id"]}])

    def test_an_analysis_in_the_same_subject_is_not_one(self):
        self.apply(analysis("a"), analysis("b", ["a"]), subject="EvA")
        nodes, edges = self.graph("EvA")
        self.assertFalse([n for n in nodes if n.get("foreign")])
        self.assertEqual(len(edges), 1)

    def test_a_need_on_a_name_in_its_own_subject_written_in_full_is_not_one(self):
        self.apply(analysis("a"), analysis("b", ["EvA/a"]), subject="EvA")
        nodes, _ = self.graph("EvA")
        self.assertFalse([n for n in nodes if n.get("foreign")])

    def test_one_node_is_shared_by_the_analyses_which_need_it(self):
        self.apply(analysis("fit"), subject="EvB")
        self.apply(analysis("x", ["EvB/fit"]), analysis("y", ["EvB/fit"]), subject="EvA")
        nodes, edges = self.graph("EvA")
        self.assertEqual(len([n for n in nodes if n.get("foreign")]), 1)
        self.assertEqual(len(edges), 2)

    def test_a_need_which_matches_nothing_gives_no_node(self):
        self.apply(analysis("a", ["EvB/typo"]), subject="EvA")
        nodes, edges = self.graph("EvA")
        self.assertFalse([n for n in nodes if n.get("foreign")])
        self.assertEqual(edges, [])

    def test_a_subject_filter_gives_a_node_for_each(self):
        self.apply(analysis("fit"), subject="EvB")
        self.apply(analysis("fit"), subject="EvC")
        self.apply(analysis("all", ["subject: EvB", "subject: EvC"]), subject="EvA")
        nodes, _ = self.graph("EvA")
        labels = sorted(n["label"].split("<")[0] for n in nodes if n.get("foreign"))
        self.assertEqual(labels, ["EvB/fit", "EvC/fit"])

    def test_many_are_one_node(self):
        for number in range(Event.FOREIGN_NODES_PER_ANALYSIS + 3):
            self.apply(analysis(f"fit{number:02d}"), subject="EvB")
        self.apply(analysis("all", ["subject: EvB"]), subject="EvA")
        nodes, edges = self.graph("EvA")
        foreign = [n for n in nodes if n.get("foreign")]
        self.assertEqual(len(foreign), 1)
        self.assertIn("13 analyses in other subjects", foreign[0]["label"])
        self.assertEqual(len(edges), 1)

    def test_reading_the_report_does_not_read_the_other_subjects_twice_over(self):
        """Only what the analyses of the subject reach is read."""
        self.apply(analysis("fit"), subject="EvB")
        self.apply(analysis("a", ["EvB/fit"]), subject="EvA")
        fresh = YAMLLedger(".asimov/ledger.yml")
        subject = fresh.get_event("EvA")[0]
        pairs = subject.foreign_dependencies()
        self.assertEqual([(n.name, [d.name for d in deps]) for n, deps in pairs], [("a", ["fit"])])


# The drawing rules, from the report's own script.
def drawing_script():
    import inspect

    import asimov.cli.report as report

    source = inspect.getsource(report)
    start = source.index("function isNodeVisible(n, filters)")
    end = source.index("// Rendering a Mermaid graph")
    body = source[start:end].replace("\\\\n", "\\n")
    return "var MERMAID_CLASSDEFS = 'classDef x fill:#fff';\n" + body


@unittest.skipUnless(NODE, "node is not installed")
class DrawingTests(unittest.TestCase):
    def run_js(self, graph, filters="{hiddenStatuses: new Set(), hiddenReviews: new Set()}"):
        script = drawing_script() + f"\nconsole.log(buildMermaidDef({json.dumps(graph)}, {filters}));"
        result = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    GRAPH = {
        "nodes": [
            {"id": "a", "label": "a", "status": "ready", "review": "none"},
            {"id": "f", "label": "EvB/fit", "status": "finished", "review": "none", "foreign": True},
            {"id": "lonely", "label": "EvC/x", "status": "finished", "review": "none", "foreign": True},
        ],
        "edges": [{"from": "f", "to": "a"}],
    }

    def test_a_foreign_node_is_drawn_dashed_with_its_edge(self):
        output = self.run_js(self.GRAPH)
        self.assertIn("f[\"EvB/fit\"]:::finished", output)
        self.assertIn("f --> a", output)
        self.assertIn("class f foreign", output)
        self.assertIn("classDef foreign", drawing_script() + open("asimov/cli/report.py").read())

    def test_one_which_nothing_needs_is_not_drawn(self):
        self.assertNotIn("lonely", self.run_js(self.GRAPH))

    def test_hiding_the_analysis_hides_what_it_needs(self):
        output = self.run_js(
            self.GRAPH, "{hiddenStatuses: new Set(['ready']), hiddenReviews: new Set()}"
        )
        self.assertNotIn("EvB/fit", output)

    def test_a_status_filter_can_hide_a_foreign_node(self):
        output = self.run_js(
            self.GRAPH, "{hiddenStatuses: new Set(['finished']), hiddenReviews: new Set()}"
        )
        self.assertNotIn("EvB/fit", output)
        self.assertIn("a[\"a\"]", output)


class ReportScriptTests(unittest.TestCase):
    def setUp(self):
        import inspect

        import asimov.cli.report as report

        self.source = inspect.getsource(report)

    def test_they_are_not_counted_in_the_statistics(self):
        start = self.source.index("function calculateStats()")
        body = self.source[start:self.source.index("function checkEventVisibility", start)]
        self.assertIn("if (n.foreign) return;", body)

    def test_they_do_not_keep_an_event_visible_or_drawn(self):
        for name in ("function hasVisibleNodes(gd)", "function checkEventVisibility()"):
            start = self.source.index(name)
            body = self.source[start:start + 900]
            self.assertIn("!n.foreign", body, name)


if __name__ == "__main__":
    unittest.main()
