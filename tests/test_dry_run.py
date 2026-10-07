"""
Tests for ``asimov apply --dry-run`` (#142).
"""

import hashlib
import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

import click
from click.testing import CliRunner

from asimov import telemetry
from asimov.cli import application
from asimov.cli.application import apply_page
from asimov.cli.project import make_project
from asimov.context import ProjectContext
from asimov.ledger import DatabaseLedger
from asimov.preview import ApplyPlan, changed_paths, current_plan, is_dry_run
from asimov.principal import Principal, acting_as

DATA = os.path.join(os.path.dirname(__file__), "test_data")
BLUEPRINTS = os.path.join(os.path.dirname(__file__), "test_blueprints")
ENGINES = ("yamlfile", "sqlite")

CONFIGURATION = "kind: configuration\nquality:\n  minimum frequency:\n    H1: {value}\n"
EVENT_UPDATE = (
    "kind: event\nname: S000000\nevent time: 901\npriors:\n  mass ratio:\n    minimum: 0.2\n"
)
PROJECT_ANALYSIS = (
    "kind: projectanalysis\nname: pa1\npipeline: simpletestpipeline\nsubjects: [S000000]\n"
    "analyses:\n- - 'pipeline: simpletestpipeline'\nstatus: ready\n"
)
BUNDLE = (
    "kind: analysisbundle\nname: b\nanalyses:\n"
    "- name: one\n  pipeline: simpletestpipeline\n  status: ready\n"
    "- name: two\n  pipeline: simpletestpipeline\n  status: ready\n"
)
POSTPROCESSING = "kind: postprocessing\nname: stage-one\npipeline: simpletestpipeline\n"
EVENT_WITH_URL = (
    "kind: event\nname: S000009\nevent time: 900\n"
    "repository: https://example.invalid/events/S000009.git\n"
)


class DryRunTestCase(unittest.TestCase):
    def setUp(self):
        self.origin = os.getcwd()
        self.dirs = []
        self.addCleanup(os.chdir, self.origin)

    def tearDown(self):
        os.chdir(self.origin)
        for path in self.dirs:
            shutil.rmtree(path, ignore_errors=True)

    def scratch(self):
        path = tempfile.mkdtemp()
        self.dirs.append(path)
        return path

    def context(self, engine):
        """A project with a configuration and an event S000000 already applied."""
        root = self.scratch()
        make_project(name="T", root=root, engine=engine)
        os.chdir(self.origin)
        ctx = ProjectContext.from_directory(root)
        self.addCleanup(lambda: getattr(ctx.ledger, "close", lambda: None)())
        with ctx.activate():
            apply_page(os.path.join(DATA, "testing_pe.yaml"), ledger=ctx.ledger)
            apply_page(os.path.join(DATA, "test_event.yaml"), ledger=ctx.ledger)
            apply_page(self.text(CONFIGURATION.format(value=20)), ledger=ctx.ledger)
        return ctx

    def text(self, text):
        path = os.path.join(self.scratch(), "blueprint.yaml")
        with open(path, "w") as f:
            f.write(text)
        return path

    def tree(self, ctx):
        """Every directory and file (by content) in the project."""
        found = {}
        for directory, _, files in os.walk(ctx.root):
            found[directory] = None
            for name in files:
                if name.endswith(".lock"):
                    continue
                with open(os.path.join(directory, name), "rb") as f:
                    found[os.path.join(directory, name)] = hashlib.md5(f.read()).hexdigest()
        return found

    def state(self, ctx):
        """What the ledger holds, and the disk, for comparing before and after."""
        ledger = ctx.ledger
        with ctx.activate():
            events = {
                e.name: sorted(p.name for p in e.productions) for e in ledger.get_event()
            }
            analyses = sorted(a.name for a in ledger.project_analyses)
        return {
            "events": events,
            "project analyses": analyses,
            "data": json.dumps(ledger.data, sort_keys=True, default=str),
            "audit": [r.to_dict() for r in ledger.audit_log()],
            "tree": self.tree(ctx),
        }

    def dry(self, ctx, path, **kwargs):
        with ctx.activate():
            return apply_page(path, ledger=ctx.ledger, dry_run=True, **kwargs)

    def real(self, ctx, path, **kwargs):
        with ctx.activate():
            return apply_page(path, ledger=ctx.ledger, **kwargs)


class TestNothingIsWritten(DryRunTestCase):
    """The point of a dry run: it leaves everything as it found it."""

    def blueprints(self):
        return {
            "an analysis": (
                os.path.join(BLUEPRINTS, "simple_test_pipeline.yaml"),
                {"event": "S000000"},
            ),
            "a new event": (os.path.join(BLUEPRINTS, "second_event.yaml"), {}),
            "an event update": (self.text(EVENT_UPDATE), {"update_page": True}),
            "a configuration": (self.text(CONFIGURATION.format(value=30)), {}),
            "a project analysis": (self.text(PROJECT_ANALYSIS), {}),
            "a bundle": (self.text(BUNDLE), {"event": "S000000"}),
            "an event with a repository to clone": (self.text(EVENT_WITH_URL), {}),
        }

    def test_the_ledger_the_disk_and_the_audit_log_are_unchanged(self):
        for engine in ENGINES:
            ctx = self.context(engine)
            for label, (path, kwargs) in self.blueprints().items():
                with self.subTest(engine=engine, blueprint=label):
                    before = self.state(ctx)
                    plan = self.dry(ctx, path, **kwargs)
                    self.assertEqual(self.state(ctx), before)
                    self.assertTrue(plan.changes or plan.refused, label)

    def test_postprocessing_leaves_a_yaml_ledger_unchanged(self):
        ctx = self.context("yamlfile")
        before = self.state(ctx)
        plan = self.dry(ctx, self.text(POSTPROCESSING))
        self.assertEqual(self.state(ctx), before)
        self.assertEqual([c.record.kind for c in plan.changes], ["postprocessing"])

    def test_nothing_is_cloned(self):
        for engine in ENGINES:
            with self.subTest(engine=engine):
                ctx = self.context(engine)
                with patch("git.Repo.clone_from", side_effect=AssertionError("cloned")):
                    plan = self.dry(ctx, self.text(EVENT_WITH_URL))
                self.assertEqual([c.record.target for c in plan.changes], ["S000009"])

    def test_nothing_is_said(self):
        ctx = self.context("yamlfile")
        runner = CliRunner()
        with runner.isolation() as (out, _err, *_):
            self.dry(ctx, os.path.join(BLUEPRINTS, "simple_test_pipeline.yaml"), event="S000000")
            self.dry(ctx, os.path.join(DATA, "test_event.yaml"))
            self.assertEqual(out.getvalue(), b"")

    def test_the_audit_log_and_telemetry_sinks_get_nothing(self):
        received = []

        class Sink(telemetry.TelemetrySink):
            @property
            def name(self):
                return "fake"

            def emit(self, event):
                received.append(event)

        telemetry.register_telemetry_sink(Sink())
        self.addCleanup(telemetry.TELEMETRY_SINK_REGISTRY.pop, "fake", None)
        for engine in ENGINES:
            with self.subTest(engine=engine):
                received.clear()
                ctx = self.context(engine)
                ctx.ledger.data.setdefault("hooks", {})["telemetry"] = {"fake": {}}
                before = len(ctx.ledger.audit_log())
                self.dry(
                    ctx, os.path.join(BLUEPRINTS, "simple_test_pipeline.yaml"), event="S000000"
                )
                self.assertEqual(len(ctx.ledger.audit_log()), before)
                self.assertEqual(received, [])

    def test_a_real_apply_still_works_afterwards(self):
        for engine in ENGINES:
            with self.subTest(engine=engine):
                ctx = self.context(engine)
                path = os.path.join(BLUEPRINTS, "simple_test_pipeline.yaml")
                self.dry(ctx, path, event="S000000")
                self.real(ctx, path, event="S000000")
                with ctx.activate():
                    names = [p.name for p in ctx.ledger.get_event("S000000")[0].productions]
                self.assertEqual(names, ["test-simple-pipeline"])
                self.assertTrue(
                    os.path.isdir(os.path.join(ctx.root, "working", "S000000"))
                )

    def test_the_directories_a_real_apply_makes_are_not_made_by_a_dry_run(self):
        ctx = self.context("sqlite")
        self.dry(ctx, os.path.join(BLUEPRINTS, "second_event.yaml"))
        self.assertFalse(os.path.exists(os.path.join(ctx.root, "working", "GW151226_033853")))
        self.assertFalse(os.path.exists(os.path.join(ctx.root, "checkouts", "GW151226_033853")))
        self.real(ctx, os.path.join(BLUEPRINTS, "second_event.yaml"))
        self.assertTrue(os.path.isdir(os.path.join(ctx.root, "working", "GW151226_033853")))


class TestThePlanIsWhatWouldHappen(DryRunTestCase):
    """What a dry run says is what applying then does."""

    def fingerprint(self, record):
        return (
            record.action,
            record.kind,
            record.target,
            record.outcome,
            record.content,
            record.content_hash,
            record.principal,
        )

    def check(self, engine, path, **kwargs):
        ctx = self.context(engine)
        with acting_as(Principal.agent("sess", acting_for=Principal.person("dw"))):
            plan = self.dry(ctx, path, **kwargs)
            before = len(ctx.ledger.audit_log())
            self.real(ctx, path, **kwargs)
        written = ctx.ledger.audit_log()[before:]
        self.assertEqual(
            [self.fingerprint(c.record) for c in plan.changes],
            [self.fingerprint(r) for r in written],
        )
        self.assertTrue(written)
        return plan

    def test_an_analysis(self):
        for engine in ENGINES:
            with self.subTest(engine=engine):
                plan = self.check(
                    engine, os.path.join(BLUEPRINTS, "simple_test_pipeline.yaml"), event="S000000"
                )
                self.assertEqual(plan.changes[0].record.target, "S000000/test-simple-pipeline")

    def test_a_new_event(self):
        for engine in ENGINES:
            with self.subTest(engine=engine):
                self.check(engine, os.path.join(BLUEPRINTS, "second_event.yaml"))

    def test_an_event_update(self):
        for engine in ENGINES:
            with self.subTest(engine=engine):
                plan = self.check(engine, self.text(EVENT_UPDATE), update_page=True)
                self.assertEqual(plan.changes[0].record.outcome, "updated")

    def test_a_configuration(self):
        for engine in ENGINES:
            with self.subTest(engine=engine):
                self.check(engine, self.text(CONFIGURATION.format(value=30)))

    def test_a_project_analysis(self):
        for engine in ENGINES:
            with self.subTest(engine=engine):
                self.check(engine, self.text(PROJECT_ANALYSIS))

    def test_a_bundle_gives_one_change_per_analysis(self):
        for engine in ENGINES:
            with self.subTest(engine=engine):
                plan = self.check(engine, self.text(BUNDLE), event="S000000")
                self.assertEqual(
                    [c.record.target for c in plan.changes], ["S000000/one", "S000000/two"]
                )

    def test_postprocessing(self):
        self.check("yamlfile", self.text(POSTPROCESSING))

    def test_a_blueprint_of_several_documents_gives_every_change_in_order(self):
        text = (
            CONFIGURATION.format(value=40)
            + "---\n"
            + "kind: event\nname: S000002\nevent time: 1\n"
            + "---\n"
            + "kind: event\nname: S000003\nevent time: 2\n"
        )
        for engine in ENGINES:
            with self.subTest(engine=engine):
                plan = self.check(engine, self.text(text))
                self.assertEqual(
                    [(c.record.kind, c.record.target) for c in plan.changes],
                    [("configuration", "@project"), ("event", "S000002"), ("event", "S000003")],
                )

    def test_the_plan_names_who_would_make_the_change(self):
        ctx = self.context("sqlite")
        agent = Principal.agent("sess", acting_for=Principal.person("dw"))
        with acting_as(agent):
            plan = self.dry(ctx, os.path.join(BLUEPRINTS, "second_event.yaml"))
        self.assertEqual(plan.changes[0].record.principal_obj, agent)

    def test_a_strategy_which_expands_to_several_analyses(self):
        """Every analysis the real apply would add is in the plan."""
        for engine in ENGINES:
            with self.subTest(engine=engine):
                ctx = self.context(engine)
                path = os.path.join(BLUEPRINTS, "simple_test_pipeline.yaml")
                plan = self.dry(ctx, path, event="S000000", iterate=True)
                self.real(ctx, path, event="S000000", iterate=True)
                with ctx.activate():
                    names = sorted(p.name for p in ctx.ledger.get_event("S000000")[0].productions)
                self.assertEqual(
                    sorted(c.record.target.split("/")[1] for c in plan.changes), names
                )


class TestRefusals(DryRunTestCase):
    def test_an_analysis_which_already_exists_is_refused(self):
        for engine in ENGINES:
            with self.subTest(engine=engine):
                ctx = self.context(engine)
                path = os.path.join(BLUEPRINTS, "simple_test_pipeline.yaml")
                self.real(ctx, path, event="S000000")
                plan = self.dry(ctx, path, event="S000000")
                self.assertEqual(plan.changes, [])
                (refusal,) = plan.refused
                self.assertIn("already exists", refusal.message)
                self.assertEqual(refusal.level, "refused")
                self.assertNotIn("\x1b", refusal.message)

    def test_an_event_which_exists_is_refused_unless_it_is_an_update(self):
        for engine in ENGINES:
            with self.subTest(engine=engine):
                ctx = self.context(engine)
                plan = self.dry(ctx, os.path.join(DATA, "test_event.yaml"))
                self.assertEqual(plan.changes, [])
                self.assertIn("S000000 already exists", plan.refused[0].message)

    def test_updating_an_event_which_does_not_exist_is_refused(self):
        for engine in ENGINES:
            with self.subTest(engine=engine):
                ctx = self.context(engine)
                plan = self.dry(
                    ctx, os.path.join(BLUEPRINTS, "second_event.yaml"), update_page=True
                )
                self.assertEqual(plan.changes, [])
                self.assertIn("cannot be updated", plan.refused[0].message)

    def test_an_analysis_for_an_event_which_does_not_exist_is_refused(self):
        for engine in ENGINES:
            with self.subTest(engine=engine):
                ctx = self.context(engine)
                path = os.path.join(BLUEPRINTS, "simple_test_pipeline.yaml")
                try:
                    plan = self.dry(ctx, path, event="NoSuchEvent")
                except (KeyError, ValueError):
                    # The real apply can't find the event either.
                    with self.assertRaises((KeyError, ValueError)):
                        self.real(ctx, path, event="NoSuchEvent")
                else:
                    self.assertEqual(plan.changes, [])
                    self.assertTrue(plan.refused)

    def test_a_bundle_says_what_it_would_skip(self):
        for engine in ENGINES:
            with self.subTest(engine=engine):
                ctx = self.context(engine)
                self.real(ctx, self.text(BUNDLE), event="S000000")
                plan = self.dry(ctx, self.text(BUNDLE), event="S000000")
                self.assertEqual(plan.changes, [])
                self.assertEqual([r.level for r in plan.refused], ["skipped", "skipped"])

    def test_part_of_a_blueprint_can_be_refused_and_the_rest_applied(self):
        ctx = self.context("sqlite")
        text = (
            open(os.path.join(DATA, "test_event.yaml")).read()
            + "---\nkind: event\nname: S000004\nevent time: 5\n"
        )
        plan = self.dry(ctx, self.text(text))
        self.assertEqual([c.record.target for c in plan.changes], ["S000004"])
        self.assertEqual(len(plan.refused), 1)

    def test_what_is_refused_is_what_a_real_apply_refuses(self):
        for engine in ENGINES:
            with self.subTest(engine=engine):
                ctx = self.context(engine)
                path = os.path.join(DATA, "test_event.yaml")
                plan = self.dry(ctx, path)
                runner = CliRunner()
                with runner.isolation() as (out, _err, *_):
                    self.real(ctx, path)
                    said = click.unstyle(out.getvalue().decode())
                self.assertIn(plan.refused[0].message, said)


class TestDiffs(DryRunTestCase):
    def test_a_configuration_change_says_what_changes(self):
        for engine in ENGINES:
            with self.subTest(engine=engine):
                ctx = self.context(engine)
                plan = self.dry(ctx, self.text(CONFIGURATION.format(value=30)))
                (change,) = plan.changes
                self.assertEqual(
                    change.diff,
                    [{"path": "quality.minimum frequency.H1", "before": 20, "after": 30}],
                )

    def test_a_configuration_which_changes_nothing_says_so(self):
        for engine in ENGINES:
            with self.subTest(engine=engine):
                ctx = self.context(engine)
                plan = self.dry(ctx, self.text(CONFIGURATION.format(value=20)))
                (change,) = plan.changes
                self.assertEqual(change.diff, [])

    def test_a_new_configuration_key_has_no_before(self):
        ctx = self.context("yamlfile")
        plan = self.dry(ctx, self.text("kind: configuration\nbrand-new:\n  setting: 1\n"))
        (entry,) = [e for e in plan.changes[0].diff if e["path"].startswith("brand-new")]
        self.assertIsNone(entry["before"])
        self.assertEqual(entry["after"], {"setting": 1})

    def test_an_event_update_says_what_changes(self):
        for engine in ENGINES:
            with self.subTest(engine=engine):
                ctx = self.context(engine)
                plan = self.dry(ctx, self.text(EVENT_UPDATE), update_page=True)
                (change,) = plan.changes
                paths = {e["path"]: (e["before"], e["after"]) for e in change.diff}
                self.assertEqual(paths["event time"], (900, 901))
                self.assertEqual(paths["priors.mass ratio.minimum"], (0.1, 0.2))
                self.assertEqual(len(paths), 2)

    def test_an_added_document_has_no_diff(self):
        ctx = self.context("sqlite")
        plan = self.dry(ctx, os.path.join(BLUEPRINTS, "second_event.yaml"))
        self.assertIsNone(plan.changes[0].diff)


class TestChangedPaths(unittest.TestCase):
    def test_changed_nested_and_new_values(self):
        before = {"a": {"b": 1, "c": 2}, "d": 3}
        after = {"a": {"b": 1, "c": 5}, "d": 3, "e": {"f": 6}}
        self.assertEqual(
            sorted(changed_paths(before, after), key=lambda e: e["path"]),
            [
                {"path": "a.c", "before": 2, "after": 5},
                {"path": "e", "before": None, "after": {"f": 6}},
            ],
        )

    def test_a_removed_key_is_not_a_change(self):
        self.assertEqual(changed_paths({"a": 1, "b": 2}, {"a": 1}), [])

    def test_a_list_is_replaced_as_a_whole(self):
        self.assertEqual(
            changed_paths({"a": [1, 2]}, {"a": [1, 2, 3]}),
            [{"path": "a", "before": [1, 2], "after": [1, 2, 3]}],
        )

    def test_no_difference(self):
        self.assertEqual(changed_paths({"a": {"b": 1}}, {"a": {"b": 1}}), [])

    def test_the_values_are_copies(self):
        after = {"a": {"b": [1]}}
        (entry,) = changed_paths({}, after)
        after["a"]["b"].append(2)
        self.assertEqual(entry["after"], {"b": [1]})


class TestPlanOutput(unittest.TestCase):
    def test_to_dict_is_json(self):
        from asimov.audit import new_record
        from asimov.preview import ApplyPlan

        plan = ApplyPlan()
        plan.add_change(new_record("apply", "event", "S1", content={"a": 1}))
        plan.add_change(
            new_record("apply", "configuration", "@project", outcome="updated"),
            [{"path": "x", "before": 1, "after": 2}],
        )
        plan.refuse("Nope", "skipped")
        data = json.loads(json.dumps(plan.to_dict()))
        self.assertTrue(data["dry_run"])
        self.assertEqual([c["target"] for c in data["changes"]], ["S1", "@project"])
        self.assertEqual(data["changes"][1]["diff"], [{"path": "x", "before": 1, "after": 2}])
        self.assertEqual(data["refused"], [{"message": "Nope", "level": "skipped"}])
        self.assertNotIn("id", data["changes"][0])

    def test_render(self):
        from asimov.audit import new_record
        from asimov.preview import ApplyPlan

        plan = ApplyPlan()
        plan.add_change(new_record("apply", "event", "S1"))
        plan.add_change(
            new_record("apply", "configuration", "@project", outcome="updated"),
            [{"path": "x.y", "before": 1, "after": 2}, {"path": "z", "before": None, "after": "n"}],
        )
        plan.refuse("Could not apply S2")
        lines = plan.render()
        self.assertEqual(lines[0], "Dry run: nothing was written.")
        self.assertIn("  + event S1 (added)", lines)
        self.assertIn("  ~ configuration @project (updated)", lines)
        self.assertIn("      x.y: 1 -> 2", lines)
        self.assertIn("      z: 'n'", lines)
        self.assertIn("  ! Could not apply S2", lines)

    def test_an_empty_plan_says_nothing_would_change(self):
        self.assertIn("  Nothing would change.", ApplyPlan().render())

    def test_the_colours_which_mark_refusals_are_the_ones_click_uses(self):
        self.assertTrue(click.style("x", fg="red").startswith(application._RED))
        self.assertTrue(click.style("x", fg="yellow").startswith(application._YELLOW))


class TestLedgerDryRun(DryRunTestCase):
    def test_writes_in_the_block_are_discarded_but_can_be_read_in_it(self):
        from asimov.audit import new_record

        for engine in ENGINES:
            with self.subTest(engine=engine):
                ctx = self.context(engine)
                with ctx.ledger.dry_run():
                    ctx.ledger.data["scratch"] = {"a": 1}
                    ctx.ledger.save()
                    self.assertEqual(ctx.ledger.data["scratch"], {"a": 1})
                self.assertNotIn("scratch", ctx.ledger.data)
                again = ProjectContext.from_directory(ctx.root)
                self.addCleanup(lambda: getattr(again.ledger, "close", lambda: None)())
                self.assertNotIn("scratch", again.ledger.data)

    def test_an_exception_in_the_block_still_discards_the_writes(self):
        for engine in ENGINES:
            with self.subTest(engine=engine):
                ctx = self.context(engine)
                with self.assertRaises(ValueError):
                    with ctx.ledger.dry_run():
                        ctx.ledger.data["scratch"] = 1
                        ctx.ledger.save()
                        raise ValueError
                self.assertNotIn("scratch", ctx.ledger.data)
                ctx.ledger.save()
                again = ProjectContext.from_directory(ctx.root)
                self.addCleanup(lambda: getattr(again.ledger, "close", lambda: None)())
                self.assertNotIn("scratch", again.ledger.data)

    def test_a_ledger_can_be_used_normally_after_a_dry_run(self):
        for engine in ENGINES:
            with self.subTest(engine=engine):
                ctx = self.context(engine)
                with ctx.ledger.dry_run():
                    pass
                ctx.ledger.data["kept"] = 1
                ctx.ledger.save()
                again = ProjectContext.from_directory(ctx.root)
                self.addCleanup(lambda: getattr(again.ledger, "close", lambda: None)())
                self.assertEqual(again.ledger.data["kept"], 1)

    def test_a_ledger_which_cannot_discard_writes_refuses_and_does_not_run_the_block(self):
        directory = self.scratch()
        ledger = DatabaseLedger(engine="tinydb", location=os.path.join(directory, "l.json"))
        ran = []
        with self.assertRaises(NotImplementedError):
            with ledger.dry_run():
                ran.append(True)
        self.assertEqual(ran, [])

    def test_dry_run_state_is_cleared_afterwards(self):
        ctx = self.context("sqlite")
        self.assertFalse(is_dry_run())
        self.dry(ctx, os.path.join(DATA, "test_event.yaml"))
        self.assertFalse(is_dry_run())
        self.assertIsNone(current_plan())
        with self.assertRaises(ValueError):
            with ctx.ledger.dry_run():
                raise ValueError
        self.assertFalse(is_dry_run())

    def test_a_dry_run_is_visible_only_in_its_own_thread(self):
        import threading

        ctx = self.context("sqlite")
        seen = []
        with ctx.activate():
            from asimov.preview import preview

            with preview(ctx.ledger):
                worker = threading.Thread(target=lambda: seen.append(is_dry_run()))
                worker.start()
                worker.join()
                self.assertTrue(is_dry_run())
        self.assertEqual(seen, [False])


class TestCommand(DryRunTestCase):
    def run_apply(self, ctx, *args):
        with ctx.activate():
            return CliRunner().invoke(application.apply, list(args))

    def test_dry_run_prints_the_plan_and_changes_nothing(self):
        for engine in ENGINES:
            with self.subTest(engine=engine):
                ctx = self.context(engine)
                before = self.state(ctx)
                result = self.run_apply(
                    ctx,
                    "-f",
                    os.path.join(BLUEPRINTS, "simple_test_pipeline.yaml"),
                    "-e",
                    "S000000",
                    "--dry-run",
                )
                self.assertEqual(result.exit_code, 0, result.output)
                self.assertIn("Dry run: nothing was written.", result.output)
                self.assertIn("+ analysis S000000/test-simple-pipeline (added)", result.output)
                self.assertNotIn("Successfully", result.output)
                self.assertEqual(self.state(ctx), before)

    def test_dry_run_does_not_open_a_log_file(self):
        ctx = self.context("sqlite")
        with patch("asimov.setup_file_logging") as setup:
            self.run_apply(
                ctx, "-f", os.path.join(DATA, "test_event.yaml"), "--dry-run"
            )
            setup.assert_not_called()
            self.run_apply(ctx, "-f", os.path.join(DATA, "test_event.yaml"))
            setup.assert_called_once()

    def test_dry_run_reports_what_would_be_refused_and_still_exits_cleanly(self):
        ctx = self.context("sqlite")
        result = self.run_apply(ctx, "-f", os.path.join(DATA, "test_event.yaml"), "--dry-run")
        self.assertEqual(result.exit_code, 0)
        self.assertIn("! S000000 already exists in this project.", result.output)

    def test_json_output(self):
        ctx = self.context("sqlite")
        result = self.run_apply(
            ctx, "-f", self.text(CONFIGURATION.format(value=30)), "--dry-run", "--format", "json"
        )
        self.assertEqual(result.exit_code, 0, result.output)
        data = json.loads(result.output)
        self.assertTrue(data["dry_run"])
        self.assertEqual(data["changes"][0]["kind"], "configuration")
        self.assertEqual(data["changes"][0]["diff"][0]["after"], 30)
        self.assertEqual(data["refused"], [])

    def test_format_needs_dry_run(self):
        ctx = self.context("sqlite")
        result = self.run_apply(
            ctx, "-f", os.path.join(DATA, "test_event.yaml"), "--format", "json"
        )
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("--format is for --dry-run", result.output)

    def test_dry_run_cannot_be_used_with_a_plugin(self):
        ctx = self.context("sqlite")
        result = self.run_apply(ctx, "--plugin", "anything", "--dry-run")
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("can't be used with --plugin", result.output)

    def test_without_dry_run_it_applies_as_before(self):
        ctx = self.context("sqlite")
        result = self.run_apply(
            ctx, "-f", os.path.join(BLUEPRINTS, "second_event.yaml")
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Successfully added GW151226_033853", result.output)
        self.assertEqual([r.target for r in ctx.ledger.audit_log()][-1], "GW151226_033853")


if __name__ == "__main__":
    unittest.main()
