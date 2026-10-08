"""
The record of a group of documents made by a plugin strategy (#232).

It is kept in the ledger's project-level data, so it works the same for the
YAML ledger and the database ledgers, and holds what is needed to come back to a
group later and is kept nowhere else: the blueprint, what made it, and the
subjects it made. The name of a group is unique in the project.
"""
import os
import shutil
import tempfile
import types
import unittest
from unittest.mock import patch

import yaml

from asimov.cli.application import apply_page
from asimov.cli.project import make_project
from asimov.ledger import DatabaseLedger, YAMLLedger
from asimov.strategies import (
    GROUPS_KEY,
    Strategy,
    StrategyError,
    plugin_info,
    read_group,
    write_group,
)

from tests.test_plugin_strategies import FakeEntryPoint

EVENT = "kind: event\nname: {name}\ninterferometers: [H1]\n"

BLUEPRINT = """kind: analysis
name: scan
pipeline: simpletestpipeline
status: ready
strategy:
  type: scan
  streams: [S1, S2]
"""


class Scan(Strategy):
    """One subject and one analysis for each of the streams in the blueprint."""

    seen = []

    def expand(self, blueprint, context):
        type(self).seen.append(context.group)
        documents = []
        for stream in blueprint["strategy"].get("streams", []):
            documents.append({"kind": "subject", "name": stream, "interferometers": ["H1"]})
            documents.append({"kind": "analysis", "name": f"fit-{stream}", "event": stream,
                              "pipeline": "simpletestpipeline", "status": "ready"})
        return documents


def provided_by(name="demo", version="1.0"):
    """The strategy ``scan``, registered by a package of this name and version."""
    entry = FakeEntryPoint("scan", Scan)
    entry.dist = types.SimpleNamespace(name=name, version=version)
    return patch("asimov.strategies.entry_points", return_value=[entry])


class GroupsCase(unittest.TestCase):
    def setUp(self):
        self.cwd = os.getcwd()
        self.root = tempfile.mkdtemp()
        os.chdir(self.root)
        self.ledger = self.make_ledger()
        Scan.seen = []
        for name in ("Base", "Other"):
            self.write("event.yaml", EVENT.format(name=name))
            apply_page("event.yaml", ledger=self.ledger)

    def make_ledger(self):
        make_project(name="Test project", root=self.root, engine="yamlfile")
        return YAMLLedger(".asimov/ledger.yml")

    def reopen(self):
        return YAMLLedger(".asimov/ledger.yml")

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, name, text):
        with open(name, "w") as handle:
            handle.write(text)

    def apply(self, text=BLUEPRINT, version="1.0", **kwargs):
        self.write("blueprint.yaml", text)
        with provided_by(version=version):
            return apply_page("blueprint.yaml", ledger=self.ledger, **kwargs)

    def group(self, name="scan"):
        return read_group(self.reopen(), name)


class TheRecordTests(GroupsCase):
    def test_there_is_no_record_before_a_strategy_is_applied(self):
        self.assertIsNone(self.group())

    def test_applying_a_strategy_records_the_group(self):
        self.apply()
        group = self.group()
        self.assertEqual(group["type"], "scan")
        self.assertEqual(group["subjects"], ["S1", "S2"])
        self.assertEqual(group["plugin"], {"name": "demo", "version": "1.0"})
        self.assertNotIn("last extended with", group)

    def test_it_holds_the_blueprint_as_it_was_applied(self):
        self.apply()
        blueprint = self.group()["blueprint"]
        self.assertEqual(blueprint["strategy"], {"type": "scan", "streams": ["S1", "S2"]})
        self.assertEqual(blueprint["pipeline"], "simpletestpipeline")
        self.assertNotIn("kind", blueprint)

    def test_it_is_in_the_ledger_with_the_other_project_data(self):
        self.apply()
        self.assertIn("scan", self.reopen().data[GROUPS_KEY])

    def test_the_subject_the_analyses_are_for_when_they_name_none_is_recorded(self):
        Scan.seen = []

        class Single(Scan):
            def expand(self, blueprint, context):
                return [{"kind": "analysis", "name": "a", "pipeline": "simpletestpipeline"}]

        entry = FakeEntryPoint("scan", Single)
        self.write("blueprint.yaml", BLUEPRINT)
        with patch("asimov.strategies.entry_points", return_value=[entry]):
            apply_page("blueprint.yaml", event="Base", ledger=self.ledger)
        self.assertEqual(self.group()["event"], "Base")

    def test_a_subject_which_was_already_there_is_not_listed(self):
        self.write("s1.yaml", EVENT.format(name="S1"))
        apply_page("s1.yaml", ledger=self.ledger)
        self.apply()
        self.assertEqual(self.group()["subjects"], ["S2"])

    def test_it_is_audited(self):
        self.apply()
        records = list(self.reopen().audit_log(kind="strategygroup"))
        self.assertEqual([r.target for r in records], ["@project/scan"])
        self.assertEqual(records[0].outcome, "added")

    def test_it_can_be_read_and_written_directly(self):
        record = {"type": "t", "blueprint": {"a": [1, 2], "b": {"c": 3}}, "subjects": []}
        write_group(self.ledger, "g", record)
        self.assertEqual(read_group(self.ledger, "g"), record)
        self.assertIsNone(read_group(self.ledger, "nothing"))


class ApplyingAgainTests(GroupsCase):
    def test_the_same_blueprint_changes_nothing(self):
        self.apply()
        before = open(".asimov/ledger.yml").read()
        audited = len(list(self.reopen().audit_log(kind="strategygroup")))
        self.apply()
        self.assertEqual(open(".asimov/ledger.yml").read(), before)
        self.assertEqual(len(list(self.reopen().audit_log(kind="strategygroup"))), audited)

    def test_a_changed_blueprint_replaces_the_blueprint_and_is_audited(self):
        self.apply()
        self.apply(BLUEPRINT.replace("[S1, S2]", "[S1, S2, S3]"))
        group = self.group()
        self.assertEqual(group["blueprint"]["strategy"]["streams"], ["S1", "S2", "S3"])
        self.assertEqual(group["subjects"], ["S1", "S2", "S3"])
        outcomes = [r.outcome for r in self.reopen().audit_log(kind="strategygroup")]
        self.assertEqual(outcomes[0], "added")
        self.assertIn("updated", outcomes[1:])

    def test_an_option_which_is_left_out_is_gone(self):
        self.apply(BLUEPRINT + "  extra: 1\n")
        self.assertEqual(self.group()["blueprint"]["strategy"]["extra"], 1)
        self.apply()
        self.assertNotIn("extra", self.group()["blueprint"]["strategy"])

    def test_the_package_which_made_it_is_kept(self):
        self.apply(version="1.0")
        self.apply(BLUEPRINT.replace("[S1, S2]", "[S1, S2, S3]"), version="2.0")
        self.assertEqual(self.group()["plugin"], {"name": "demo", "version": "1.0"})

    def test_adding_to_it_with_another_version_is_recorded(self):
        self.apply(version="1.0")
        self.apply(BLUEPRINT.replace("[S1, S2]", "[S1, S2, S3]"), version="2.0")
        group = self.group()
        self.assertEqual(group["last extended with"], {"name": "demo", "version": "2.0"})
        self.assertNotEqual(group["plugin"], group["last extended with"])

    def test_applying_with_another_version_but_adding_nothing_is_not(self):
        self.apply(version="1.0")
        self.apply(version="2.0")
        self.assertNotIn("last extended with", self.group())

    def test_the_strategy_is_given_the_record_it_made_before(self):
        self.apply()
        self.apply(BLUEPRINT.replace("[S1, S2]", "[S1, S2, S3]"))
        first, second = Scan.seen
        self.assertIsNone(first)
        self.assertEqual(second["subjects"], ["S1", "S2"])
        self.assertEqual(second["blueprint"]["strategy"]["streams"], ["S1", "S2"])

    def test_the_context_gives_a_copy(self):
        self.apply()
        self.apply()
        Scan.seen[1]["subjects"].append("changed")
        self.assertEqual(self.group()["subjects"], ["S1", "S2"])


class TheNameOfAGroupIsUniqueTests(GroupsCase):
    def test_another_strategy_cannot_use_the_name(self):
        self.apply()
        entry = FakeEntryPoint("other", Scan)
        self.write("blueprint.yaml", BLUEPRINT.replace("type: scan", "type: other"))
        with patch("asimov.strategies.entry_points", return_value=[entry]):
            with self.assertRaisesRegex(StrategyError, "already the name of a group made by the 'scan'"):
                apply_page("blueprint.yaml", ledger=self.ledger)
        self.assertEqual(self.group()["type"], "scan")

    def single(self):
        class Single(Scan):
            def expand(self, blueprint, context):
                return [{"kind": "analysis", "name": f"a-{context.event}",
                         "pipeline": "simpletestpipeline"}]

        return Single

    def apply_to(self, event, name="scan"):
        self.write("blueprint.yaml", BLUEPRINT.replace("name: scan", f"name: {name}"))
        entry = FakeEntryPoint("scan", self.single())
        with patch("asimov.strategies.entry_points", return_value=[entry]):
            apply_page("blueprint.yaml", event=event, ledger=self.ledger)

    def test_it_cannot_be_applied_to_another_subject(self):
        self.apply_to("Base")
        with self.assertRaisesRegex(StrategyError, "is for the subject 'Base'.*'Other'"):
            self.apply_to("Other")
        fresh = self.reopen().get_event("Other")[0]
        self.assertEqual([p.name for p in fresh.productions], [])

    def test_it_can_be_applied_to_the_same_subject_again(self):
        self.apply_to("Base")
        self.apply_to("Base")

    def test_a_different_name_is_a_different_group(self):
        self.apply_to("Base")
        self.apply_to("Other", name="scan-2")
        self.assertEqual(self.group("scan-2")["event"], "Other")
        self.assertEqual(self.group("scan")["event"], "Base")


class DryRunTests(GroupsCase):
    def test_a_dry_run_keeps_no_record_but_plans_it(self):
        plan = self.apply(dry_run=True)
        self.assertIsNone(self.group())
        self.assertNotIn(GROUPS_KEY, self.ledger.data)
        planned = [c.record for c in plan.changes if c.record.kind == "strategygroup"]
        self.assertEqual([r.target for r in planned], ["@project/scan"])

    def test_a_dry_run_of_what_is_unchanged_plans_no_record(self):
        self.apply()
        plan = self.apply(dry_run=True)
        self.assertEqual([c for c in plan.changes if c.record.kind == "strategygroup"], [])


class PluginInfoTests(unittest.TestCase):
    def test_the_package_which_provides_a_strategy(self):
        info = plugin_info("chain")
        self.assertEqual(info["name"], "asimov")
        self.assertNotEqual(info["version"], "unknown")

    def test_a_strategy_which_is_not_installed(self):
        self.assertEqual(plugin_info("nope"), {"name": "unknown", "version": "unknown"})

    def test_a_package_which_cannot_be_found_is_unknown(self):
        with patch("asimov.strategies.entry_points", return_value=[FakeEntryPoint("x", Scan)]):
            self.assertEqual(plugin_info("x"), {"name": "unknown", "version": "unknown"})


class DatabaseLedgerTests(GroupsCase):
    """The same, in a ledger that is a database, which merges what it saves."""

    def make_ledger(self):
        self.location = f"sqlite:///{os.path.join(self.root, 'ledger.db')}"
        ledger = DatabaseLedger(engine="sqlalchemy", location=self.location)
        ledger.db.create_tables()
        return ledger

    def reopen(self):
        return DatabaseLedger(engine="sqlalchemy", location=self.location)

    def test_the_record_is_kept(self):
        self.apply()
        group = self.group()
        self.assertEqual(group["subjects"], ["S1", "S2"])
        self.assertEqual(group["plugin"], {"name": "demo", "version": "1.0"})

    def test_an_option_which_is_left_out_is_gone(self):
        self.apply(BLUEPRINT + "  extra: 1\n  nested: {a: 1, b: 2}\n")
        self.assertEqual(self.group()["blueprint"]["strategy"]["nested"], {"a": 1, "b": 2})
        self.apply()
        strategy = self.group()["blueprint"]["strategy"]
        self.assertNotIn("extra", strategy)
        self.assertNotIn("nested", strategy)

    def test_adding_to_it_is_recorded(self):
        self.apply(version="1.0")
        self.apply(BLUEPRINT.replace("[S1, S2]", "[S1, S2, S3]"), version="2.0")
        self.assertEqual(self.group()["last extended with"]["version"], "2.0")
        self.assertEqual(self.group()["plugin"]["version"], "1.0")

    def test_the_name_is_unique(self):
        self.apply()
        entry = FakeEntryPoint("other", Scan)
        self.write("blueprint.yaml", BLUEPRINT.replace("type: scan", "type: other"))
        with patch("asimov.strategies.entry_points", return_value=[entry]):
            with self.assertRaises(StrategyError):
                apply_page("blueprint.yaml", ledger=self.ledger)

    def test_a_dry_run_keeps_nothing(self):
        self.apply(dry_run=True)
        self.assertIsNone(self.group())


if __name__ == "__main__":
    unittest.main()
