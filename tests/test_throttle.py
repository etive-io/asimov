"""
Tests for submission throttling.
"""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from asimov.throttle import (
    SubmissionThrottle,
    count_active,
    is_transient_submit_error,
    submit_with_backoff,
)


def _event(*statuses):
    return SimpleNamespace(productions=[SimpleNamespace(status=s) for s in statuses])


class FakeLedger:
    def __init__(self, event_statuses, project_statuses=()):
        self._events = [_event(*s) for s in event_statuses]
        self.project_analyses = [SimpleNamespace(status=s) for s in project_statuses]

    def get_event(self, event=None):
        return self._events


class TestBudget(unittest.TestCase):
    def test_unlimited_by_default(self):
        throttle = SubmissionThrottle()
        self.assertFalse(throttle.limited)
        self.assertIsNone(throttle.remaining)
        for _ in range(1000):
            self.assertTrue(throttle.can_submit())
            throttle.record_submission()

    def test_non_positive_means_unlimited(self):
        throttle = SubmissionThrottle(max_queued=0, max_per_pass=-1)
        self.assertFalse(throttle.limited)

    def test_max_queued_accounts_for_active(self):
        throttle = SubmissionThrottle(max_queued=200, active=198)
        self.assertEqual(throttle.remaining, 2)
        throttle.record_submission()
        throttle.record_submission()
        self.assertFalse(throttle.can_submit())
        self.assertEqual(throttle.remaining, 0)

    def test_already_over_the_limit(self):
        throttle = SubmissionThrottle(max_queued=200, active=250)
        self.assertEqual(throttle.remaining, 0)
        self.assertFalse(throttle.can_submit())

    def test_per_pass_limit(self):
        throttle = SubmissionThrottle(max_per_pass=3)
        for _ in range(3):
            self.assertTrue(throttle.can_submit())
            throttle.record_submission()
        self.assertFalse(throttle.can_submit())

    def test_tightest_limit_wins(self):
        throttle = SubmissionThrottle(max_queued=10, max_per_pass=3, active=9)
        self.assertEqual(throttle.remaining, 1)
        throttle = SubmissionThrottle(max_queued=100, max_per_pass=3, active=0)
        self.assertEqual(throttle.remaining, 3)

    def test_halt_stops_submissions(self):
        throttle = SubmissionThrottle()
        throttle.halt()
        self.assertFalse(throttle.can_submit())

    def test_interval_sleeps_between_but_not_after_last(self):
        sleeps = []
        throttle = SubmissionThrottle(max_per_pass=2, interval=5, sleep=sleeps.append)
        throttle.record_submission()
        throttle.record_submission()
        self.assertEqual(sleeps, [5.0])

    def test_summary(self):
        throttle = SubmissionThrottle(max_per_pass=1)
        throttle.record_submission()
        throttle.defer("a/b")
        self.assertIn("Submitted 1", throttle.summary())
        self.assertIn("deferred 1", throttle.summary())
        self.assertIn("queue limit", throttle.summary())
        throttle.halt()
        self.assertIn("scheduler busy", throttle.summary())


class TestConfig(unittest.TestCase):
    def _config(self, **values):
        def get(section, key, fallback=None):
            if section != "scheduler":
                return fallback
            return values.get(key, fallback)

        return patch("asimov.throttle.config", new=SimpleNamespace(get=get))

    def test_defaults_are_unlimited(self):
        with self._config():
            throttle = SubmissionThrottle.from_config(FakeLedger([]))
        self.assertFalse(throttle.limited)

    def test_reads_limits_and_counts_active(self):
        ledger = FakeLedger(
            [["running", "finished", "ready"], ["processing", "stuck"]],
            ["running", "ready"],
        )
        with self._config(max_queued="200", submit_interval="1.5"):
            throttle = SubmissionThrottle.from_config(ledger)
        self.assertEqual(throttle.max_queued, 200)
        self.assertEqual(throttle.interval, 1.5)
        self.assertEqual(throttle.active, 3)
        self.assertEqual(throttle.remaining, 197)

    def test_cli_override_beats_config(self):
        with self._config(max_submit_per_pass="50"):
            throttle = SubmissionThrottle.from_config(FakeLedger([]), max_per_pass=5)
        self.assertEqual(throttle.max_per_pass, 5)

    def test_ledger_not_read_without_max_queued(self):
        class Boom:
            def get_event(self, event=None):
                raise AssertionError("ledger should not be read")

        with self._config(max_submit_per_pass="5"):
            SubmissionThrottle.from_config(Boom())

    def test_invalid_values_are_ignored(self):
        with self._config(max_queued="lots", submit_interval="soon"):
            throttle = SubmissionThrottle.from_config(FakeLedger([]))
        self.assertFalse(throttle.limited)
        self.assertEqual(throttle.interval, 0)


class TestCountActive(unittest.TestCase):
    def test_counts_only_active_states(self):
        ledger = FakeLedger(
            [["Running", "ready", "stuck", "finished"], ["processing"]], ["running"]
        )
        self.assertEqual(count_active(ledger), 3)


class TestTransient(unittest.TestCase):
    def test_classification(self):
        self.assertTrue(is_transient_submit_error(TimeoutError()))
        self.assertTrue(is_transient_submit_error(RuntimeError("Too many jobs")))
        self.assertFalse(is_transient_submit_error(ValueError("bad ini file")))

    def test_cause_is_inspected(self):
        try:
            try:
                raise ConnectionError("down")
            except ConnectionError as inner:
                raise RuntimeError("wrapped") from inner
        except RuntimeError as outer:
            self.assertTrue(is_transient_submit_error(outer))


class TestBackoff(unittest.TestCase):
    def test_retries_then_succeeds(self):
        calls, sleeps = [], []

        def submit():
            calls.append(1)
            if len(calls) < 3:
                raise TimeoutError("busy")
            return 42

        self.assertEqual(submit_with_backoff(submit, retries=2, sleep=sleeps.append), 42)
        self.assertEqual(sleeps, [2.0, 4.0])

    def test_gives_up_after_retries(self):
        def submit():
            raise TimeoutError("busy")

        with self.assertRaises(TimeoutError):
            submit_with_backoff(submit, retries=1, sleep=lambda s: None)

    def test_permanent_errors_not_retried(self):
        calls = []

        def submit():
            calls.append(1)
            raise ValueError("bad ini file")

        with self.assertRaises(ValueError):
            submit_with_backoff(submit, retries=3, sleep=lambda s: None)
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
