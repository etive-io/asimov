import os
import shutil
import unittest

import click

import asimov.event
from asimov.ledger import YAMLLedger
from asimov.cli.project import make_project
from asimov.cli.application import apply_page
import git
from tests.blueprints import DEFAULTS_PE


TEST_LEDGER = """

"""

class DAGTests(unittest.TestCase):
    """All the tests to check production DAGs are generated successfully."""
    @classmethod
    def setUpClass(cls):
        cls.cwd = os.getcwd()
    
    @classmethod
    def tearDownClass(cls):
        """Destroy all the products of this test."""
        os.chdir(cls.cwd)

    def setUp(self):
        os.makedirs(f"{self.cwd}/tests/tmp/project")
        os.chdir(f"{self.cwd}/tests/tmp/project")
        make_project(
            name="Test project", root=f"{self.cwd}/tests/tmp/project", engine="yamlfile"
        )
        self.ledger = YAMLLedger(f".asimov/ledger.yml")
        apply_page(file=DEFAULTS_PE, event=None, ledger=self.ledger)
        apply_page(file = f"{self.cwd}/tests/test_data/events_blueprint.yaml", ledger=self.ledger)


    def tearDown(self):
        del(self.ledger)
        shutil.rmtree(f"{self.cwd}/tests/tmp/project")

    def test_dependency_list(self):
        """Check that all jobs are run when the dependencies are a chain."""
        self.assertTrue(len(self.ledger.get_event('GW150914_095045')[0].productions)==0)
        apply_page(file = f"{self.cwd}/tests/test_data/test_linear_dag.yaml", ledger=self.ledger)
        event = self.ledger.get_event('GW150914_095045')[0]
        self.assertTrue(len(event.productions[0]._needs) == 0)
        self.assertTrue(len(event.productions[0].dependencies) == 0)
        self.assertTrue(len(event.productions[1].dependencies) == 1)

    def test_dependency_tree(self):
        apply_page(file = f"{self.cwd}/tests/test_data/test_linear_dag.yaml", ledger=self.ledger)
        event = self.ledger.get_event('GW150914_095045')[0]
        self.assertTrue(len(event.graph.edges) == 1)
        
    def test_linear_dag(self):
        """Check that all jobs are run when the dependencies are a chain."""
        apply_page(file = f"{self.cwd}/tests/test_data/test_linear_dag.yaml", ledger=self.ledger)
        event = self.ledger.get_event('GW150914_095045')[0]
        self.assertEqual(len(event.get_all_latest()), 1)
    
    def test_simple_dag(self):
        """Check that all jobs are run when there are no dependencies specified."""
        apply_page(file = f"{self.cwd}/tests/test_data/test_simple_dag.yaml", ledger=self.ledger)
        event = self.ledger.get_event('GW150914_095045')[0]
        self.assertEqual(len(event.get_all_latest()), 2)   

    def test_complex_dag(self):
        """Check that all jobs are run when the dependencies are not a chain."""

        apply_page(file = f"{self.cwd}/tests/test_data/test_complex_dag.yaml", event='GW150914_095045', ledger=self.ledger)
        event = self.ledger.get_event('GW150914_095045')[0]
        print([ev.name for ev in event.get_all_latest()])
        self.assertEqual(len(event.get_all_latest()), 2)
        
    def test_query_dag(self):
        """Check that all jobs are run when the dependencies are not a chain."""

        apply_page(file = f"{self.cwd}/tests/test_data/test_query_dag.yaml", event='GW150914_095045', ledger=self.ledger)
        event = self.ledger.get_event('GW150914_095045')[0]

        self.assertEqual(len(event.get_all_latest()), 1)
        


DIAMOND = """
kind: analysis
name: a
pipeline: simpletestpipeline
status: ready
---
kind: analysis
name: b
pipeline: simpletestpipeline
status: ready
needs: [a]
---
kind: analysis
name: c
pipeline: simpletestpipeline
status: ready
needs: [a]
---
kind: analysis
name: d
pipeline: simpletestpipeline
status: ready
needs: [b, c]
---
kind: analysis
name: e
pipeline: simpletestpipeline
status: ready
"""


def reference_latest(event):
    """The analyses ready to run, computed as get_all_latest used to (via ``reverse()``)."""
    event.update_graph()
    unfinished = event.graph.subgraph(
        [p for p in event.productions if p.finished is False and p.status not in {"wait"}]
    )
    ends = [
        p
        for p in unfinished.reverse().nodes()
        if unfinished.reverse().out_degree(p) == 0 and p.finished is False
    ]
    return {p for p in ends if p.status.lower() == "ready"}


class LatestAnalysesTests(unittest.TestCase):
    """get_all_latest should return the analyses with nothing unfinished upstream."""

    @classmethod
    def setUpClass(cls):
        cls.cwd = os.getcwd()

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls.cwd)

    def setUp(self):
        self.root = f"{self.cwd}/tests/tmp/latest_project"
        os.makedirs(self.root)
        os.chdir(self.root)
        make_project(name="Test project", root=self.root, engine="yamlfile")
        self.ledger = YAMLLedger(".asimov/ledger.yml")
        apply_page(file=DEFAULTS_PE, event=None, ledger=self.ledger)
        apply_page(file=f"{self.cwd}/tests/test_data/events_blueprint.yaml", ledger=self.ledger)
        with open("diamond.yaml", "w") as handle:
            handle.write(DIAMOND)
        apply_page(file="diamond.yaml", event="GW150914_095045", ledger=self.ledger)
        self.event = self.ledger.get_event("GW150914_095045")[0]

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.root, ignore_errors=True)

    def names(self):
        return {p.name for p in self.event.get_all_latest()}

    def set_status(self, **statuses):
        for production in self.event.productions:
            production.status = statuses.get(production.name, "ready")

    def test_only_unblocked_analyses_are_returned(self):
        self.assertEqual(self.names(), {"a", "e"})

    def test_finishing_the_head_releases_its_dependents(self):
        self.set_status(a="finished")
        self.assertEqual(self.names(), {"b", "c", "e"})

    def test_a_join_waits_for_every_branch(self):
        self.set_status(a="finished", b="finished")
        self.assertEqual(self.names(), {"c", "e"})
        self.set_status(a="finished", b="finished", c="finished")
        self.assertEqual(self.names(), {"d", "e"})

    def test_running_analyses_are_not_returned(self):
        self.set_status(a="running")
        self.assertEqual(self.names(), {"e"})

    def test_matches_the_reverse_based_result_for_every_status_combination(self):
        import itertools

        for combination in itertools.product(["ready", "finished", "running", "wait"], repeat=5):
            self.set_status(**dict(zip("abcde", combination)))
            self.assertEqual(
                set(self.event.get_all_latest()),
                reference_latest(self.event),
                combination,
            )
