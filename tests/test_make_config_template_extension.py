"""Tests for Production/Analysis.make_config's template filename resolution."""

import os
import unittest
from unittest.mock import patch, mock_open

from asimov import config
from asimov.analysis import Analysis


class FakePipeline:
    """A pipeline stand-in whose config lives in a non-.ini file."""

    config_template = "/bundled/myplugin.toml"

    def __str__(self):
        return "myplugin"


class MakeConfigTemplateExtensionTests(unittest.TestCase):
    def _make_analysis(self, pipeline):
        analysis = Analysis.__new__(Analysis)
        analysis.meta = {}
        analysis.pipeline = pipeline
        return analysis

    def tearDown(self):
        if config.has_section("templating"):
            config.remove_section("templating")

    def test_templating_directory_override_respects_pipeline_extension(self):
        """When [templating] directory is set, the pipeline's own
        config_template extension should be used, not a hardcoded .ini."""
        analysis = self._make_analysis(FakePipeline())

        config.add_section("templating")
        config.set("templating", "directory", "/deployment/templates")

        with patch("asimov.analysis.Liquid") as mock_liquid, \
                patch("builtins.open", mock_open()):
            mock_liquid.return_value.render.return_value = "rendered"
            analysis.make_config("/tmp/out.toml")

        template_file_arg = mock_liquid.call_args[0][0]
        self.assertEqual(
            template_file_arg,
            os.path.join("/deployment/templates", "myplugin.toml"),
        )

    def test_explicit_template_extension_is_preserved_with_override(self):
        """An explicit --template value that already has its own extension
        (e.g. `testinggr.ini`) must not get a second extension appended."""
        analysis = self._make_analysis(FakePipeline())
        analysis.meta["template"] = "testinggr.ini"

        config.add_section("templating")
        config.set("templating", "directory", "/deployment/templates")

        with patch("asimov.analysis.Liquid") as mock_liquid, \
                patch("builtins.open", mock_open()):
            mock_liquid.return_value.render.return_value = "rendered"
            analysis.make_config("/tmp/out.ini")

        template_file_arg = mock_liquid.call_args[0][0]
        self.assertEqual(
            template_file_arg,
            os.path.join("/deployment/templates", "testinggr.ini"),
        )

    def test_explicit_template_without_extension_gets_pipeline_extension(self):
        """An extensionless explicit --template value still gets the
        pipeline's derived extension appended."""
        analysis = self._make_analysis(FakePipeline())
        analysis.meta["template"] = "custom-template"

        config.add_section("templating")
        config.set("templating", "directory", "/deployment/templates")

        with patch("asimov.analysis.Liquid") as mock_liquid, \
                patch("builtins.open", mock_open()):
            mock_liquid.return_value.render.return_value = "rendered"
            analysis.make_config("/tmp/out.toml")

        template_file_arg = mock_liquid.call_args[0][0]
        self.assertEqual(
            template_file_arg,
            os.path.join("/deployment/templates", "custom-template.toml"),
        )

    def test_default_bundled_template_used_without_override(self):
        """Without a [templating] directory override, the pipeline's own
        config_template path should be used directly, as before."""
        analysis = self._make_analysis(FakePipeline())

        with patch("asimov.analysis.Liquid") as mock_liquid, \
                patch("builtins.open", mock_open()):
            mock_liquid.return_value.render.return_value = "rendered"
            analysis.make_config("/tmp/out.toml")

        template_file_arg = mock_liquid.call_args[0][0]
        self.assertEqual(template_file_arg, FakePipeline.config_template)


if __name__ == "__main__":
    unittest.main()
