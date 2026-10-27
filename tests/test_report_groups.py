"""
The report shows the analyses which strategies made as groups, with a matrix
placed by two metadata keys (#235).
"""
import os
import shutil
import tempfile
import types
import unittest

from asimov.cli.application import apply_page
from asimov.cli.project import make_project
from asimov.groups import Member
from asimov.ledger import YAMLLedger
from asimov.report_groups import (
    build_matrix,
    find_groups,
    groups_html,
    lookup,
    panel_html,
)
from asimov.strategies import read_group
from tests.test_chain_until_idle_e2e import CLI, EndToEndCase

TOY = (
    "kind: analysis\nname: {name}\nstrategy:\n  type: toy-rounds\n  rounds: {rounds}\n"
    "{report}"
)
REPORT = "report:\n  rows: stream\n  columns: round\n"


def fake(name, status="ready", subject="S", **meta):
    analysis = types.SimpleNamespace(name=name, status=status, meta=meta)
    return Member(analysis, subject)


class LookupTests(unittest.TestCase):
    def test_a_key(self):
        self.assertEqual(lookup({"round": 3}, "round"), "3")

    def test_a_dotted_key_reaches_into_a_mapping(self):
        self.assertEqual(lookup({"a": {"b": {"c": "x"}}}, "a.b.c"), "x")

    def test_a_key_with_a_dot_in_it_is_found_whole(self):
        self.assertEqual(lookup({"likelihood.minimum": 20}, "likelihood.minimum"), "20")

    def test_what_is_missing_is_none(self):
        self.assertIsNone(lookup({"a": 1}, "b"))
        self.assertIsNone(lookup({"a": 1}, "a.b"))
        self.assertIsNone(lookup({"a": None}, "a"))
        self.assertIsNone(lookup(None, "a"))

    def test_a_mapping_or_list_is_not_a_value_for_a_cell(self):
        self.assertIsNone(lookup({"a": {"b": 1}}, "a"))
        self.assertIsNone(lookup({"a": [1]}, "a"))


class MatrixTests(unittest.TestCase):
    def test_analyses_are_placed_by_the_two_keys(self):
        members = [
            fake("a", stream="A", round=1),
            fake("b", stream="A", round=2),
            fake("c", stream="B", round=1),
        ]
        matrix = build_matrix(members, "stream", "round")
        self.assertEqual(matrix["rows"], ["A", "B"])
        self.assertEqual(matrix["columns"], ["1", "2"])
        self.assertEqual([m.name for m in matrix["cells"][("A", "2")]], ["b"])

    def test_a_combination_which_does_not_exist_is_absent(self):
        members = [fake("a", stream="A", round=1), fake("b", stream="B", round=2)]
        matrix = build_matrix(members, "stream", "round")
        self.assertNotIn(("A", "2"), matrix["cells"])
        self.assertNotIn(("B", "1"), matrix["cells"])

    def test_numbers_sort_as_numbers_and_numbered_words_in_order(self):
        members = [fake(str(n), stream=f"s{n}", round=n) for n in (10, 2, 1)]
        matrix = build_matrix(members, "stream", "round")
        self.assertEqual(matrix["columns"], ["1", "2", "10"])
        self.assertEqual(matrix["rows"], ["s1", "s2", "s10"])

    def test_an_analysis_without_either_key_is_not_placed(self):
        matrix = build_matrix([fake("a", stream="A"), fake("b", round=1)], "stream", "round")
        self.assertEqual(matrix["cells"], {})
        self.assertEqual(len(matrix["unplaced"]), 2)

    def test_two_analyses_may_share_a_cell(self):
        members = [fake("a", stream="A", round=1), fake("b", stream="A", round=1)]
        matrix = build_matrix(members, "stream", "round")
        self.assertEqual(len(matrix["cells"][("A", "1")]), 2)


class PanelTests(unittest.TestCase):
    def members(self):
        return [
            fake("a", "finished", "S1", stream="A", round=1),
            fake("b", "stuck", "S2", stream="B", round=1),
        ]

    def test_a_group_without_matrix_settings_still_has_its_summary(self):
        html = panel_html("fit", "chain", self.members(), record={"blueprint": {}})
        self.assertIn("2 analyses: 1 finished, 1 stuck", html)
        self.assertNotIn("<table", html)
        self.assertIn('data-status="stuck"', html)

    def test_the_matrix_has_a_cell_per_analysis_coloured_by_status(self):
        record = {"blueprint": {"report": {"rows": "stream", "columns": "round"}}}
        html = panel_html("fit", "chain", self.members(), record)
        self.assertEqual(html.count("group-cell s-"), 2)
        self.assertIn("group-cell s-done", html)
        self.assertIn("group-cell s-stuck", html)
        self.assertIn('data-key="S1/a"', html)

    def test_only_one_key_is_not_a_matrix(self):
        record = {"blueprint": {"report": {"rows": "stream"}}}
        self.assertNotIn("group-matrix", panel_html("fit", "chain", self.members(), record))

    def test_nothing_in_it_can_break_out_of_the_page(self):
        member = fake('x"><script>alert(1)</script>', "ready", "S", stream='<b>', round=1)
        record = {"blueprint": {"report": {"rows": "stream", "columns": "round"}}}
        html = panel_html('<i>id</i>', "t<y>pe", [member], record)
        self.assertNotIn("<script>alert", html)
        self.assertNotIn("<i>id", html)
        self.assertNotIn("<b>", html)

    def test_an_unknown_status_is_drawn_as_other(self):
        html = panel_html("fit", "chain", [fake("a", "frobnicated", stream="A", round=1)],
                          {"blueprint": {"report": {"rows": "stream", "columns": "round"}}})
        self.assertIn("s-other", html)


class FindGroupsTests(unittest.TestCase):
    def test_only_stamped_analyses_are_in_a_group(self):
        subject = types.SimpleNamespace(
            name="S",
            productions=[
                types.SimpleNamespace(name="a", status="ready", meta={"strategy": {"type": "t", "id": "g"}}),
                types.SimpleNamespace(name="b", status="ready", meta={}),
                types.SimpleNamespace(name="c", status="ready", meta={"strategy": {"type": "t", "id": "h"}}),
            ],
        )
        found = find_groups([subject])
        self.assertEqual(list(found), ["g", "h"])
        self.assertEqual([m.name for m in found["g"]["members"]], ["a"])

    def test_no_groups_is_no_section(self):
        subject = types.SimpleNamespace(
            name="S", productions=[types.SimpleNamespace(name="b", status="ready", meta={})]
        )
        self.assertEqual(groups_html([subject]), "")


class LedgerTests(unittest.TestCase):
    def setUp(self):
        os.environ["ASIMOV_TOY_STRATEGY"] = "1"
        self.cwd = os.getcwd()
        self.root = tempfile.mkdtemp()
        os.chdir(self.root)
        make_project(name="Test project", root=self.root, engine="yamlfile")
        self.ledger = YAMLLedger(".asimov/ledger.yml")

    def tearDown(self):
        os.environ.pop("ASIMOV_TOY_STRATEGY", None)
        os.chdir(self.cwd)
        shutil.rmtree(self.root, ignore_errors=True)

    def apply(self, text, subject=None):
        with open("blueprint.yaml", "w") as handle:
            handle.write(text)
        apply_page("blueprint.yaml", event=subject, ledger=self.ledger)

    def section(self):
        ledger = YAMLLedger(".asimov/ledger.yml")
        subjects = [ledger.get_event(name)[0] for name in ledger.subject_names()]
        return groups_html(subjects, ledger.project_analyses, lambda i: read_group(ledger, i))

    def test_a_group_made_by_a_strategy_has_a_matrix_from_its_blueprint(self):
        self.apply(TOY.format(name="toy", rounds=3, report=REPORT))
        html = self.section()
        self.assertIn('id="group-toy"', html)
        # 2 components x 3 rounds of steps, and the combine steps in 'shared'
        self.assertEqual(html.count("group-cell s-"), 9)
        self.assertIn("<th>component-A</th>", html)
        self.assertIn("<th>shared</th>", html)
        self.assertIn("<th>3</th>", html)

    def test_without_settings_the_summary_is_there_and_the_matrix_is_not(self):
        self.apply(TOY.format(name="toy", rounds=2, report=""))
        html = self.section()
        self.assertIn("6 analyses: 6 ready", html)
        self.assertNotIn("<table", html)

    def test_analyses_which_no_strategy_made_are_unaffected(self):
        self.apply("kind: event\nname: E\ninterferometers: [H1]\n")
        self.apply("kind: analysis\nname: solo\npipeline: simpletestpipeline\n", subject="E")
        self.assertEqual(self.section(), "")

    def test_a_status_shows_in_its_cell(self):
        self.apply(TOY.format(name="toy", rounds=2, report=REPORT))
        event = self.ledger.get_event("component-A")[0]
        next(p for p in event.productions if p.name == "step-r1").status = "stuck"
        self.ledger.update_event(event)
        self.assertEqual(self.section().count("group-cell s-stuck"), 1)

    def test_a_group_of_a_few_thousand_analyses_is_quick(self):
        import time

        members = [fake(f"a{i}", ["ready", "finished", "running"][i % 3], f"S{i % 40}", stream=f"s{i % 40}", round=i // 40)
                   for i in range(3000)]
        record = {"blueprint": {"report": {"rows": "stream", "columns": "round"}}}
        start = time.perf_counter()
        html = panel_html("big", "t", members, record)
        self.assertLess(time.perf_counter() - start, 2.0)
        self.assertEqual(html.count("group-cell s-"), 3000)


@unittest.skipUnless(os.path.exists(CLI), "the asimov command is not installed")
class ReportPageTests(EndToEndCase):
    """The page which ``asimov report html`` writes."""

    @classmethod
    def setUpClass(cls):
        os.environ["ASIMOV_TOY_STRATEGY"] = "1"
        super().setUpClass()
        cls.env["ASIMOV_TOY_STRATEGY"] = "1"
        cls.apply(TOY.format(name="toy", rounds=2, report=REPORT))
        cls.apply(
            "kind: analysis\nname: solo\npipeline: simpletestpipeline\nstatus: ready\n", "shared"
        )
        cls.run_cli("report", "html", "--location", os.path.join(cls.root, "out"))
        with open(os.path.join(cls.root, "out", "index.html")) as handle:
            cls.page = handle.read()

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("ASIMOV_TOY_STRATEGY", None)
        super().tearDownClass()

    def test_the_page_has_the_group_and_its_matrix(self):
        self.assertIn("Strategy groups", self.page)
        self.assertIn('id="group-toy"', self.page)
        self.assertEqual(self.page.count("group-cell s-ready"), 6)

    def test_every_cell_can_open_the_analysis_modal(self):
        for key in ("component-A/step-r1", "shared/combine-r2"):
            self.assertIn(f'data-analysis-key="{key}"', self.page)
            self.assertIn(f'data-key="{key}"', self.page)

    def test_an_analysis_which_no_strategy_made_is_in_no_group(self):
        self.assertNotIn('data-key="shared/solo"', self.page)
        self.assertIn('data-analysis-key="shared/solo"', self.page)


if __name__ == "__main__":
    unittest.main()
