"""
Tests for labels on subjects, and the labellers which set them.
"""

import unittest
from unittest.mock import MagicMock

from asimov import actions, labellers
from asimov.analysis import SUBJECT_ONLY_KEYS
from asimov.event import Event
from asimov.labellers import Labeller, apply_labellers, apply_subject_labellers


class Plain(Labeller):
    """An analysis-only labeller, as every existing plugin is."""

    name = "plain"

    def label(self, analysis, context=None):
        return {"analysis only": True}


class Both(Labeller):
    name = "both"
    targets = ("analysis", "subject")

    def label(self, analysis, context=None):
        return {"seen": "analysis"}

    def label_subject(self, subject, context=None):
        return {"seen": "subject", "ready": 1}

    def should_label_subject(self, subject, context=None):
        return subject.name != "skipped"


class Target:
    def __init__(self, name):
        self.name = name
        self.meta = {}


class TestSubjectLabellers(unittest.TestCase):
    def setUp(self):
        self._saved = dict(labellers.LABELLER_REGISTRY)
        labellers.LABELLER_REGISTRY.clear()
        labellers.LABELLER_REGISTRY.update({"plain": Plain(), "both": Both()})
        self.addCleanup(self._restore)

    def _restore(self):
        labellers.LABELLER_REGISTRY.clear()
        labellers.LABELLER_REGISTRY.update(self._saved)

    def test_default_labeller_only_labels_analyses(self):
        self.assertEqual(Plain.targets, ("analysis",))
        subject = Target("S1")
        self.assertEqual(apply_subject_labellers(subject), {"seen": "subject", "ready": 1})
        self.assertNotIn("analysis only", subject.meta["labels"])

    def test_analysis_pass_skips_subject_only_hooks(self):
        analysis = Target("a1")
        apply_labellers(analysis)
        self.assertEqual(analysis.meta["labels"], {"analysis only": True, "seen": "analysis"})

    def test_should_label_subject(self):
        subject = Target("skipped")
        self.assertEqual(apply_subject_labellers(subject), {})

    def test_manual_subject_label_is_not_overwritten(self):
        subject = Target("S1")
        subject.meta = {"labels": {"ready": 5}, "manual labels": ["ready"]}
        apply_subject_labellers(subject)
        self.assertEqual(subject.meta["labels"], {"ready": 5, "seen": "subject"})

    def test_a_failing_labeller_does_not_stop_the_others(self):
        class Broken(Labeller):
            name = "broken"
            targets = ("subject",)

            def label(self, analysis, context=None):
                return {}

            def label_subject(self, subject, context=None):
                raise RuntimeError("no")

        labellers.LABELLER_REGISTRY["broken"] = Broken()
        self.assertEqual(apply_subject_labellers(Target("S1"))["ready"], 1)


class TestSubjectProperties(unittest.TestCase):
    def test_labels_is_a_copy(self):
        event = Event.__new__(Event)
        event.meta = {"labels": {"a": 1}, "manual labels": ["a"]}
        event.labels["a"] = 2
        event.manual_labels.append("b")
        self.assertEqual(event.labels, {"a": 1})
        self.assertEqual(event.manual_labels, ["a"])

    def test_no_labels(self):
        event = Event.__new__(Event)
        event.meta = {}
        self.assertEqual(event.labels, {})
        self.assertEqual(event.manual_labels, [])

    def test_subject_only_keys(self):
        self.assertEqual(set(SUBJECT_ONLY_KEYS), {"labels", "manual labels"})


class TestActionsOnSubjects(unittest.TestCase):
    def test_target_of_a_subject_is_its_name(self):
        subject = Target("GW150914")
        self.assertEqual(actions._target(subject), "GW150914")
        analysis = Target("bilby")
        analysis.event = subject
        self.assertEqual(actions._target(analysis), "GW150914/bilby")
        self.assertIs(actions._event(analysis), subject)
        self.assertIs(actions._event(subject), subject)

    def test_add_and_remove(self):
        subject = Target("GW150914")
        ledger = MagicMock()
        record = actions.add_label(ledger, subject, "ready", 3)
        self.assertEqual(subject.meta["labels"], {"ready": 3})
        self.assertEqual(subject.meta["manual labels"], ["ready"])
        ledger.update_event.assert_called_with(subject)
        actions.remove_label(ledger, subject, "ready")
        self.assertEqual(subject.meta["labels"], {})
        with self.assertRaises(actions.ActionError):
            actions.remove_label(ledger, subject, "ready")
        self.assertIsNotNone(record)


if __name__ == "__main__":
    unittest.main()
