"""
Asset retention (#237): sizes are recorded, and outputs which nothing needs any
more are released, only when it is safe, and with a record.
"""
import hashlib
import os
import shutil
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from asimov import groups, retention
from asimov.cli import analysis as analysis_cli
from asimov.cli.application import apply_page
from asimov.cli.project import make_project
from asimov.ledger import YAMLLedger
from asimov.monitor_states import RunningState
from asimov.pipelines.command import CommandError
from asimov.strategies import Strategy

EVENTS = "kind: event\nname: E\ninterferometers: [H1]\n---\nkind: event\nname: F\ninterferometers: [H1]\n"

#: gen (a big until_consumed output and a kept one), use needs gen, and in another subject, far needs gen.
BLUEPRINT = """kind: analysis
name: gen
command: [true]
outputs:
  big: {path: big.dat, retention: until_consumed}
  final: {path: final.txt, retention: keep}
  tree: {path: tree, retention: until_consumed}
---
kind: analysis
name: use
command: [cat, "{inputs.big}"]
needs: [gen]
"""
FAR = "kind: analysis\nname: far\ncommand: [echo, hi]\nneeds: [E/gen]\n"


class RetentionCase(unittest.TestCase):
    def setUp(self):
        self.cwd = os.getcwd()
        self.root = tempfile.mkdtemp()
        os.chdir(self.root)
        make_project(name="Test project", root=self.root, engine="yamlfile")
        self.ledger = YAMLLedger(".asimov/ledger.yml")
        self.apply(EVENTS)
        self.apply(BLUEPRINT, "E")
        self.apply(FAR, "F")
        self.members = None

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.root, ignore_errors=True)

    def apply(self, text, subject=None):
        with open("blueprint.yaml", "w") as handle:
            handle.write(text)
        apply_page("blueprint.yaml", event=subject, ledger=self.ledger)

    def fresh(self):
        return YAMLLedger(".asimov/ledger.yml")

    def find(self, subject, name, ledger=None):
        return groups.find(ledger or self.fresh(), subject, name)

    def change(self, subject, name, status=None, **meta):
        member = self.find(subject, name)
        if status:
            member.analysis.status = status
        member.analysis.meta.update(meta)
        groups._save(self.fresh(), member)

    def make_outputs(self, size=1000):
        """What gen produced, in its run directory."""
        gen = self.find("E", "gen").analysis
        os.makedirs(os.path.join(gen.rundir, "tree", "sub"), exist_ok=True)
        with open(os.path.join(gen.rundir, "big.dat"), "wb") as handle:
            handle.write(b"x" * size)
        with open(os.path.join(gen.rundir, "final.txt"), "w") as handle:
            handle.write("answer")
        with open(os.path.join(gen.rundir, "tree", "sub", "a.bin"), "wb") as handle:
            handle.write(b"y" * 50)
        return gen.rundir

    def finish_all(self):
        for subject, name in (("E", "gen"), ("E", "use"), ("F", "far")):
            self.change(subject, name, "complete")

    def plan(self, **kwargs):
        ledger = self.fresh()
        return retention.plan(ledger, groups.everything(ledger), **kwargs)

    def released_items(self, **kwargs):
        return sorted((i.member.label, i.asset) for i in self.plan(**kwargs).items)


class HelperTests(unittest.TestCase):
    def test_human_sizes(self):
        self.assertEqual(retention.human(0), "0 B")
        self.assertEqual(retention.human(999), "999 B")
        self.assertEqual(retention.human(1500), "1.5 kB")
        self.assertEqual(retention.human(3_000_000), "3.0 MB")
        self.assertEqual(retention.human(None), "?")

    def test_the_size_of_a_file_and_of_a_directory(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "d", "e"))
            for path, n in (("a", 10), ("d/b", 20), ("d/e/c", 30)):
                with open(os.path.join(root, path), "wb") as handle:
                    handle.write(b"z" * n)
            self.assertEqual(retention.size_of(os.path.join(root, "a")), (10, 1))
            self.assertEqual(retention.size_of(os.path.join(root, "d")), (50, 2))

    def test_the_hash_of_a_file_only(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "f")
            with open(path, "wb") as handle:
                handle.write(b"hello")
            self.assertEqual(retention.hash_of(path), hashlib.sha256(b"hello").hexdigest())
            self.assertIsNone(retention.hash_of(root))
            self.assertIsNone(retention.hash_of(os.path.join(root, "missing")))

    def test_the_switch(self):
        import configparser

        parser = configparser.ConfigParser()
        parser.add_section("retention")
        parser.set("retention", "release", "false")
        with patch.object(retention, "config", parser):
            self.assertFalse(retention.enabled())
        self.assertTrue(retention.enabled())


class DeclarationTests(RetentionCase):
    def test_the_command_pipeline_reads_retention_from_its_outputs(self):
        gen = self.find("E", "gen").analysis
        self.assertEqual(retention.policy_of(gen, "big"), "until_consumed")
        self.assertEqual(retention.policy_of(gen, "final"), "keep")

    def test_an_output_which_says_nothing_is_kept(self):
        use = self.find("E", "use").analysis
        self.assertEqual(retention.policy_of(use, "anything"), "keep")

    def test_a_policy_which_is_not_one_is_kept(self):
        gen = self.find("E", "gen").analysis
        with patch.object(type(gen.pipeline), "retention_of", return_value="store"):
            self.assertEqual(retention.policy_of(gen, "big"), "keep")
        with patch.object(type(gen.pipeline), "retention_of", return_value="whenever"):
            self.assertEqual(retention.policy_of(gen, "big"), "keep")

    def test_a_pipeline_which_says_nothing_has_no_outputs_and_keeps_everything(self):
        from asimov.pipeline import Pipeline

        self.assertEqual(Pipeline.output_retention, {})
        pipe = Pipeline.__new__(Pipeline)
        self.assertEqual(pipe.retention_of("x"), "keep")
        self.assertEqual(pipe.output_paths(), {})

    def test_what_exists_is_what_is_found(self):
        gen = self.find("E", "gen").analysis
        self.assertEqual(retention.output_paths(gen), {})
        self.make_outputs()
        self.assertEqual(sorted(retention.output_paths(self.find("E", "gen").analysis)), ["big", "final", "tree"])


class SizeTests(RetentionCase):
    def test_sizes_are_recorded(self):
        self.make_outputs(1000)
        gen = self.find("E", "gen").analysis
        found = retention.record_sizes(gen)
        self.assertEqual(found["big"], {"size": 1000, "files": 1})
        self.assertEqual(found["tree"], {"size": 50, "files": 1})
        self.assertEqual(gen.meta["assets"], found)
        self.assertEqual(retention.recorded_size(gen), 1000 + 6 + 50)

    def test_nothing_is_recorded_when_there_is_nothing(self):
        gen = self.find("E", "gen").analysis
        self.assertEqual(retention.record_sizes(gen), {})
        self.assertNotIn("assets", gen.meta)

    def test_sizes_are_recorded_when_an_analysis_finishes(self):
        analysis = types.SimpleNamespace(
            name="a", status="running", meta={}, job_id=None, rundir=tempfile.mkdtemp(),
        )
        self.addCleanup(shutil.rmtree, analysis.rundir, True)
        with open(os.path.join(analysis.rundir, "out.dat"), "wb") as handle:
            handle.write(b"q" * 123)
        pipe = MagicMock()
        pipe.detect_completion.return_value = True
        pipe.output_paths.return_value = {"out": "out.dat"}
        analysis.pipeline = pipe
        context = types.SimpleNamespace(
            analysis=analysis, job_id=None, update_ledger=MagicMock(), refresh_job_list=MagicMock(),
            clear_job_id=MagicMock(), ledger=MagicMock(), dry_run=False,
        )
        RunningState()._handle_no_condor_job(context)
        self.assertEqual(analysis.meta["assets"], {"out": {"size": 123, "files": 1}})


class PlanTests(RetentionCase):
    def setUp(self):
        super().setUp()
        self.make_outputs()
        self.finish_all()

    def test_what_every_consumer_has_finished_with_may_go(self):
        self.assertEqual(self.released_items(), [("E/gen", "big"), ("E/gen", "tree")])

    def test_a_keep_output_is_never_released(self):
        self.assertNotIn(("E/gen", "final"), self.released_items())

    def test_the_size_is_the_sum_of_what_goes(self):
        self.assertEqual(self.plan().size, 1000 + 50)

    def test_nothing_goes_while_a_consumer_has_not_finished(self):
        self.change("E", "use", "running")
        self.assertEqual(self.released_items(), [])
        self.assertTrue(any("use" in why and "still to finish" in why for _, _, why in self.plan().kept))

    def test_nothing_goes_while_a_consumer_in_another_subject_has_not_finished(self):
        self.change("F", "far", "ready")
        self.assertEqual(self.released_items(), [])
        self.assertTrue(any("F/far" in why for _, _, why in self.plan().kept))

    def test_a_consumer_which_was_skipped_will_not_consume_it(self):
        self.change("E", "use", "skipped")
        self.assertEqual(self.released_items(), [("E/gen", "big"), ("E/gen", "tree")])

    def test_a_consumer_which_is_stuck_may_be_run_again_so_it_holds_the_output(self):
        self.change("E", "use", "stuck")
        self.assertEqual(self.released_items(), [])

    def test_nothing_goes_from_an_analysis_which_has_not_finished(self):
        self.change("E", "gen", "running")
        self.assertEqual(self.released_items(), [])
        self.assertTrue(any("has not finished" in why for _, _, why in self.plan().kept))

    def test_an_output_which_nothing_consumed_is_not_an_intermediate(self):
        """No analysis needs the first one, so its until_consumed output stays."""
        self.apply(
            "kind: analysis\nname: lonely\ncommand: [true]\noutputs:\n  o: {path: o.dat, retention: until_consumed}\n",
            "E",
        )
        lonely = self.find("E", "lonely").analysis
        os.makedirs(lonely.rundir, exist_ok=True)
        with open(os.path.join(lonely.rundir, "o.dat"), "w") as handle:
            handle.write("x")
        self.change("E", "lonely", "complete")
        self.assertNotIn(("E/lonely", "o"), self.released_items())
        self.assertTrue(any(why == "nothing has consumed it" for _, _, why in self.plan().kept))

    def test_what_is_already_released_is_not_released_again(self):
        retention.release(self.fresh(), self.plan().items)
        self.assertEqual(self.released_items(), [])

    def test_the_scope_limits_what_is_released(self):
        ledger = self.fresh()
        members = groups.everything(ledger)
        nothing = retention.plan(ledger, members, scope=[m for m in members if m.name == "use"])
        self.assertEqual(nothing.items, [])

    def test_a_symbolic_link_is_not_followed(self):
        gen = self.find("E", "gen").analysis
        os.remove(os.path.join(gen.rundir, "big.dat"))
        with open(os.path.join(self.root, "elsewhere.dat"), "w") as handle:
            handle.write("precious")
        os.symlink(os.path.join(self.root, "elsewhere.dat"), os.path.join(gen.rundir, "big.dat"))
        self.assertNotIn(("E/gen", "big"), self.released_items())
        self.assertTrue(any("symbolic link" in why for _, _, why in self.plan().kept))

    def test_nothing_outside_the_run_directory_is_released(self):
        outside = os.path.join(self.root, "outside.dat")
        with open(outside, "w") as handle:
            handle.write("not yours")
        gen = self.find("E", "gen").analysis
        with patch.object(type(gen.pipeline), "output_paths", return_value={"big": outside}):
            ledger = self.fresh()
            result = retention.plan(ledger, groups.everything(ledger))
        self.assertNotIn(("E/gen", "big"), [(i.member.label, i.asset) for i in result.items])
        self.assertTrue(any("outside the run directory" in why for _, _, why in result.kept))

    def test_nothing_in_the_results_store_is_released(self):
        gen = self.find("E", "gen").analysis
        with patch.object(retention, "_store_root", return_value=os.path.realpath(gen.rundir)):
            self.assertEqual(self.released_items(), [])
            self.assertTrue(any("results store" in why for _, _, why in self.plan().kept))


class Grower(Strategy):
    def expand(self, blueprint, context):
        return []

    def extend(self, analysis, context):
        return []


class Fixed(Strategy):
    def expand(self, blueprint, context):
        return []


class SelectiveGrower(Grower):
    def may_consume(self, analysis, context):
        return analysis.name != "gen"


class GroupTests(RetentionCase):
    def setUp(self):
        super().setUp()
        self.make_outputs()
        self.finish_all()

    def plugins(self, **strategies):
        entries = [types.SimpleNamespace(name=n, load=lambda c=c: c) for n, c in strategies.items()]
        return patch("asimov.strategies.entry_points", return_value=entries)

    def stamp(self, kind):
        for subject, name in (("E", "gen"), ("E", "use"), ("F", "far")):
            self.change(subject, name, strategy={"type": kind, "id": "g"})

    def test_a_group_which_can_grow_keeps_what_a_later_analysis_may_consume(self):
        self.stamp("grower")
        with self.plugins(grower=Grower):
            self.assertEqual(self.released_items(), [])
            self.assertTrue(any("may still add" in why for _, _, why in self.plan().kept))

    def test_done_says_the_group_will_not_grow(self):
        self.stamp("grower")
        with self.plugins(grower=Grower):
            self.assertEqual(self.released_items(done=True), [("E/gen", "big"), ("E/gen", "tree")])

    def test_a_strategy_can_say_what_a_later_analysis_will_not_consume(self):
        self.stamp("selective")
        with self.plugins(selective=SelectiveGrower):
            self.assertEqual(self.released_items(), [("E/gen", "big"), ("E/gen", "tree")])

    def test_a_group_which_cannot_grow_has_nothing_to_wait_for(self):
        self.stamp("fixed")
        with self.plugins(fixed=Fixed):
            self.assertEqual(self.released_items(), [("E/gen", "big"), ("E/gen", "tree")])

    def test_a_strategy_which_cannot_be_found_keeps_what_it_made(self):
        """It may have failed to load for now: that does not say its group will not grow."""
        self.stamp("gone")
        with self.plugins():
            self.assertEqual(self.released_items(), [])
            self.assertEqual(self.released_items(done=True), [("E/gen", "big"), ("E/gen", "tree")])

    def test_a_strategy_which_fails_when_asked_keeps_everything(self):
        class Broken(Grower):
            def may_consume(self, analysis, context):
                raise RuntimeError("no")

        self.stamp("broken")
        with self.plugins(broken=Broken):
            self.assertEqual(self.released_items(), [])

    def test_the_default_is_to_say_yes_only_if_the_strategy_grows(self):
        self.assertTrue(Grower().may_consume(None, None))
        self.assertFalse(Fixed().may_consume(None, None))


class ReleaseTests(RetentionCase):
    def setUp(self):
        super().setUp()
        self.make_outputs(1000)
        self.finish_all()

    def release(self):
        ledger = self.fresh()
        result = retention.plan(ledger, groups.everything(ledger))
        return retention.release(ledger, result.items)

    def test_the_files_are_removed_and_what_is_kept_is_not(self):
        rundir = self.find("E", "gen").analysis.rundir
        self.release()
        self.assertFalse(os.path.exists(os.path.join(rundir, "big.dat")))
        self.assertFalse(os.path.exists(os.path.join(rundir, "tree")))
        self.assertTrue(os.path.exists(os.path.join(rundir, "final.txt")))

    def test_each_release_is_recorded_with_its_size_hash_reason_and_time(self):
        self.release()
        records = {r["asset"]: r for r in retention.released(self.find("E", "gen").analysis)}
        big = records["big"]
        self.assertEqual(big["size"], 1000)
        self.assertEqual(big["paths"], ["big.dat"])
        self.assertEqual(list(big["hash"].values()), [hashlib.sha256(b"x" * 1000).hexdigest()])
        self.assertIn("until_consumed", big["reason"])
        self.assertRegex(big["released"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertIsNone(records["tree"]["hash"])  # a directory has no one hash

    def test_the_record_is_in_the_ledger(self):
        self.release()
        self.assertEqual(retention.released_names(self.find("E", "gen", self.fresh()).analysis), {"big", "tree"})

    def test_it_is_audited(self):
        self.release()
        records = [r for r in self.fresh().audit_log() if r.action == "release"]
        self.assertEqual(sorted(r.target for r in records), ["E/gen", "E/gen"])

    def test_it_is_refused_when_the_project_switches_it_off(self):
        ledger = self.fresh()
        result = retention.plan(ledger, groups.everything(ledger))
        with patch.object(retention, "enabled", return_value=False):
            with self.assertRaises(RuntimeError):
                retention.release(ledger, result.items)
        self.assertTrue(os.path.exists(os.path.join(self.find("E", "gen").analysis.rundir, "big.dat")))

    def test_a_released_output_is_not_a_missing_one(self):
        gen = self.find("E", "gen").analysis
        gen.pipeline.detect_completion()  # (it has not run: no exit status, but the outputs are there)
        self.release()
        gen = self.find("E", "gen").analysis
        self.assertTrue(gen.pipeline.detect_completion())

    def test_an_output_which_is_missing_and_was_not_released_is_missing(self):
        gen = self.find("E", "gen").analysis
        os.remove(os.path.join(gen.rundir, "big.dat"))
        self.assertFalse(gen.pipeline.detect_completion())

    def test_a_consumer_which_asks_for_a_released_asset_is_told_so(self):
        self.release()
        use = self.find("E", "use").analysis
        with self.assertRaisesRegex(CommandError, "released to save space.*asimov analysis rerun"):
            use.pipeline.resolve_command()


class RerunTests(RetentionCase):
    def setUp(self):
        super().setUp()
        self.make_outputs()
        self.finish_all()
        ledger = self.fresh()
        retention.release(ledger, retention.plan(ledger, groups.everything(ledger)).items)

    def test_what_is_needed_and_was_released_is_found(self):
        ledger = self.fresh()
        members = groups.everything(ledger)
        use = groups.find(ledger, "E", "use", members)
        self.assertEqual(retention.pruned_inputs([use], members), [("E/use", "E/gen", "big")])

    def test_running_the_maker_again_too_is_enough(self):
        ledger = self.fresh()
        members = groups.everything(ledger)
        chosen = [groups.find(ledger, "E", "gen", members), groups.find(ledger, "E", "use", members)]
        self.assertEqual(retention.pruned_inputs(chosen, members), [])

    def test_regenerate_adds_what_makes_it(self):
        ledger = self.fresh()
        members = groups.everything(ledger)
        use = groups.find(ledger, "E", "use", members)
        self.assertEqual([m.label for m in retention.regenerate([use], members)], ["E/use", "E/gen"])

    def test_the_command_refuses_and_says_what_is_missing(self):
        result = self.cli("rerun", "E", "use", "--yes")
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("E/use needs big of E/gen", result.output)
        self.assertEqual(groups.find(self.fresh(), "E", "use").status, "complete")

    def test_the_command_can_regenerate(self):
        result = self.cli("rerun", "E", "use", "--regenerate", "--yes")
        self.assertEqual(result.exit_code, 0, result.output)
        ledger = self.fresh()
        self.assertEqual(groups.find(ledger, "E", "gen").status, "ready")
        self.assertEqual(groups.find(ledger, "E", "use").status, "ready")
        self.assertNotIn("released", groups.find(ledger, "E", "gen").analysis.meta)

    def test_downstream_of_the_maker_needs_nothing_regenerated(self):
        result = self.cli("rerun", "E", "gen", "--downstream", "--yes")
        self.assertEqual(result.exit_code, 0, result.output)

    def cli(self, *arguments):
        with patch("asimov.cli.analysis.ledger", self.fresh()):
            return CliRunner().invoke(analysis_cli.analysis, list(arguments))


class CommandTests(RetentionCase):
    def setUp(self):
        super().setUp()
        self.make_outputs(2000)
        self.finish_all()

    def cli(self, *arguments, **kwargs):
        with patch("asimov.cli.analysis.ledger", self.fresh()):
            return CliRunner().invoke(analysis_cli.analysis, list(arguments), **kwargs)

    def test_du_lists_each_analysis_and_a_total(self):
        result = self.cli("du")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("E/gen", result.output)
        self.assertIn("3 analyses", result.output)
        self.assertIn("kB on disk", result.output)

    def test_prune_dry_run_releases_nothing(self):
        result = self.cli("prune", "--dry-run")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Release 2 outputs", result.output)
        self.assertIn("Dry run", result.output)
        self.assertTrue(os.path.exists(os.path.join(self.find("E", "gen").analysis.rundir, "big.dat")))

    def test_prune_asks_and_a_no_releases_nothing(self):
        result = self.cli("prune", input="n\n")
        self.assertIn("Go ahead?", result.output)
        self.assertTrue(os.path.exists(os.path.join(self.find("E", "gen").analysis.rundir, "big.dat")))

    def test_prune_with_yes_releases(self):
        result = self.cli("prune", "--yes")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Released 2 outputs", result.output)
        self.assertFalse(os.path.exists(os.path.join(self.find("E", "gen").analysis.rundir, "big.dat")))

    def test_prune_says_what_it_kept_and_why(self):
        self.change("F", "far", "running")
        result = self.cli("prune", "--dry-run")
        self.assertIn("Kept:", result.output)
        self.assertIn("F/far still to finish", result.output)
        self.assertIn("Nothing to release.", result.output)

    def test_prune_is_refused_when_switched_off(self):
        with patch.object(retention, "enabled", return_value=False):
            result = self.cli("prune", "--yes")
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("switched off", result.output)

    def test_prune_of_a_group_which_does_not_exist_fails(self):
        self.assertNotEqual(self.cli("prune", "--group", "nope", "--yes").exit_code, 0)

    def test_running_an_analysis_again_forgets_what_was_released(self):
        self.cli("prune", "--yes")
        self.assertIn("released", self.find("E", "gen").analysis.meta)
        groups.reset(self.fresh(), [self.find("E", "gen")])
        meta = self.find("E", "gen").analysis.meta
        self.assertNotIn("released", meta)
        self.assertNotIn("assets", meta)


class ReviewTests(RetentionCase):
    """What a review of the first version found."""

    def setUp(self):
        super().setUp()
        self.make_outputs()
        self.finish_all()

    def cli(self, *arguments, **kwargs):
        with patch("asimov.cli.analysis.ledger", self.fresh()):
            return CliRunner().invoke(analysis_cli.analysis, list(arguments), **kwargs)

    def only_gen(self, paths):
        """gen's pipeline says it made these; no other analysis made anything."""
        return patch.object(
            type(self.find("E", "gen").analysis.pipeline),
            "output_paths",
            autospec=True,
            side_effect=lambda pipe: paths if pipe.production.name == "gen" else {},
        )

    # Nothing is released which has become needed since the plan was made

    def test_what_is_needed_again_while_the_prompt_is_open_is_not_released(self):
        from asimov.cli import analysis as module

        original = module.click.confirm

        def meanwhile(*a, **k):
            # another command runs the consumer again, while the question is on the screen
            self.change("E", "use", "ready")
            return True

        with patch.object(module.click, "confirm", side_effect=meanwhile):
            result = self.cli("prune")
        self.assertIn("can no longer be released", result.output)
        self.assertTrue(os.path.exists(os.path.join(self.find("E", "gen").analysis.rundir, "big.dat")))
        self.assertEqual(retention.released_names(self.find("E", "gen").analysis), set())

    # Something which would release a kept output with it

    def test_a_directory_which_holds_a_kept_output_is_not_released(self):
        gen = self.find("E", "gen").analysis
        with open(os.path.join(gen.rundir, "tree", "final.txt"), "w") as handle:
            handle.write("keep me")
        paths = {
            "tree": os.path.join(gen.rundir, "tree"),
            "final": os.path.join(gen.rundir, "tree", "final.txt"),
            "big": os.path.join(gen.rundir, "big.dat"),
        }
        with self.only_gen(paths):
            ledger = self.fresh()
            result = retention.plan(ledger, groups.everything(ledger))
        self.assertEqual(sorted(i.asset for i in result.items), ["big"])
        self.assertTrue(any("overlaps" in why and "kept" in why for _, a, why in result.kept if a == "tree"))

    def test_two_names_for_one_file_where_one_is_kept(self):
        gen = self.find("E", "gen").analysis
        big = os.path.join(gen.rundir, "big.dat")
        paths = {"big": big, "final": big}  # final (keep) is the same file
        with self.only_gen(paths):
            ledger = self.fresh()
            result = retention.plan(ledger, groups.everything(ledger))
        self.assertEqual(result.items, [])

    def test_an_output_which_is_the_results_store_itself_is_not_released(self):
        gen = self.find("E", "gen").analysis
        store = os.path.join(gen.rundir, "tree")
        with patch.object(retention, "_store_root", return_value=os.path.realpath(store)):
            self.assertNotIn(("E/gen", "tree"), self.released_items())
            self.assertTrue(any("results store" in why for _, a, why in self.plan().kept if a == "tree"))

    def test_a_directory_which_contains_the_results_store_is_not_released(self):
        gen = self.find("E", "gen").analysis
        store = os.path.join(gen.rundir, "tree", "sub")
        with patch.object(retention, "_store_root", return_value=os.path.realpath(store)):
            self.assertNotIn(("E/gen", "tree"), self.released_items())

    # A new run starts afresh

    def test_setting_ready_by_hand_forgets_what_was_released(self):
        retention.release(self.fresh(), self.plan().items)
        result = self.cli("set", "--group", "nope", "--status", "ready", "--yes")  # (no such group)
        self.assertNotEqual(result.exit_code, 0)
        groups.set_status(self.fresh(), [self.find("E", "gen")], "ready")
        self.assertNotIn("released", self.find("E", "gen").analysis.meta)

    def test_production_set_ready_forgets_what_was_released(self):
        from asimov.cli import production

        retention.release(self.fresh(), self.plan().items)
        with patch("asimov.cli.production.ledger", new=self.fresh()):
            result = CliRunner().invoke(production.set, ["E", "gen", "-s", "ready"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertNotIn("released", self.find("E", "gen").analysis.meta)

    def test_submitting_forgets_what_was_released(self):
        retention.release(self.fresh(), self.plan().items)
        gen = self.find("E", "gen").analysis
        self.assertIn("released", gen.meta)
        with patch("asimov.pipelines.command.JobDescription"), patch.object(
            type(gen.pipeline), "scheduler", new_callable=MagicMock
        ) as scheduler:
            scheduler.submit.return_value = 7
            gen.pipeline.submit_dag()
        self.assertNotIn("released", gen.meta)
        self.assertNotIn("assets", gen.meta)

    def test_a_released_output_is_not_present_for_a_run_which_has_not_made_it(self):
        retention.release(self.fresh(), self.plan().items)
        gen = self.find("E", "gen").analysis
        gen.pipeline.production.meta.pop("released")  # a new run has been started
        self.assertFalse(gen.pipeline.detect_completion())

    # A released contribution is missing even when another provider has the name

    def test_another_provider_of_the_same_name_does_not_hide_a_released_one(self):
        self.apply(
            "kind: analysis\nname: other\ncommand: [true]\noutputs:\n  big: other.dat\n---\n"
            "kind: analysis\nname: both\ncommand: [cat, '{inputs.big}']\nneeds: [gen, other]\n",
            "E",
        )
        self.make_outputs()
        self.finish_all()  # (applying more to the subject starts them from ready again)
        other = self.find("E", "other").analysis
        os.makedirs(other.rundir, exist_ok=True)
        with open(os.path.join(other.rundir, "other.dat"), "w") as handle:
            handle.write("surviving")
        self.change("E", "other", "complete")
        self.change("E", "both", "ready")
        self.assertEqual(len(self.find("E", "both").analysis.pipeline.resolve_command()), 3)  # both are there
        self.change("E", "both", "complete")  # (it has run; gen's output is no longer needed)
        retention.release(self.fresh(), self.plan().items)
        self.change("E", "both", "ready")  # and now it is to be run again
        with self.assertRaisesRegex(CommandError, "released to save space"):
            self.find("E", "both").analysis.pipeline.resolve_command()

    # A failure part of the way through does not lose the record of what went

    def test_what_was_removed_is_recorded_when_a_later_removal_fails(self):
        items = self.plan().items
        real = os.remove
        calls = []

        def refuse_big(path):
            calls.append(path)
            if path.endswith("big.dat"):
                raise PermissionError("not allowed")
            real(path)

        with patch("asimov.retention.os.remove", side_effect=refuse_big):
            with self.assertRaisesRegex(RuntimeError, "could not be released.*big"):
                retention.release(self.fresh(), items)
        gen = self.find("E", "gen").analysis
        self.assertEqual(retention.released_names(gen), {"tree"})  # tree went, and is recorded
        self.assertTrue(os.path.exists(os.path.join(gen.rundir, "big.dat")))
        self.assertFalse(os.path.exists(os.path.join(gen.rundir, "tree")))

    def test_an_output_with_several_paths_records_the_ones_which_went(self):
        gen = self.find("E", "gen").analysis
        a, b = os.path.join(gen.rundir, "a.dat"), os.path.join(gen.rundir, "b.dat")
        for path in (a, b):
            with open(path, "w") as handle:
                handle.write("data")
        item = retention.Item(self.find("E", "gen"), "pair", [a, b], 8, "test")
        real = os.remove

        def refuse_b(path):
            if path == b:
                raise PermissionError("no")
            real(path)

        with patch("asimov.retention.os.remove", side_effect=refuse_b):
            with self.assertRaises(RuntimeError):
                retention.release(self.fresh(), [item])
        record = retention.released(self.find("E", "gen").analysis)[-1]
        self.assertEqual(record["paths"], ["a.dat"])
        self.assertTrue(record["partial"])
        self.assertTrue(os.path.exists(b))

    def test_the_command_says_what_could_not_be_released(self):
        with patch("asimov.retention.os.remove", side_effect=PermissionError("no")):
            result = self.cli("prune", "--yes")
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("could not be released", result.output)

    def test_each_file_is_hashed_once(self):
        with patch.object(retention, "hash_of", wraps=retention.hash_of) as hashed:
            retention.release(self.fresh(), self.plan().items)
        big = [c for c in hashed.call_args_list if str(c.args[0]).endswith("big.dat")]
        self.assertEqual(len(big), 1)

    # A project analysis and a subject's analysis may both need an analysis

    def test_a_producer_with_a_subject_and_a_project_consumer_can_be_planned(self):
        members = groups.everything(self.fresh())
        project = types.SimpleNamespace(
            name="pa", status="complete", meta={}, event=None, pipeline=None, rundir=None,
            _dependency_analyses=lambda: [self.find("E", "gen").analysis],
        )
        members.append(groups.Member(project, None))
        after = groups.dependents(members)
        self.assertEqual(after[("E", "gen")], [("E", "use"), ("F", "far"), (None, "pa")])
        self.assertEqual(
            [m.label for m in groups.downstream(None, groups.find(self.fresh(), "E", "gen", members), members)][:2],
            ["E/gen", "E/use"],
        )

    # An input list which is known to be empty is not an unknown one

    def test_a_command_which_asks_for_nothing_does_not_need_what_was_released(self):
        retention.release(self.fresh(), self.plan().items)
        ledger = self.fresh()
        members = groups.everything(ledger)
        far = groups.find(ledger, "F", "far", members)
        self.assertEqual(retention.pruned_inputs([far], members), [])
        self.assertEqual([m.label for m in retention.regenerate([far], members)], ["F/far"])
        self.assertEqual(self.cli("rerun", "F", "far", "--yes").exit_code, 0)

    def test_a_pipeline_which_does_not_declare_its_inputs_may_need_anything(self):
        retention.release(self.fresh(), self.plan().items)
        ledger = self.fresh()
        members = groups.everything(ledger)
        far = groups.find(ledger, "F", "far", members)
        with patch.object(type(far.analysis.pipeline), "declares_inputs", False):
            self.assertEqual(
                [(u, p) for u, p, _ in retention.pruned_inputs([far], members)], [("F/far", "E/gen")] * 2
            )


class ReportTests(unittest.TestCase):
    def test_the_panel_says_how_much_the_outputs_take(self):
        from asimov.report_groups import panel_html

        analysis = types.SimpleNamespace(
            name="a",
            status="complete",
            meta={"assets": {"x": {"size": 2_500_000, "files": 1}}, "released": [{"asset": "y", "size": 1_000_000}]},
        )
        html = panel_html("g", "t", [groups.Member(analysis, "S")], None)
        self.assertIn("2.5 MB of outputs, 1.0 MB released", html)

    def test_a_cell_says_how_big_the_analysis_is(self):
        from asimov.report_groups import panel_html

        analysis = types.SimpleNamespace(
            name="a", status="complete", meta={"assets": {"x": {"size": 2_500_000}}, "round": 1, "stream": "s"}
        )
        html = panel_html(
            "g", "t", [groups.Member(analysis, "S")], {"blueprint": {"report": {"rows": "stream", "columns": "round"}}}
        )
        self.assertIn("S/a: complete (2.5 MB)", html)

    def test_nothing_is_said_when_nothing_is_recorded(self):
        from asimov.report_groups import panel_html

        analysis = types.SimpleNamespace(name="a", status="ready", meta={})
        self.assertNotIn("of outputs", panel_html("g", "t", [groups.Member(analysis, "S")], None))


if __name__ == "__main__":
    unittest.main()
