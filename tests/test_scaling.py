"""
Tests for changes which keep large projects tractable.
"""

import logging
import unittest

from asimov import set_logger_level
from asimov.cli.report import _RawHTML


class TestSetLoggerLevel(unittest.TestCase):
    def test_sets_level_without_clearing_every_logger_cache(self):
        parent = logging.getLogger("asimov.test_scaling")
        child = parent.getChild("event").getChild("GW150914")
        calls = []
        original = logging.Logger.manager._clear_cache
        logging.Logger.manager._clear_cache = lambda: calls.append(1)
        try:
            set_logger_level(child, logging.DEBUG)
            set_logger_level(child, logging.DEBUG)
        finally:
            logging.Logger.manager._clear_cache = original
        self.assertEqual(child.level, logging.DEBUG)
        self.assertTrue(child.isEnabledFor(logging.DEBUG))
        self.assertEqual(calls, [])


class TestRawHTML(unittest.TestCase):
    def test_not_parsed_as_markdown(self):
        html = "<div class='x'>*not emphasis*\n\n    indented</div>"
        self.assertEqual(repr(_RawHTML(html)), html)
        self.assertEqual(str(_RawHTML(html)), html)

    def test_otter_writes_it_verbatim(self):
        import otter

        report = otter.Otter.__new__(otter.Otter)
        report.items = []
        report.add(_RawHTML("<p>*raw*</p>"))
        self.assertEqual(repr(report.items[0]), "<p>*raw*</p>")


if __name__ == "__main__":
    unittest.main()
