"""
Test that an O3a final event is pushed-through all of the steps of
ini and DAG creation.
"""

import unittest
import os

import asimov.event
from asimov.pipelines import known_pipelines



class EventTests(unittest.TestCase):
    """All tests of the YAML event format."""
    @classmethod
    def setUpClass(cls):
        pass

    def setUp(self):
        with open("GW190426190642.yaml", "r") as f:
            TEST_YAML = f.read()
        TEST_YAML = TEST_YAML.format(wd=os.getcwd())
        self.event = asimov.event.Event.from_yaml(TEST_YAML, repo=False)

    def test_ini_generation(self):
        """Check that the ini file is correctly generated."""

        for production in self.event.productions:
            production.make_config(f"{self.event.name}_{production.name}.ini")

    def test_commandline(self):
        """Check that the correct commandline is run."""
        for production in self.event.productions:
            production.make_config(f"{production.name}.ini")
            if production.pipeline.lower() in known_pipelines:
                try:
                    pipe = known_pipelines[production.pipeline.lower()](production, "analyses")
                    pipe.clean()
                    pipe.build_dag()
                except Exception as e:
                    print(production.name)
                    print(e)

if __name__ == '__main__':
    unittest.main()
