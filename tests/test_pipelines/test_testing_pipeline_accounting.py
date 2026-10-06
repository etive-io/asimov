"""
Tests for the shared accounting/request-disk submit-file helper used by
asimov's bundled testing pipelines (SimpleTestPipeline, SubjectTestPipeline,
ProjectTestPipeline).

This helper exists so those pipelines can be submitted to a production-like
LIGO Data Grid pool -- which rejects jobs missing a valid accounting_group
or explicit request_disk -- and not just the permissive disposable pool
most CI uses.
"""

import configparser
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from asimov.pipelines.testing import _util


def _production(meta=None):
    return SimpleNamespace(meta=meta or {})


class AccountingSubmitLinesTests(unittest.TestCase):
    def setUp(self):
        self.test_config = configparser.ConfigParser()
        patcher = patch.object(_util, "asimov_config", self.test_config)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_falls_back_to_fixture_tag_with_no_config_or_meta(self):
        lines = _util.accounting_submit_lines(_production())
        self.assertIn(
            f"accounting_group = {_util.FALLBACK_ACCOUNTING_GROUP}\n", lines
        )
        self.assertTrue(any(line.startswith("request_disk = ") for line in lines))
        self.assertFalse(
            any(line.startswith("accounting_group_user") for line in lines)
        )

    def test_production_meta_takes_priority_over_config(self):
        self.test_config["condor"] = {"accounting": "should.not.be.used"}
        production = _production(
            {
                "scheduler": {
                    "accounting group": "ligo.dev.o4.cbc.test.test",
                    "accounting group user": "someuser",
                    "request disk": "250MB",
                }
            }
        )
        lines = _util.accounting_submit_lines(production)
        self.assertIn("accounting_group = ligo.dev.o4.cbc.test.test\n", lines)
        self.assertIn("accounting_group_user = someuser\n", lines)
        self.assertIn("request_disk = 250MB\n", lines)

    def test_falls_back_to_condor_config_section(self):
        self.test_config["condor"] = {
            "accounting": "ligo.dev.o4.cbc.test.test",
            "user": "submituser",
        }
        lines = _util.accounting_submit_lines(_production())
        self.assertIn("accounting_group = ligo.dev.o4.cbc.test.test\n", lines)
        self.assertIn("accounting_group_user = submituser\n", lines)

    def test_never_writes_a_getenv_line(self):
        # Regression guard: a real LDG pool with SUBMIT_ALLOW_GETENV = False
        # rejects submissions that set getenv = true outright, so callers
        # must not reintroduce that alongside these lines.
        lines = _util.accounting_submit_lines(_production())
        self.assertFalse(any("getenv" in line.lower() for line in lines))


if __name__ == "__main__":
    unittest.main()
