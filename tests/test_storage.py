"""
Tests for asimov.storage.Store.

Regression coverage for a bug found while building asimov.provenance (#154):
``Manifest.uuid_dict`` built fetch paths from a resource's UUID, but
``Store.add_file`` always writes files to disk under their own name (see
``Store.add_file``), never renamed to their UUID. So ``Store.fetch_file``/
``fetch_uuid`` looked for a file that was never created, and would raise
``FileNotFoundError`` for anything actually stored via ``add_file``.
"""

import os
import shutil
import unittest

from asimov.storage import Store


class StoreRoundTripTests(unittest.TestCase):
    def setUp(self):
        self.cwd = os.getcwd()
        self.tmp_dir = os.path.join(self.cwd, "tests", "tmp", "store_test")
        os.makedirs(self.tmp_dir)
        os.chdir(self.tmp_dir)
        self.root = "results"
        Store.create(root=self.root, name="Test store")
        self.store = Store(root=self.root)

        self.source_file = "sample.dat"
        with open(self.source_file, "w") as source:
            source.write("hello asimov\n")

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.tmp_dir)

    def test_fetch_file_returns_a_path_that_exists(self):
        added = self.store.add_file("GW150914_095045", "TestAnalysis", self.source_file)

        fetched_path = self.store.fetch_file(
            "GW150914_095045", "TestAnalysis", self.source_file
        )

        self.assertTrue(os.path.isfile(fetched_path))
        with open(fetched_path) as fetched:
            self.assertEqual(fetched.read(), "hello asimov\n")
        self.assertEqual(added["hash"], self.store.manifest.get_hash(added["uuid"]))

    def test_fetch_file_checks_the_supplied_hash(self):
        added = self.store.add_file("GW150914_095045", "TestAnalysis", self.source_file)

        with self.assertRaises(Exception):
            self.store.fetch_file(
                "GW150914_095045", "TestAnalysis", self.source_file, hash="not-the-real-hash"
            )

        # A correct hash still works.
        self.store.fetch_file(
            "GW150914_095045", "TestAnalysis", self.source_file, hash=added["hash"]
        )

    def test_fetch_uuid_matches_fetch_file(self):
        added = self.store.add_file("GW150914_095045", "TestAnalysis", self.source_file)

        by_name = self.store.fetch_file("GW150914_095045", "TestAnalysis", self.source_file)
        by_uuid = self.store.fetch_uuid(added["uuid"])

        self.assertEqual(os.path.abspath(by_name), os.path.abspath(by_uuid))
