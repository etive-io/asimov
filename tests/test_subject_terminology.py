"""
Tests for the event -> subject terminology generalization (issue #151).

Blueprints using `kind: subject` should behave identically to `kind: event`,
and the ledger should expose `get_subject()` as an alias of `get_event()`.
"""
import os
import shutil
import unittest

from asimov.event import Event, Subject
from asimov.ledger import YAMLLedger
from asimov.cli.project import make_project
from asimov.cli.application import apply_page

SUBJECT_BLUEPRINT = """
kind: subject
name: J1909-3744
"""

EVENT_BLUEPRINT = """
kind: event
name: GW150914_095045
"""


class SubjectTerminologyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cwd = os.getcwd()

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls.cwd)

    def setUp(self):
        os.makedirs(f"{self.cwd}/tests/tmp/subject_terminology_project")
        os.chdir(f"{self.cwd}/tests/tmp/subject_terminology_project")
        make_project(
            name="Test project",
            root=f"{self.cwd}/tests/tmp/subject_terminology_project",
        )
        self.ledger = YAMLLedger(".asimov/ledger.yml")

    def tearDown(self):
        del self.ledger
        os.chdir(self.cwd)
        shutil.rmtree(f"{self.cwd}/tests/tmp/subject_terminology_project")

    def _apply(self, contents, name):
        path = f"tests/tmp/subject_terminology_project/{name}.yaml"
        with open(f"{self.cwd}/{path}", "w") as blueprint_file:
            blueprint_file.write(contents)
        apply_page(file=f"{self.cwd}/{path}", ledger=self.ledger)

    def test_kind_subject_is_accepted_by_apply_page(self):
        """`kind: subject` should be treated the same as `kind: event`."""
        self._apply(SUBJECT_BLUEPRINT, "subject")
        self.assertIn("J1909-3744", self.ledger.events)

    def test_get_subject_matches_get_event(self):
        """`get_subject` and `get_event` should return the same subject."""
        self._apply(EVENT_BLUEPRINT, "event")
        by_event = self.ledger.get_event("GW150914_095045")[0]
        by_subject = self.ledger.get_subject("GW150914_095045")[0]
        self.assertEqual(by_event.name, by_subject.name)

    def test_get_subject_with_no_argument_returns_all_subjects(self):
        self._apply(EVENT_BLUEPRINT, "event")
        self._apply(SUBJECT_BLUEPRINT, "subject")
        # Reload so the ledger's cached "all subjects" list picks up both additions.
        reloaded = YAMLLedger(".asimov/ledger.yml")
        all_via_subject = {subject.name for subject in reloaded.get_subject()}
        all_via_event = {event.name for event in reloaded.get_event()}
        self.assertEqual(all_via_subject, all_via_event)
        self.assertEqual(all_via_subject, {"GW150914_095045", "J1909-3744"})

    def test_subject_is_an_alias_for_event(self):
        self.assertIs(Subject, Event)
