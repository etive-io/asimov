"""Perform tests on the base asimov package."""

import unittest
from unittest.mock import patch
from importlib import reload
import asimov

try:
    from importlib.metadata import PackageNotFoundError
except ImportError:
    from importlib_metadata import PackageNotFoundError

class TestAsimovBase(unittest.TestCase):

    @patch("importlib.metadata.version",
           **{
               'side_effect': PackageNotFoundError,
           })
    def testImports(self, blah):
        reload(asimov)

        self.assertEqual(asimov.__version__, "dev")
