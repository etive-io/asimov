"""
Regression tests for a specific class of bug: Event/Analysis/Production
objects get reconstructed fresh from the ledger on almost every read
(events/project_analyses were previously uncached properties, and even
now a cache can be invalidated between two reads). Without proper
__eq__/__hash__, two independently-constructed objects representing the
same underlying entity are never equal to each other - which silently
breaks any code comparing/combining results across two separate reads,
and for Event specifically crashed outright (unhashable).

See also: tests/test_project.py (the exact NoSuchPathError regression
this chain of bugs produced) and tests/test_database.py (ledger/database
plumbing in general).
"""

import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from asimov.event import Event
from asimov.analysis import Analysis, ProjectAnalysis
from asimov.ledger import YAMLLedger, DatabaseLedger
from asimov.git import EventRepo


def _all_subclasses(cls):
    seen = {cls}
    stack = [cls]
    while stack:
        parent = stack.pop()
        for child in parent.__subclasses__():
            if child not in seen:
                seen.add(child)
                stack.append(child)
    return seen


class HashableModelTests(unittest.TestCase):
    """
    Structural guard against the general footgun, not just today's
    instances of it: in Python, defining __eq__ on a class without also
    defining __hash__ makes that class's instances unhashable
    (`__hash__` is implicitly set to None). This is exactly what
    happened to Event, and it's easy to reintroduce - either on these
    classes directly, or on a new subclass added later.
    """

    def test_event_is_hashable(self):
        self.assertIsNotNone(
            Event.__hash__,
            "Event defines __eq__ without __hash__, making it unhashable",
        )

    def test_analysis_family_is_hashable(self):
        for cls in _all_subclasses(Analysis) | {Analysis}:
            with self.subTest(cls=cls.__name__):
                self.assertIsNotNone(
                    cls.__hash__,
                    f"{cls.__name__} defines __eq__ without __hash__, making it unhashable",
                )


class EventRepoLazinessTests(unittest.TestCase):
    """
    Direct regression test for the original crash: constructing an
    EventRepo (which every Event does for its `repository`) used to open
    a real git.Repo(directory) eagerly, requiring the checkout to already
    exist at a resolvable path. Since Event objects get reconstructed on
    essentially every ledger read, this meant just listing events could
    fail if the working directory wasn't what it was when the checkout
    was created - which is exactly what happened calling
    Project.get_event() outside a `with project:` block.
    """

    def test_construction_does_not_touch_git(self):
        # A path that doesn't exist and never will for this test -
        # construction itself must not care.
        repo = EventRepo("/nonexistent/path/for/this/test")
        self.assertEqual(repo.directory, "/nonexistent/path/for/this/test")

    def test_repo_property_does_the_real_work_lazily(self):
        repo = EventRepo("/nonexistent/path/for/this/test")
        with self.assertRaises(Exception):
            # Only actually touching git should fail.
            repo.repo


class EventEqualityTests(unittest.TestCase):
    def test_events_with_same_name_are_equal_and_hash_equal(self):
        e1 = Event(name="GW150914")
        e2 = Event(name="GW150914")
        self.assertEqual(e1, e2)
        self.assertEqual(hash(e1), hash(e2))
        # The whole point: two independent reconstructions dedupe in a set,
        # and set difference against a second independent reconstruction
        # actually removes matching entries.
        self.assertEqual(len({e1, e2}), 1)
        self.assertEqual({e1, e2} - {e2}, set())

    def test_events_with_different_names_are_not_equal(self):
        e1 = Event(name="GW150914")
        e2 = Event(name="GW151226")
        self.assertNotEqual(e1, e2)
        self.assertEqual(len({e1, e2}), 2)


class ProjectAnalysisEqualityTests(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_ledger.db")
        self.config_patcher = patch("asimov.database.config")
        mock_config = self.config_patcher.start()
        mock_config.get.side_effect = lambda section, key, fallback=None: {
            ("ledger", "engine"): "sqlite",
            ("ledger", "location"): self.db_path,
        }.get((section, key), fallback)
        self.ledger = DatabaseLedger(engine="sqlite")
        self.ledger.db.create_tables()

    def tearDown(self):
        self.config_patcher.stop()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_project_analyses_with_same_name_are_equal_and_hash_equal(self):
        pa1 = ProjectAnalysis(
            name="combined", pipeline="simpletestpipeline", ledger=self.ledger, subjects=[]
        )
        pa2 = ProjectAnalysis(
            name="combined", pipeline="simpletestpipeline", ledger=self.ledger, subjects=[]
        )
        self.assertEqual(pa1, pa2)
        self.assertEqual(hash(pa1), hash(pa2))
        self.assertEqual(len({pa1, pa2}), 1)

    def test_project_analyses_with_different_names_are_not_equal(self):
        pa1 = ProjectAnalysis(
            name="combined", pipeline="simpletestpipeline", ledger=self.ledger, subjects=[]
        )
        pa2 = ProjectAnalysis(
            name="other", pipeline="simpletestpipeline", ledger=self.ledger, subjects=[]
        )
        self.assertNotEqual(pa1, pa2)

    def test_regression_set_difference_correctly_excludes_completed(self):
        """
        Direct regression test for the bug found in cli/monitor.py:
        `all_analyses - complete`, where both sides come from two
        independent `ledger.project_analyses` reads, silently never
        removed anything because the two reads produced non-equal
        objects. With real equality (and caching returning the same
        objects across reads that don't intervene with a write), this
        must actually work.
        """
        finished = ProjectAnalysis(
            name="finished-one", pipeline="simpletestpipeline", ledger=self.ledger, subjects=[]
        )
        finished.status = "finished"
        waiting = ProjectAnalysis(
            name="waiting-one", pipeline="simpletestpipeline", ledger=self.ledger, subjects=[]
        )
        waiting.status = "wait"
        self.ledger.add_analysis(finished)
        self.ledger.add_analysis(waiting)

        all_analyses = set(self.ledger.project_analyses)
        complete = {
            analysis
            for analysis in self.ledger.project_analyses
            if analysis.status in {"finished", "uploaded", "processing"}
        }
        others = all_analyses - complete

        self.assertEqual({a.name for a in others}, {"waiting-one"})

    def test_regression_subjects_comparison_does_not_crash(self):
        """
        Direct regression test for the crash found in cli/review.py:
        `set(analysis.subjects) == set(subjects)` raised TypeError
        outright, because ProjectAnalysis.subjects returns a list of
        Event objects (correctly, by design - see
        asimov/analysis.py's resolve_analyses(), which relies on this),
        and Event was unhashable. review.py was the one place written as
        though .subjects returned plain name strings; it should compare
        by .name instead of relying on object equality/hashing at all.
        """
        self.ledger.add_event(Event(name="GW150914"))
        self.ledger.add_event(Event(name="GW151226"))
        analysis = ProjectAnalysis(
            name="combined",
            pipeline="simpletestpipeline",
            ledger=self.ledger,
            subjects=["GW150914", "GW151226"],
        )

        # This is what cli/review.py now does; it used to do
        # `set(analysis.subjects)`, which raised TypeError.
        subject_names = {s.name for s in analysis.subjects}
        self.assertEqual(subject_names, {"GW150914", "GW151226"})
        self.assertEqual(" ".join(sorted(subject_names)), "GW150914 GW151226")


class LedgerCachingTests(unittest.TestCase):
    """
    events/project_analyses used to reconstruct everything from scratch
    on every access (DatabaseLedger always did; YAMLLedger's `_all_events`
    was cached once at __init__ and then simply went stale after any
    write). Both are wrong in different ways - the fix needs to be
    genuinely correct, not just consistent with prior behaviour.
    """

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_ledger.db")
        self.config_patcher = patch("asimov.database.config")
        mock_config = self.config_patcher.start()
        mock_config.get.side_effect = lambda section, key, fallback=None: {
            ("ledger", "engine"): "sqlite",
            ("ledger", "location"): self.db_path,
        }.get((section, key), fallback)
        self.ledger = DatabaseLedger(engine="sqlite")
        self.ledger.db.create_tables()

    def tearDown(self):
        self.config_patcher.stop()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_events_is_stable_across_repeated_reads(self):
        self.ledger.add_event(Event(name="GW150914"))
        first = self.ledger.events
        second = self.ledger.events
        self.assertEqual(first, second)

    def test_events_reflects_a_write_made_in_between(self):
        self.ledger.add_event(Event(name="GW150914"))
        self.assertEqual({e.name for e in self.ledger.events}, {"GW150914"})

        self.ledger.add_event(Event(name="GW151226"))
        self.assertEqual(
            {e.name for e in self.ledger.events}, {"GW150914", "GW151226"}
        )

    def test_project_analyses_reflects_a_write_made_in_between(self):
        self.assertEqual(self.ledger.project_analyses, [])
        self.ledger.add_analysis(
            ProjectAnalysis(
                name="combined", pipeline="simpletestpipeline", ledger=self.ledger, subjects=[]
            )
        )
        self.assertEqual({a.name for a in self.ledger.project_analyses}, {"combined"})


class YAMLLedgerReadYourOwnWritesTests(unittest.TestCase):
    """
    Direct regression test for the specific staleness this investigation
    turned up: inside a single `with project:` block, get_event() right
    after add_subject() returned the event list from *before* the add,
    because YAMLLedger's `_all_events` was cached once at __init__ and
    never invalidated by writes.
    """

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.location = os.path.join(self.test_dir, "ledger.yml")
        with open(self.location, "w") as f:
            f.write("events: []\nproject analyses: []\n")
        self.ledger = YAMLLedger(self.location)

        # save() needs [project] root set, which real project
        # initialization provides; this fixture bypasses that. Mutate the
        # exact config object asimov.ledger.save() will read, rather than
        # a fresh `from asimov import config` - some other test files
        # (e.g. test_analysis.py) call importlib.reload(asimov) without
        # reloading asimov.ledger, which leaves asimov.ledger holding a
        # stale config reference for the rest of the process while a
        # fresh import elsewhere would get the new object.
        import asimov.ledger
        global_config = asimov.ledger.config
        if not global_config.has_section("project"):
            global_config.add_section("project")
        self._previous_root = global_config.get("project", "root", fallback=None)
        global_config.set("project", "root", self.test_dir)

    def tearDown(self):
        import asimov.ledger
        global_config = asimov.ledger.config
        if self._previous_root is None:
            global_config.remove_option("project", "root")
        else:
            global_config.set("project", "root", self._previous_root)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_get_event_sees_a_subject_added_moments_ago(self):
        self.assertEqual(self.ledger.get_event(), [])
        self.ledger.add_subject(Event(name="GW150914"))
        self.assertEqual(
            {e.name for e in self.ledger.get_event()}, {"GW150914"}
        )


if __name__ == "__main__":
    unittest.main()
