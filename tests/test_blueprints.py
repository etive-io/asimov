import unittest

import pydantic

from asimov import blueprints

class TestAnalysisBlueprint(unittest.TestCase):
    def test_blueprints_module_importable(self):
        self.assertIsNotNone(blueprints)


class TestLikelihoodComponents(unittest.TestCase):
    def test_valid_components_validate(self):
        likelihood = blueprints.Likelihood.model_validate(
            {
                "sample rate": 4096,
                "components": {
                    "signal": "wavelets",
                    "glitch": "wavelets",
                    "noise": {"psd": "fit", "lines": True},
                },
            },
            strict=True,
        )
        self.assertEqual(likelihood.components.signal, "wavelets")
        self.assertEqual(likelihood.components.glitch, "wavelets")
        self.assertEqual(likelihood.components.noise.psd, "fit")
        self.assertTrue(likelihood.components.noise.lines)

    def test_analysis_blueprint_with_components_validates(self):
        analysis = blueprints.Analysis.model_validate(
            {
                "name": "Prod0",
                "comment": "test",
                "likelihood": {
                    "sample rate": 4096,
                    "components": {
                        "signal": "cbc",
                        "noise": {"psd": "fixed"},
                    },
                },
            },
            strict=True,
        )
        self.assertEqual(analysis.likelihood.components.signal, "cbc")

    def test_invalid_signal_value_is_rejected(self):
        with self.assertRaises(pydantic.ValidationError):
            blueprints.Likelihood.model_validate(
                {
                    "sample rate": 4096,
                    "components": {"signal": "sinegaussian"},
                },
                strict=True,
            )

    def test_unknown_key_under_components_is_rejected(self):
        with self.assertRaises(pydantic.ValidationError):
            blueprints.Likelihood.model_validate(
                {
                    "sample rate": 4096,
                    "components": {"signal model": "cbc"},
                },
                strict=True,
            )