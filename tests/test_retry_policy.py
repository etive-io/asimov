"""
Retry policy and failure semantics (#240).

With nothing configured nothing changes; with a policy a failure is tried
again, up to a limit which depends on the kind of failure, and what needs an
analysis which was given up on either waits (``halt``) or goes ahead (``skip``).
"""
import configparser
import datetime
import os
import shutil
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch

from asimov import retry
from asimov.cli.application import apply_page
from asimov.cli.manage import check_dependencies_satisfied
from asimov.cli.project import make_project
from asimov.ledger import YAMLLedger
from asimov.monitor_states import RunningState, STATE_REGISTRY
from asimov.pipelines.command import CommandError

T0 = datetime.datetime(2026, 1, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)


def fake(status="running", **meta):
    return types.SimpleNamespace(name="a", status=status, meta=dict(meta), job_id=5)


def config_with(**options):
    parser = configparser.ConfigParser()
    parser.add_section("retry")
    for key, value in options.items():
        parser.set("retry", key, str(value))
    return patch.object(retry, "config", parser)


class PolicyTests(unittest.TestCase):
    def test_nothing_is_configured_by_default(self):
        rules = retry.policy(fake())
        self.assertFalse(rules["configured"])
        self.assertEqual(rules["attempts"], 1)
        self.assertEqual(rules["on failure"], "halt")

    def test_a_block_on_the_analysis(self):
        rules = retry.policy(fake(retry={"attempts": 4, "delay": 30, "backoff": 2}))
        self.assertTrue(rules["configured"])
        self.assertEqual((rules["attempts"], rules["delay"], rules["backoff"]), (4, 30.0, 2.0))

    def test_a_bare_number_is_the_attempts(self):
        self.assertEqual(retry.policy(fake(retry=3))["attempts"], 3)

    def test_the_project_configuration_is_the_default(self):
        with config_with(attempts=5, **{"on_failure": "skip"}):
            rules = retry.policy(fake())
        self.assertEqual(rules["attempts"], 5)
        self.assertEqual(rules["on failure"], "skip")
        self.assertTrue(rules["configured"])

    def test_the_analysis_wins_over_the_configuration(self):
        with config_with(attempts=5):
            self.assertEqual(retry.policy(fake(retry={"attempts": 2}))["attempts"], 2)

    def test_nonsense_falls_back_to_the_default(self):
        rules = retry.policy(fake(retry={"attempts": "many", "delay": -3}, **{"on failure": "explode"}))
        self.assertEqual(rules["attempts"], 1)
        self.assertEqual(rules["delay"], 0.0)
        self.assertEqual(rules["on failure"], "halt")


class ClassifyTests(unittest.TestCase):
    def test_a_held_job_is_transient(self):
        self.assertEqual(retry.classify(held=True), retry.TRANSIENT)

    def test_an_error_which_says_it_is_transient_is(self):
        error = RuntimeError("node lost")
        error.transient = True
        self.assertEqual(retry.classify(error), retry.TRANSIENT)

    def test_anything_else_is_deterministic(self):
        self.assertEqual(retry.classify(CommandError("exit 1")), retry.DETERMINISTIC)
        self.assertEqual(retry.classify(ValueError("x")), retry.DETERMINISTIC)


class OnFailureTests(unittest.TestCase):
    def test_with_no_policy_it_is_stuck_and_nothing_is_recorded(self):
        analysis = fake()
        self.assertEqual(retry.on_failure(analysis, retry.DETERMINISTIC, "boom", now=T0), retry.STUCK)
        self.assertEqual(analysis.status, "stuck")
        self.assertEqual(analysis.meta, {})

    def test_a_transient_failure_is_tried_again_up_to_the_limit(self):
        analysis = fake(retry={"attempts": 3})
        outcomes = []
        for _ in range(3):
            analysis.status = "running"
            outcomes.append(retry.on_failure(analysis, retry.TRANSIENT, "held", now=T0))
        self.assertEqual(outcomes, [retry.RETRY, retry.RETRY, retry.STUCK])
        self.assertEqual(analysis.status, "stuck")

    def test_a_deterministic_failure_is_tried_fewer_times(self):
        analysis = fake(retry={"attempts": 5, "deterministic attempts": 2})
        first = retry.on_failure(analysis, retry.DETERMINISTIC, "exit 1", now=T0)
        second = retry.on_failure(analysis, retry.DETERMINISTIC, "exit 1", now=T0)
        self.assertEqual((first, second), (retry.RETRY, retry.STUCK))

    def test_the_deterministic_limit_cannot_exceed_the_attempts(self):
        analysis = fake(retry={"attempts": 1, "deterministic attempts": 9})
        self.assertEqual(retry.on_failure(analysis, retry.DETERMINISTIC, "x", now=T0), retry.STUCK)

    def test_each_failure_is_recorded_with_its_kind_and_reason(self):
        analysis = fake(retry={"attempts": 3})
        retry.on_failure(analysis, retry.TRANSIENT, "held on the scheduler", now=T0)
        retry.on_failure(analysis, retry.DETERMINISTIC, "exit 3", now=T0)
        self.assertEqual(
            [(a["attempt"], a["kind"], a["reason"]) for a in analysis.meta["attempts"]],
            [(1, "transient", "held on the scheduler"), (2, "deterministic", "exit 3")],
        )
        self.assertEqual(analysis.meta["attempts"][0]["failed"], "2026-01-01T12:00:00Z")

    def test_a_retry_is_ready_again_and_waits_out_its_delay(self):
        analysis = fake(retry={"attempts": 4, "delay": 60, "backoff": 2})
        retry.on_failure(analysis, retry.TRANSIENT, "x", now=T0)
        self.assertEqual(analysis.status, "ready")
        self.assertEqual(analysis.meta["retry after"], "2026-01-01T12:01:00Z")
        retry.on_failure(analysis, retry.TRANSIENT, "x", now=T0)
        self.assertEqual(analysis.meta["retry after"], "2026-01-01T12:02:00Z")
        retry.on_failure(analysis, retry.TRANSIENT, "x", now=T0)
        self.assertEqual(analysis.meta["retry after"], "2026-01-01T12:04:00Z")

    def test_no_delay_means_no_wait(self):
        analysis = fake(retry={"attempts": 2})
        retry.on_failure(analysis, retry.TRANSIENT, "x", now=T0)
        self.assertNotIn("retry after", analysis.meta)

    def test_skip_gives_the_analysis_up_instead_of_sticking(self):
        analysis = fake(retry={"attempts": 1}, **{"on failure": "skip"})
        self.assertEqual(retry.on_failure(analysis, retry.DETERMINISTIC, "x", now=T0), retry.SKIPPED)
        self.assertEqual(analysis.status, "skipped")
        self.assertNotIn("retry after", analysis.meta)

    def test_skip_applies_with_no_retry_block(self):
        analysis = fake(**{"on failure": "skip"})
        self.assertEqual(retry.on_failure(analysis, retry.DETERMINISTIC, "x", now=T0), retry.SKIPPED)

    def test_a_policy_from_the_configuration_applies(self):
        analysis = fake()
        with config_with(attempts=2):
            self.assertEqual(retry.on_failure(analysis, retry.TRANSIENT, "x", now=T0), retry.RETRY)

    def test_describing_what_was_decided(self):
        analysis = fake(retry={"attempts": 3})
        outcome = retry.on_failure(analysis, retry.TRANSIENT, "x", now=T0)
        self.assertIn("attempt 2 of 3", retry.describe(analysis, outcome))


class DeferredTests(unittest.TestCase):
    def test_deferred_until_the_time(self):
        analysis = fake("ready", **{"retry after": "2026-01-01T12:01:00Z"})
        self.assertTrue(retry.deferred(analysis, T0))
        self.assertFalse(retry.deferred(analysis, T0 + datetime.timedelta(seconds=61)))

    def test_not_deferred_without_a_time_or_with_nonsense(self):
        self.assertFalse(retry.deferred(fake("ready"), T0))
        self.assertFalse(retry.deferred(fake("ready", **{"retry after": "soon"}), T0))

    def test_pending_counts_ready_analyses_which_are_waiting(self):
        waiting = fake("ready", **{"retry after": "2026-01-01T12:01:00Z"})
        other = fake("running", **{"retry after": "2026-01-01T12:01:00Z"})
        self.assertEqual(retry.pending([waiting, other, fake("ready")], T0), 1)

    def test_clear_forgets_everything(self):
        analysis = fake(attempts=[{"attempt": 1}], **{"retry after": "x", "skipped inputs": ["b"]})
        retry.clear(analysis)
        self.assertEqual(analysis.meta, {})


class MonitorTests(unittest.TestCase):
    """What the monitor does when an analysis fails."""

    def context(self, analysis, pipeline):
        analysis.pipeline = pipeline
        return types.SimpleNamespace(
            analysis=analysis,
            dry_run=False,
            ledger=MagicMock(),
            job_id=5,
            job=None,
            update_ledger=MagicMock(),
            clear_job_id=MagicMock(),
            refresh_job_list=MagicMock(),
        )

    def pipeline(self, error=None):
        pipe = MagicMock()
        pipe.detect_completion.return_value = False
        pipe.resurrect.side_effect = error or CommandError("exited with status 1")
        return pipe

    def test_with_no_policy_a_failed_rescue_is_stuck_as_before(self):
        analysis = fake()
        context = self.context(analysis, self.pipeline())
        self.assertFalse(RunningState()._handle_no_condor_job(context))
        self.assertEqual(analysis.status, "stuck")
        self.assertEqual(analysis.meta, {})
        context.clear_job_id.assert_not_called()

    def test_with_a_policy_a_failed_command_is_tried_again(self):
        analysis = fake(retry={"attempts": 3, "deterministic attempts": 3})
        context = self.context(analysis, self.pipeline())
        self.assertTrue(RunningState()._handle_no_condor_job(context))
        self.assertEqual(analysis.status, "ready")
        context.clear_job_id.assert_called_once()
        context.update_ledger.assert_called()
        self.assertEqual(len(analysis.meta["attempts"]), 1)
        self.assertEqual(analysis.meta["attempts"][0]["kind"], "deterministic")

    def test_at_the_limit_it_is_stuck_and_the_event_is_emitted(self):
        analysis = fake(retry={"attempts": 2, "deterministic attempts": 2})
        with patch("asimov.telemetry.emit_event") as emit:
            context = self.context(analysis, self.pipeline())
            RunningState()._handle_no_condor_job(context)
            self.assertEqual(analysis.status, "ready")
            emit.assert_not_called()
            analysis.status = "running"
            self.assertFalse(RunningState()._handle_no_condor_job(context))
            self.assertEqual(analysis.status, "stuck")
            self.assertEqual(emit.call_args[0][1], "retries_exhausted")
            self.assertEqual(emit.call_args[1]["attempts"], 2)

    def test_a_transient_error_is_tried_more_often_than_a_deterministic_one(self):
        error = RuntimeError("node failure")
        error.transient = True
        analysis = fake(retry={"attempts": 4, "deterministic attempts": 1})
        context = self.context(analysis, self.pipeline(error))
        for _ in range(3):
            analysis.status = "running"
            self.assertTrue(RunningState()._handle_no_condor_job(context))
            self.assertEqual(analysis.status, "ready")

    def test_skip_marks_the_analysis_skipped(self):
        analysis = fake(**{"on failure": "skip"})
        context = self.context(analysis, self.pipeline())
        self.assertTrue(RunningState()._handle_no_condor_job(context))
        self.assertEqual(analysis.status, "skipped")

    def held(self, analysis, removes):
        """A held job; the scheduler does or does not let it be removed."""
        pipe = self.pipeline()
        if removes:
            pipe.eject_job.side_effect = lambda: setattr(analysis, "job_id", None)
        context = self.context(analysis, pipe)
        context.job = {"status": 5}
        return pipe, context

    def test_a_held_job_is_removed_and_tried_again(self):
        analysis = fake(retry={"attempts": 2})
        pipe, context = self.held(analysis, removes=True)
        self.assertTrue(RunningState()._handle_condor_job(context))
        self.assertEqual(analysis.status, "ready")
        pipe.eject_job.assert_called_once()
        context.clear_job_id.assert_called_once()
        self.assertEqual(analysis.meta["attempts"][0]["kind"], "transient")

    def test_a_held_job_which_cannot_be_removed_is_not_tried_again(self):
        """eject_job does not raise when condor_rm fails: a second run would join the first."""
        analysis = fake(retry={"attempts": 3})
        with patch("asimov.telemetry.emit_event") as emit:
            pipe, context = self.held(analysis, removes=False)
            self.assertTrue(RunningState()._handle_condor_job(context))
            self.assertEqual(analysis.status, "stuck")
            self.assertEqual(analysis.job_id, 5)
            context.clear_job_id.assert_not_called()
            self.assertNotIn("retry after", analysis.meta)
            self.assertIn("could not be removed", analysis.meta["attempts"][0]["reason"])
            emit.assert_not_called()

    def test_a_held_job_whose_removal_raises_is_not_tried_again(self):
        analysis = fake(retry={"attempts": 3})
        pipe, context = self.held(analysis, removes=False)
        pipe.eject_job.side_effect = RuntimeError("condor is not installed")
        self.assertTrue(RunningState()._handle_condor_job(context))
        self.assertEqual(analysis.status, "stuck")
        self.assertEqual(analysis.job_id, 5)

    def test_a_held_job_with_no_policy_is_stuck_and_left_on_the_scheduler(self):
        analysis = fake()
        pipe = self.pipeline()
        context = self.context(analysis, pipe)
        context.job = {"status": 5}
        self.assertTrue(RunningState()._handle_condor_job(context))
        self.assertEqual(analysis.status, "stuck")
        pipe.eject_job.assert_not_called()

    def test_there_is_a_handler_for_the_skipped_state(self):
        self.assertIn("skipped", STATE_REGISTRY)
        self.assertTrue(STATE_REGISTRY["skipped"].handle(types.SimpleNamespace(analysis=fake("skipped"))))


class GraphCase(unittest.TestCase):
    """Analyses in a ledger: a, then b which needs it; in another subject, c needs a."""

    def setUp(self):
        self.cwd = os.getcwd()
        self.root = tempfile.mkdtemp()
        os.chdir(self.root)
        make_project(name="Test project", root=self.root, engine="yamlfile")
        self.ledger = YAMLLedger(".asimov/ledger.yml")
        self.apply("kind: event\nname: E\ninterferometers: [H1]\n---\nkind: event\nname: F\ninterferometers: [H1]\n")
        self.apply(
            "kind: analysis\nname: a\npipeline: simpletestpipeline\nstatus: ready\n---\n"
            "kind: analysis\nname: b\npipeline: simpletestpipeline\nstatus: ready\nneeds: [a]\n",
            subject="E",
        )
        self.apply(
            "kind: analysis\nname: c\npipeline: simpletestpipeline\nstatus: ready\nneeds: [E/a]\n",
            subject="F",
        )

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.root, ignore_errors=True)

    def apply(self, text, subject=None):
        with open("blueprint.yaml", "w") as handle:
            handle.write(text)
        apply_page("blueprint.yaml", event=subject, ledger=self.ledger)

    def analysis(self, subject, name, ledger=None):
        event = (ledger or YAMLLedger(".asimov/ledger.yml")).get_event(subject)[0]
        return event, next(p for p in event.productions if p.name == name)

    def change(self, subject, name, status=None, **meta):
        event, analysis = self.analysis(subject, name)
        if status:
            analysis.status = status
        analysis.meta.update(meta)
        self.ledger.update_event(event)

    def startable(self, subject):
        event = YAMLLedger(".asimov/ledger.yml").get_event(subject)[0]
        return sorted(p.name for p in event.get_all_latest())


class GatingTests(GraphCase):
    def test_a_retry_waits_for_its_delay(self):
        self.change("E", "a", "ready", **{"retry after": "2026-01-01T12:01:00Z"})
        with patch.object(retry, "_now", return_value=T0):
            self.assertEqual(self.startable("E"), [])
        with patch.object(retry, "_now", return_value=T0 + datetime.timedelta(minutes=2)):
            self.assertEqual(self.startable("E"), ["a"])

    def test_without_a_delay_it_is_startable_at_once(self):
        self.assertEqual(self.startable("E"), ["a"])

    def test_halt_leaves_what_needs_a_failed_analysis_waiting(self):
        self.change("E", "a", "stuck")
        self.assertEqual(self.startable("E"), [])
        self.assertEqual(self.startable("F"), [])

    def test_skip_lets_what_needs_it_go_ahead(self):
        self.change("E", "a", "skipped")
        self.assertEqual(self.startable("E"), ["b"])

    def test_skip_lets_an_analysis_in_another_subject_go_ahead(self):
        self.assertEqual(self.startable("F"), [])
        self.change("E", "a", "skipped")
        self.assertEqual(self.startable("F"), ["c"])

    def test_a_skipped_analysis_is_not_started_itself(self):
        self.change("E", "a", "skipped")
        self.assertNotIn("a", self.startable("E"))


class SkippedInputTests(GraphCase):
    def test_what_was_skipped_is_noted_on_what_needs_it(self):
        self.change("E", "a", "skipped")
        _, b = self.analysis("E", "b")
        self.assertEqual(retry.note_skipped_inputs(b), ["a"])
        self.assertEqual(b.meta["skipped inputs"], ["a"])
        _, c = self.analysis("F", "c")
        self.assertEqual(retry.note_skipped_inputs(c), ["E/a"])

    def test_nothing_is_noted_when_nothing_was_skipped(self):
        _, b = self.analysis("E", "b")
        self.assertEqual(retry.note_skipped_inputs(b), [])
        self.assertNotIn("skipped inputs", b.meta)

    def test_building_says_so(self):
        self.change("E", "a", "skipped")
        _, b = self.analysis("E", "b")
        with patch("asimov.cli.manage.click.echo") as echo:
            check_dependencies_satisfied(b, MagicMock())
        said = " ".join(str(call.args[0]) for call in echo.call_args_list)
        self.assertIn("b needs a, which was skipped", said)


class RerunTests(GraphCase):
    def test_running_one_again_forgets_the_failures(self):
        from asimov import groups

        self.change(
            "E", "a", "stuck", attempts=[{"attempt": 1}], **{"retry after": "2026-01-01T12:01:00Z"}
        )
        member = groups.find(self.ledger, "E", "a")
        groups.reset(self.ledger, [member])
        _, a = self.analysis("E", "a")
        self.assertEqual(a.status, "ready")
        self.assertNotIn("attempts", a.meta)
        self.assertNotIn("retry after", a.meta)

    def test_setting_it_ready_forgets_them_too(self):
        from asimov import groups

        self.change("E", "a", "stuck", attempts=[{"attempt": 1}])
        groups.set_status(self.ledger, [groups.find(self.ledger, "E", "a")], "ready")
        _, a = self.analysis("E", "a")
        self.assertNotIn("attempts", a.meta)


class CommandMessageTests(GraphCase):
    def test_a_missing_input_says_when_it_is_because_the_provider_was_skipped(self):
        self.apply(
            "kind: analysis\nname: p\ncommand: [true]\noutputs:\n  data: d.txt\n---\n"
            "kind: analysis\nname: q\ncommand: [cat, '{inputs.data}']\nneeds: [p]\n",
            subject="E",
        )
        self.change("E", "p", "skipped")
        _, q = self.analysis("E", "q")
        with self.assertRaisesRegex(CommandError, "p failed and was skipped"):
            q.pipeline.resolve_command()


class UntilIdleTests(unittest.TestCase):
    """``monitor --until-idle`` and a retry which falls due while a pass runs."""

    def run_loop(self, pending):
        from asimov.cli import monitor as monitor_module

        ctx = MagicMock()
        ctx.meta = {}
        ctx.invoke.return_value = {}
        with patch.object(monitor_module, "_status_counts", return_value={"ready": 1}), patch.object(
            monitor_module, "_attempt_counts", return_value={}
        ), patch.object(monitor_module, "_analyses", return_value=[]), patch.object(
            monitor_module.retry, "pending", side_effect=pending
        ), patch.object(monitor_module.time, "sleep"):
            monitor_module._monitor_until_idle(ctx, None, False, False, 0, None, None)
        return ctx.invoke.call_count

    def test_a_retry_which_was_waiting_at_the_start_of_the_pass_gets_another(self):
        """Its delay ended during the pass, after submit had passed it by."""
        self.assertEqual(self.run_loop([1, 0, 0, 0]), 2)

    def test_nothing_waiting_is_idle_after_one_pass(self):
        self.assertEqual(self.run_loop([0, 0]), 1)


class SkippedOutputsTests(GraphCase):
    def test_what_a_skipped_analysis_left_is_not_an_input(self):
        self.apply(
            "kind: analysis\nname: p\ncommand: [true]\noutputs:\n  data: d.txt\n---\n"
            "kind: analysis\nname: q\ncommand: [cat, '{inputs.data}']\nneeds: [p]\n",
            subject="E",
        )
        _, p = self.analysis("E", "p")
        os.makedirs(p.rundir, exist_ok=True)
        with open(os.path.join(p.rundir, "d.txt"), "w") as handle:
            handle.write("partial")
        self.change("E", "p", "finished")
        _, q = self.analysis("E", "q")
        self.assertEqual(len(q.pipeline.resolve_command()), 2)  # it is there while p has finished
        self.change("E", "p", "skipped")
        _, q = self.analysis("E", "q")
        with self.assertRaisesRegex(CommandError, "skipped"):
            q.pipeline.resolve_command()

    def test_previous_assets_leave_out_a_skipped_analysis(self):
        _, b = self.analysis("E", "b")
        _, a = self.analysis("E", "a")
        with patch.object(type(a.pipeline), "collect_assets", return_value={"x": 1}):
            self.assertEqual(b._previous_assets(), {"x": 1})
            self.change("E", "a", "skipped")
            _, b = self.analysis("E", "b")
            self.assertEqual(b._previous_assets(), {})


class ManualReadyTests(GraphCase):
    def test_production_set_ready_forgets_the_failures(self):
        from click.testing import CliRunner

        from asimov.cli import production

        self.change("E", "a", "stuck", attempts=[{"attempt": 1}], **{"retry after": "2026-01-01T12:01:00Z"})
        with patch("asimov.cli.production.ledger", new=YAMLLedger(".asimov/ledger.yml")):
            result = CliRunner().invoke(production.set, ["E", "a", "-s", "ready"])
        self.assertEqual(result.exit_code, 0, result.output)
        _, a = self.analysis("E", "a")
        self.assertEqual(a.status, "ready")
        self.assertNotIn("attempts", a.meta)
        self.assertNotIn("retry after", a.meta)

    def test_restarting_forgets_them_too(self):
        from asimov.custom_states import RestartState

        self.change("E", "a", "restart", attempts=[{"attempt": 1}])
        event, a = self.analysis("E", "a")
        context = types.SimpleNamespace(
            analysis=a, has_condor_job=lambda: False, update_ledger=MagicMock(), job_id=None, dry_run=False,
            refresh_job_list=MagicMock(), clear_job_id=MagicMock(),
        )
        a.pipeline = MagicMock()
        RestartState().handle(context)
        self.assertEqual(a.status, "ready")
        self.assertNotIn("attempts", a.meta)


from tests.test_project_analysis_cli import ProjectAnalysisTestCase  # noqa: E402
from click.testing import CliRunner  # noqa: E402
from asimov.cli import manage  # noqa: E402
from asimov.review import ReviewMessage  # noqa: E402


class ProjectAnalysisDelayTests(ProjectAnalysisTestCase):
    """A project analysis which failed waits out its delay as an analysis of a subject does."""

    base_status = "finished"

    def setUp(self):
        super().setUp()
        ledger = YAMLLedger(".asimov/ledger.yml")
        event = ledger.get_event("EvA")[0]
        analysis = event.productions[0]
        analysis.review.add(ReviewMessage(message="ok", status="approved", production=analysis))
        ledger.update_event(event)

    def delay(self, until):
        ledger = YAMLLedger(".asimov/ledger.yml")
        pa = ledger.project_analyses[0]
        pa.meta["retry after"] = until
        ledger.update_analysis_in_project_analysis(pa)

    def submit(self):
        with patch("asimov.cli.manage.ledger", new=YAMLLedger(".asimov/ledger.yml")), patch(
            "asimov.cli.manage.condor"
        ), patch("asimov.pipelines.testing.SimpleTestPipeline.build_dag", create=True) as build_dag:
            CliRunner().invoke(manage.submit, [])
        return build_dag

    def test_it_is_submitted_when_it_has_no_delay(self):
        self.submit().assert_called()

    def test_it_is_not_submitted_while_it_waits(self):
        self.delay("2999-01-01T00:00:00Z")
        self.submit().assert_not_called()

    def test_it_is_submitted_once_the_delay_is_over(self):
        self.delay("2000-01-01T00:00:00Z")
        self.submit().assert_called()


if __name__ == "__main__":
    unittest.main()
