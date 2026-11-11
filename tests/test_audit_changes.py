"""
Tests for recording every change to the ledger in the audit trail (#143).
"""

import os
import shutil
import tempfile
import unittest

from asimov.audit import MAX_CHANGES, changes
from asimov.cli.application import apply_page
from asimov.cli.project import make_project
from asimov.context import ProjectContext
from asimov.principal import Principal, acting_as

DATA = os.path.join(os.path.dirname(__file__), "test_data")
ANALYSIS = "kind: analysis\nname: a1\nevent: S000000\npipeline: simpletestpipeline\nstatus: ready\n"


class TestChanges(unittest.TestCase):
    def test_named_lists_are_compared_by_name(self):
        before = {"productions": [{"a1": {"status": "ready"}}, {"a2": {"status": "ready"}}]}
        after = {"productions": [{"a2": {"status": "ready"}}, {"a1": {"status": "running"}}]}
        self.assertEqual(changes(before, after), {"productions.a1.status": ["ready", "running"]})

    def test_added_and_removed_fields(self):
        self.assertEqual(changes({"a": 1}, {"b": 2}), {"a": ["1", None], "b": [None, "2"]})
        self.assertEqual(changes(None, None), {})

    def test_large_edits_are_cut_short(self):
        found = changes({}, {f"k{i}": "x" * 500 for i in range(200)})
        self.assertEqual(len(found), MAX_CHANGES + 1)
        self.assertLessEqual(len(found["k0"][1]), 200)


class ChangeRecordingCase(unittest.TestCase):
    engine = "yamlfile"

    def setUp(self):
        self.origin = os.getcwd()
        self.addCleanup(os.chdir, self.origin)
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        root = os.path.join(self.dir, "p")
        make_project(name="p", root=root, engine=self.engine)
        os.chdir(self.origin)
        self.context = ProjectContext.from_directory(root)
        page = os.path.join(self.dir, "a1.yaml")
        with open(page, "w") as handle:
            handle.write(ANALYSIS)
        with self.context.activate():
            apply_page(os.path.join(DATA, "testing_pe.yaml"), ledger=self.context.ledger)
            apply_page(os.path.join(DATA, "test_event.yaml"), ledger=self.context.ledger)
            apply_page(page, ledger=self.context.ledger)

    @property
    def ledger(self):
        return self.context.ledger

    def event(self):
        return self.ledger.get_event("S000000")[0]

    def records(self):
        return [r for r in self.ledger.audit_log() if r.action == "change"]

    def set_status(self, status):
        event = self.event()
        next(a for a in event.productions if a.name == "a1").status = status
        self.ledger.update_event(event)

    def test_a_status_change_is_recorded_with_who_made_it(self):
        with self.context.activate(), acting_as(Principal.monitor()):
            self.set_status("running")
            records = self.records()
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual((record.kind, record.target, record.outcome), ("event", "S000000", "changed"))
        self.assertEqual(record.principal["kind"], "monitor")
        status = [v for k, v in record.content["changes"].items() if k.endswith("status")]
        self.assertIn(["ready", "running"], status)

    def test_a_write_which_changes_nothing_is_not_recorded(self):
        with self.context.activate():
            # The database ledger stores the project's defaults in an event the
            # first time it is written back, which is a real change; after
            # that, writing it unchanged records nothing.
            self.ledger.update_event(self.event())
            already = len(self.records())
            self.ledger.update_event(self.event())
            self.assertEqual(len(self.records()), already)
            self.assertLessEqual(already, 0 if self.engine == "yamlfile" else 1)

    def test_an_explicit_record_in_the_same_transaction_covers_it(self):
        from asimov.audit import append_audit, new_record

        with self.context.activate():
            with self.ledger.transaction():
                self.set_status("running")
                append_audit(self.ledger, new_record("review", "review", "S000000/a1"))
            self.assertEqual(self.records(), [])

    def test_changes_in_a_transaction_are_recorded_when_it_ends_or_not_at_all(self):
        with self.context.activate():
            with self.ledger.transaction():
                self.set_status("running")
            self.assertEqual(len(self.records()), 1)
            with self.assertRaises(RuntimeError):
                with self.ledger.transaction():
                    self.set_status("stuck")
                    raise RuntimeError("no")
            self.assertEqual(len(self.records()), 1)

    def test_deleting_is_recorded(self):
        with self.context.activate():
            self.ledger.delete_analysis("S000000", "a1")
            records = self.records()
        self.assertEqual([(r.target, r.outcome) for r in records], [("S000000/a1", "deleted")])

    def test_applying_a_blueprint_is_not_recorded_twice(self):
        with self.context.activate():
            self.assertEqual(self.records(), [])
            self.assertTrue(self.ledger.audit_log(action="apply"))


class ChangeRecordingSQLite(ChangeRecordingCase):
    engine = "sqlite"


if __name__ == "__main__":
    unittest.main()
