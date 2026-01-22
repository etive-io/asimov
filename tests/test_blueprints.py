import unittest

from asimov import blueprints

class TestAnalysisBlueprint(unittest.TestCase):
    def test_blueprints_module_importable(self):
        self.assertIsNotNone(blueprints)