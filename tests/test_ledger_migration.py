"""
Tests for converting ledgers between the YAML and SQL backends.
"""

import os
import shutil
import tempfile
import unittest

import yaml
from click.testing import CliRunner

from asimov.cli import project
from asimov.ledger_migration import (
    MigrationError,
    differences,
    migrate_ledger,
    read_sql_ledger,
    read_yaml_ledger,
)

LEDGER = {
    "asimov": {"version": "0.8.0"},
    "project": {"name": "Migration Test"},
    "pipelines": {"bilby": {"sampler": {"sampler": "dynesty"}}},
    "priors": {"chirp mass": {"minimum": 10}},
    "events": [
        {
            "name": "GW150914",
            "repository": "https://git.example.org/GW150914.git",
            "working directory": "/work/GW150914",
            "interferometers": ["H1", "L1"],
            "event time": 1126259462.4,
            "productions": [
                {
                    "Prod0": {
                        "name": "Prod0",
                        "event": "GW150914",
                        "pipeline": "bilby",
                        "status": "finished",
                        "comment": "first run",
                        "needs": [],
                        "review": [{"status": "approved", "message": "ok"}],
                        "waveform": {"approximant": "IMRPhenomXPHM"},
                    }
                },
                {
                    "Prod1": {
                        "pipeline": "bilby",
                        "status": "ready",
                        "needs": ["Prod0"],
                    }
                },
            ],
        },
        {
            "name": "GW151012",
            "repository": "https://git.example.org/GW151012.git",
            "working directory": "/work/GW151012",
            "productions": [],
        },
    ],
    "project analyses": [
        {"name": "Combine", "pipeline": "pesummary", "status": "ready"},
    ],
    "trash": {"events": {"Old": {"name": "Old"}}},
}


class MigrationTestCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.yaml_path = os.path.join(self.dir, "ledger.yml")
        self.db_path = os.path.join(self.dir, "ledger.db")
        with open(self.yaml_path, "w") as f:
            yaml.dump(LEDGER, f)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)


class TestMigrateLedger(MigrationTestCase):
    def test_yaml_to_sql(self):
        report = migrate_ledger("yamlfile", self.yaml_path, "sqlite", self.db_path)

        self.assertTrue(report.verified)
        self.assertEqual(
            report.counts, {"events": 2, "productions": 2, "project analyses": 1}
        )
        migrated = read_sql_ledger(self.db_path)
        self.assertEqual(migrated.config["project"]["name"], "Migration Test")
        self.assertEqual(migrated.config["trash"], LEDGER["trash"])
        self.assertEqual(
            {p["name"] for p in migrated.productions["GW150914"]}, {"Prod0", "Prod1"}
        )

    def test_project_defaults_are_stored_on_events(self):
        """SQL ledgers don't apply defaults, so the migration must bake them in."""
        migrate_ledger("yamlfile", self.yaml_path, "sqlite", self.db_path)
        for event in read_sql_ledger(self.db_path).events:
            self.assertEqual(event["priors"], LEDGER["priors"])

    def test_sql_to_yaml(self):
        migrate_ledger("yamlfile", self.yaml_path, "sqlite", self.db_path)
        out = os.path.join(self.dir, "back.yml")

        migrate_ledger("sqlite", self.db_path, "yamlfile", out)

        with open(out) as f:
            data = yaml.safe_load(f)
        self.assertEqual(data["project"]["name"], "Migration Test")
        self.assertEqual([e["name"] for e in data["events"]], ["GW150914", "GW151012"])
        prod1 = next(
            p["Prod1"] for p in data["events"][0]["productions"] if "Prod1" in p
        )
        self.assertEqual(prod1["needs"], ["Prod0"])

    def test_round_trip_is_lossless(self):
        original = read_yaml_ledger(self.yaml_path)
        back = os.path.join(self.dir, "back.yml")

        migrate_ledger("yamlfile", self.yaml_path, "sqlite", self.db_path)
        migrate_ledger("sqlite", self.db_path, "yamlfile", back)

        self.assertEqual(
            differences(original, read_yaml_ledger(back, merge_defaults=False)), []
        )

    def test_migrated_yaml_loads_as_a_ledger(self):
        from asimov.ledger import YAMLLedger

        migrate_ledger("yamlfile", self.yaml_path, "sqlite", self.db_path)
        out = os.path.join(self.dir, "back.yml")
        migrate_ledger("sqlite", self.db_path, "yamlfile", out)

        ledger = YAMLLedger(out)
        self.assertEqual(set(ledger.events), {"GW150914", "GW151012"})
        self.assertEqual(len(ledger.data["project analyses"]), 1)

    def test_source_is_not_modified(self):
        with open(self.yaml_path, "rb") as f:
            before = f.read()
        migrate_ledger("yamlfile", self.yaml_path, "sqlite", self.db_path)
        with open(self.yaml_path, "rb") as f:
            self.assertEqual(f.read(), before)

    def test_refuses_to_overwrite_an_existing_destination(self):
        with open(self.db_path, "w") as f:
            f.write("precious")
        with self.assertRaises(MigrationError):
            migrate_ledger("yamlfile", self.yaml_path, "sqlite", self.db_path)
        with open(self.db_path) as f:
            self.assertEqual(f.read(), "precious")

    def test_same_kind_is_rejected(self):
        with self.assertRaises(MigrationError):
            migrate_ledger(
                "yamlfile", self.yaml_path, "yamlfile", os.path.join(self.dir, "x.yml")
            )

    def test_unsupported_engine_is_rejected(self):
        with self.assertRaises(MigrationError):
            migrate_ledger("tinydb", self.db_path, "yamlfile", "out.yml")

    def test_missing_source_does_not_create_a_database(self):
        with self.assertRaises(MigrationError):
            migrate_ledger("sqlite", self.db_path, "yamlfile", os.path.join(self.dir, "o.yml"))
        self.assertFalse(os.path.exists(self.db_path))

    def test_dry_run_writes_nothing(self):
        report = migrate_ledger(
            "yamlfile", self.yaml_path, "sqlite", self.db_path, dry_run=True
        )
        self.assertTrue(report.dry_run)
        self.assertTrue(report.verified)
        self.assertFalse(os.path.exists(self.db_path))

    def test_failed_write_leaves_no_destination(self):
        broken = dict(LEDGER)
        broken["events"] = [
            dict(LEDGER["events"][0], productions=[{"Bad": {"status": "ready"}}])
        ]
        with open(self.yaml_path, "w") as f:
            yaml.dump(broken, f)

        with self.assertRaises(MigrationError) as raised:
            migrate_ledger("yamlfile", self.yaml_path, "sqlite", self.db_path)

        self.assertIn("GW150914", str(raised.exception))
        self.assertFalse(os.path.exists(self.db_path))


class TestMigrateLedgerCommand(MigrationTestCase):
    def setUp(self):
        super().setUp()
        self.cwd = os.getcwd()
        os.makedirs(os.path.join(self.dir, ".asimov"))
        self.conf = os.path.join(self.dir, ".asimov", "asimov.conf")
        shutil.move(self.yaml_path, os.path.join(self.dir, ".asimov", "ledger.yml"))
        with open(self.conf, "w") as f:
            f.write(
                "[ledger]\nengine = yamlfile\nlocation = .asimov/ledger.yml\n"
            )
        os.chdir(self.dir)

    def tearDown(self):
        os.chdir(self.cwd)
        super().tearDown()

    def invoke(self, *args):
        return CliRunner().invoke(project.migrate_ledger, list(args))

    def test_migrates_and_switches(self):
        result = self.invoke("--to", "sqlite")

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertTrue(os.path.exists(".asimov/ledger.db"))
        self.assertTrue(os.path.exists(".asimov/ledger.yml"))
        with open(self.conf) as f:
            text = f.read()
        self.assertIn("engine = sqlite", text)
        self.assertIn("location = .asimov/ledger.db", text)
        self.assertTrue(os.path.exists(self.conf + ".bak"))

    def test_no_switch_leaves_config_alone(self):
        with open(self.conf) as f:
            before = f.read()
        result = self.invoke("--to", "sqlite", "--no-switch")

        self.assertEqual(result.exit_code, 0, result.output)
        with open(self.conf) as f:
            self.assertEqual(f.read(), before)

    def test_dry_run_changes_nothing(self):
        result = self.invoke("--to", "sqlite", "--dry-run")

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Dry run", result.output)
        self.assertFalse(os.path.exists(".asimov/ledger.db"))

    def test_already_on_target_engine(self):
        result = self.invoke("--to", "yamlfile")
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("already uses", result.output)

    def test_round_trip_through_the_cli(self):
        self.assertEqual(self.invoke("--to", "sqlite").exit_code, 0)
        result = self.invoke("--to", "yamlfile", "--dest", ".asimov/back.yml")

        self.assertEqual(result.exit_code, 0, result.output)
        with open(".asimov/back.yml") as f:
            self.assertEqual(len(yaml.safe_load(f)["events"]), 2)


if __name__ == "__main__":
    unittest.main()
