"""
The built-in command pipeline (#236): an analysis with a ``command`` runs it.
"""
import configparser
import os
import shutil
import stat
import tempfile
import unittest
from unittest.mock import patch

import asimov
from asimov import features
from asimov.analysis import SimpleAnalysis
from asimov.cli.application import apply_page
from asimov.cli.project import make_project
from asimov.ledger import YAMLLedger
from asimov.pipelines import known_pipelines
from asimov.pipelines import command as command_module
from asimov.pipelines.command import (
    CommandError,
    CommandNotAllowed,
    CommandPipeline,
    asset_paths,
    command_allowed,
)

EVENT = "kind: event\nname: EvA\ninterferometers: [H1]\n"


def gate(**options):
    """A project configuration with the command pipeline's section."""
    parser = configparser.ConfigParser()
    parser.add_section("pipelines.command")
    for key, value in options.items():
        parser.set("pipelines.command", key, value)
    return patch.object(command_module, "config", parser)


class CommandCase(unittest.TestCase):
    def setUp(self):
        self.cwd = os.getcwd()
        self.root = tempfile.mkdtemp()
        os.chdir(self.root)
        make_project(name="Test project", root=self.root, engine="yamlfile")
        self.ledger = YAMLLedger(".asimov/ledger.yml")
        self.apply(EVENT)
        self.gate = gate(enabled="true")
        self.gate.start()

    def tearDown(self):
        self.gate.stop()
        os.chdir(self.cwd)
        shutil.rmtree(self.root, ignore_errors=True)

    def apply(self, *documents, subject=None):
        with open("blueprint.yaml", "w") as handle:
            handle.write("---\n".join(documents))
        return apply_page("blueprint.yaml", event=subject, ledger=self.ledger)

    def analyses(self):
        return {a.name: a for a in YAMLLedger(".asimov/ledger.yml").get_event("EvA")[0].productions}

    def command(self, name="step", **fields):
        text = f"kind: analysis\nname: {name}\n"
        for key, value in fields.items():
            text += f"{key}: {value}\n"
        return text

    def pipeline(self, name):
        return self.analyses()[name].pipeline


class ConstructionTests(CommandCase):
    def test_a_command_without_a_pipeline_uses_the_command_pipeline(self):
        self.apply(self.command(command="[echo, hi]"), subject="EvA")
        self.assertIsInstance(self.pipeline("step"), CommandPipeline)

    def test_naming_the_pipeline_is_the_same(self):
        self.apply(self.command("a", command="[echo, hi]"), self.command("b", pipeline="command", command="[echo, hi]"), subject="EvA")
        self.assertIsInstance(self.pipeline("a"), CommandPipeline)
        self.assertIsInstance(self.pipeline("b"), CommandPipeline)
        self.assertEqual(self.pipeline("a").name, self.pipeline("b").name)

    def test_it_is_registered(self):
        self.assertIs(known_pipelines["command"], CommandPipeline)

    def test_neither_a_pipeline_nor_a_command_is_still_an_error(self):
        with self.assertRaises(Exception) as caught:
            self.apply(self.command(status="ready"), subject="EvA")
        self.assertIn("required parameters", str(caught.exception).lower())

    def test_it_can_be_needed_by_pipeline_name(self):
        self.apply(
            self.command("a", command="[echo, hi]"),
            "kind: analysis\nname: b\npipeline: simpletestpipeline\nneeds:\n  - pipeline: command\n",
            subject="EvA",
        )
        self.assertEqual([d.name for d in self.analyses()["b"].dependency_objects], ["a"])

    def test_the_command_may_be_a_string(self):
        self.apply(self.command(command="'echo  hi there'"), subject="EvA")
        self.assertEqual(self.pipeline("step").command_template(), ["echo", "hi", "there"])

    def test_a_word_which_is_a_number_is_a_word(self):
        self.apply(self.command(command="[sleep, 1]"), subject="EvA")
        self.assertEqual(self.pipeline("step").command_template(), ["sleep", "1"])


class PlaceholderTests(CommandCase):
    def make(self, command, outputs="", needs=""):
        """``prep`` provides assets; ``step`` runs ``command``."""
        self.apply(
            self.command("prep", command="[true]"),
            self.command("step", command=command) + outputs + needs,
            subject="EvA",
        )
        prep = self.analyses()["prep"]
        os.makedirs(prep.rundir, exist_ok=True)
        return self.pipeline("step")

    def provide(self, **assets):
        prep = self.analyses()["prep"]
        patcher = patch.object(type(prep.pipeline), "collect_assets", return_value=assets)
        patcher.start()
        self.addCleanup(patcher.stop)

    NEEDS = "needs: [prep]\n"

    def test_an_input_is_the_asset_of_what_is_needed(self):
        step = self.make("[cat, '{inputs.data}']", needs=self.NEEDS)
        self.provide(data="/x/data.txt")
        self.assertEqual(step.resolve_command(), ["cat", "/x/data.txt"])

    def test_a_list_is_several_words(self):
        step = self.make("[cat, '{inputs.frames}']", needs=self.NEEDS)
        self.provide(frames=["/x/a.gwf", "/x/b.gwf"])
        self.assertEqual(step.resolve_command(), ["cat", "/x/a.gwf", "/x/b.gwf"])

    def test_a_mapping_is_all_its_paths_and_a_label_picks_one(self):
        step = self.make("[cat, '{inputs.psds}', '--h1={inputs.psds.H1}']", needs=self.NEEDS)
        self.provide(psds={"L1": "/x/l1.dat", "H1": "/x/h1.dat"})
        self.assertEqual(step.resolve_command(), ["cat", "/x/h1.dat", "/x/l1.dat", "--h1=/x/h1.dat"])

    def test_a_mapping_of_lists_flattens(self):
        step = self.make("[cat, '{inputs.frames}']", needs=self.NEEDS)
        self.provide(frames={"H1": ["/x/1", "/x/2"], "L1": "/x/3"})
        self.assertEqual(step.resolve_command(), ["cat", "/x/1", "/x/2", "/x/3"])

    def test_a_name_may_have_a_space(self):
        step = self.make("[cat, '{inputs.xml psds}']", needs=self.NEEDS)
        self.provide(**{"xml psds": "/x/psd.xml"})
        self.assertEqual(step.resolve_command(), ["cat", "/x/psd.xml"])

    def test_an_output_is_in_the_run_directory(self):
        step = self.make("[touch, '{outputs.out}']", outputs="outputs:\n  out: result.txt\n")
        self.assertEqual(
            step.resolve_command(), ["touch", os.path.join(os.path.abspath(step.production.rundir), "result.txt")]
        )

    def test_an_absolute_output_is_left_alone(self):
        step = self.make("[touch, '{outputs.out}']", outputs="outputs:\n  out: {path: /tmp/elsewhere.txt}\n")
        self.assertEqual(step.resolve_command(), ["touch", "/tmp/elsewhere.txt"])

    def test_an_input_nobody_provides_is_an_error_which_says_so(self):
        step = self.make("[cat, '{inputs.data}']", needs=self.NEEDS)
        self.provide()
        with self.assertRaisesRegex(CommandError, "inputs.data.*prep"):
            step.resolve_command()

    def test_an_undeclared_output_is_an_error(self):
        step = self.make("[touch, '{outputs.out}']")
        with self.assertRaisesRegex(CommandError, "no output called 'out'"):
            step.resolve_command()

    def test_several_paths_inside_a_word_is_an_error(self):
        step = self.make("[cat, '--files={inputs.frames}']", needs=self.NEEDS)
        self.provide(frames=["/x/a", "/x/b"])
        with self.assertRaisesRegex(CommandError, "2 paths"):
            step.resolve_command()

    def test_the_executable_cannot_be_a_placeholder(self):
        step = self.make("['{inputs.tool}', --help]", needs=self.NEEDS)
        self.provide(tool="/x/tool")
        with self.assertRaisesRegex(CommandError, "executable"):
            step.resolve_command()

    def test_a_label_which_is_not_there_is_an_error(self):
        step = self.make("[cat, '{inputs.psds.V1}']", needs=self.NEEDS)
        self.provide(psds={"H1": "/x/h1.dat"})
        with self.assertRaises(CommandError):
            step.resolve_command()

    def test_the_inputs_and_outputs_are_declared_to_asimov(self):
        step = self.make(
            "[cp, '{inputs.data}', '{outputs.out}']", outputs="outputs:\n  out: o.txt\n", needs=self.NEEDS
        )
        self.assertEqual(step.get_actual_inputs(step.production), ["data"])
        self.assertEqual(step.get_actual_outputs(step.production), ["out"])

    def test_an_unprovided_input_is_warned_about_before_anything_runs(self):
        step = self.make("[cat, '{inputs.data}']", needs=self.NEEDS)
        self.provide()
        with self.assertWarnsRegex(UserWarning, "requires 'data'"):
            step.production.validate_needs()

    def test_a_broken_declaration_does_not_stop_reading_the_declarations(self):
        step = self.make("[touch, '{outputs.out}']", outputs="outputs:\n  out: {}\n")
        with self.assertLogs(level="WARNING"):
            self.assertEqual(step.get_actual_outputs(step.production), [])


class AssetPathTests(unittest.TestCase):
    def test_shapes(self):
        self.assertEqual(asset_paths(None), [])
        self.assertEqual(asset_paths("a"), ["a"])
        self.assertEqual(asset_paths(["a", "b"]), ["a", "b"])
        self.assertEqual(asset_paths({"L1": "l", "H1": ["h", "i"]}), ["h", "i", "l"])
        self.assertEqual(asset_paths(os.path.join("a", "b")), [os.path.join("a", "b")])


class GateTests(CommandCase):
    def setUp(self):
        super().setUp()
        self.apply(self.command(command="[echo, hi]"), subject="EvA")

    def test_it_is_off_without_configuration(self):
        with gate():
            with self.assertRaisesRegex(CommandNotAllowed, "not enabled"):
                command_allowed("echo")

    def test_it_is_off_when_not_enabled(self):
        with gate(enabled="false"):
            with self.assertRaises(CommandNotAllowed):
                command_allowed("echo")

    def test_it_is_on_when_enabled(self):
        command_allowed("echo")

    def test_an_allow_list_is_matched_on_the_executable_as_written(self):
        with gate(enabled="true", allowed_executables="gwaith_*, python"):
            command_allowed("gwaith_fit")
            command_allowed("python")
            for refused in ("rm", "/usr/bin/python", "python3"):
                with self.assertRaises(CommandNotAllowed, msg=refused):
                    command_allowed(refused)

    def test_building_is_refused_when_off(self):
        with gate():
            with self.assertRaises(CommandNotAllowed):
                self.pipeline("step").build_dag()

    def test_submitting_is_refused_when_off(self):
        with gate():
            with self.assertRaises(CommandNotAllowed):
                self.pipeline("step").submit_dag()

    def test_a_dry_run_is_refused_when_off_too(self):
        with gate():
            with self.assertRaises(CommandNotAllowed):
                self.pipeline("step").submit_dag(dryrun=True)

    def test_it_applies_to_both_spellings(self):
        self.apply(self.command("named", pipeline="command", command="[echo, hi]"), subject="EvA")
        with gate():
            with self.assertRaises(CommandNotAllowed):
                self.pipeline("named").build_dag()

    def test_a_subclass_which_fixes_the_executable_is_not_gated(self):
        class Fixed(CommandPipeline):
            arbitrary_command = False

        pipeline = Fixed(self.analyses()["step"])
        with gate():
            pipeline._check_allowed(["anything"])

    def test_the_shipped_configuration_does_not_enable_it(self):
        shipped = configparser.ConfigParser()
        shipped.read(os.path.join(os.path.dirname(asimov.__file__), "asimov.conf"))
        self.assertFalse(shipped.has_option("pipelines.command", "enabled"))

    def test_a_new_project_enables_it_in_its_own_configuration(self):
        parser = configparser.ConfigParser()
        parser.read(os.path.join(self.root, ".asimov", "asimov.conf"))
        self.assertEqual(parser.get("pipelines.command", "enabled"), "true")


class BuildAndCompletionTests(CommandCase):
    def make(self, command, outputs=""):
        self.apply(self.command(command=command) + outputs, subject="EvA")
        pipeline = self.pipeline("step")
        os.makedirs(pipeline.production.rundir, exist_ok=True)
        return pipeline

    def test_the_script_runs_the_command_without_a_shell(self):
        pipeline = self.make("[echo, 'a b; rm -rf /', '$HOME']", "outputs:\n  o: o.txt\n")
        pipeline.build_dag()
        script = os.path.join(pipeline.production.rundir, "command.sh")
        text = open(script).read()
        self.assertIn("echo 'a b; rm -rf /' '$HOME'", text)
        self.assertTrue(os.stat(script).st_mode & stat.S_IXUSR)

    def test_a_dry_run_writes_nothing(self):
        pipeline = self.make("[echo, hi]")
        self.assertEqual(pipeline.build_dag(dryrun=True), ["echo", "hi"])
        self.assertFalse(os.path.exists(os.path.join(pipeline.production.rundir, "command.sh")))

    def test_it_is_complete_when_what_it_declared_exists(self):
        pipeline = self.make("[true]", "outputs:\n  o: o.txt\n")
        self.assertFalse(pipeline.detect_completion())
        open(pipeline.output_path("o"), "w").close()
        self.assertTrue(pipeline.detect_completion())

    def test_a_failed_command_is_not_complete_even_if_the_output_exists(self):
        pipeline = self.make("[true]", "outputs:\n  o: o.txt\n")
        open(pipeline.output_path("o"), "w").close()
        open(os.path.join(pipeline.production.rundir, ".asimov-exit-status"), "w").write("3\n")
        self.assertFalse(pipeline.detect_completion())
        with self.assertRaisesRegex(CommandError, "status 3"):
            pipeline.resurrect()

    def test_without_outputs_it_is_complete_when_it_is_known_to_have_finished(self):
        pipeline = self.make("[true]")
        self.assertFalse(pipeline.detect_completion())
        status = os.path.join(pipeline.production.rundir, ".asimov-exit-status")
        open(status, "w").write("0\n")
        self.assertTrue(pipeline.detect_completion())

    def test_a_command_which_has_not_finished_is_left_alone_by_resurrect(self):
        self.make("[true]").resurrect()

    def test_assets_are_the_outputs_which_exist(self):
        pipeline = self.make("[true]", "outputs:\n  a: a.txt\n  b: {path: b.txt}\n")
        open(pipeline.output_path("a"), "w").close()
        self.assertEqual(pipeline.collect_assets(), {"a": pipeline.output_path("a")})

    def test_completion_is_complete(self):
        pipeline = self.make("[true]")
        pipeline.after_completion()
        self.assertEqual(pipeline.production.status, "complete")

    def test_a_subclass_can_ask_for_more(self):
        class Strict(CommandPipeline):
            def command_succeeded(self):
                return False

        pipeline = Strict(self.make("[true]", "outputs:\n  o: o.txt\n").production)
        open(pipeline.output_path("o"), "w").close()
        self.assertFalse(pipeline.detect_completion())

    def test_resources_are_read_from_the_scheduler_block(self):
        pipeline = self.make("[true]", "scheduler:\n  request memory: 4GB\n  request_cpus: 2\n  accounting group: ligo.dev\n")
        self.assertEqual(
            pipeline._resources(), {"memory": "4GB", "cpus": 2, "accounting_group": "ligo.dev"}
        )


class FeatureTests(CommandCase):
    def test_using_it_is_recorded_and_warned_about_once(self):
        plan = self.apply(self.command(command="[echo, hi]"), subject="EvA")
        self.assertTrue(any("'command:'" in p.message for p in plan.problems))
        self.assertIn("command-pipeline", features.recorded(YAMLLedger(".asimov/ledger.yml")))
        again = self.apply(self.command("second", command="[echo, hi]"), subject="EvA")
        self.assertFalse(any("'command:'" in p.message for p in again.problems))

    def test_other_pipelines_do_not_record_it(self):
        self.apply("kind: analysis\nname: x\npipeline: simpletestpipeline\n", subject="EvA")
        self.assertNotIn("command-pipeline", features.recorded(YAMLLedger(".asimov/ledger.yml")))


class StrategyTests(unittest.TestCase):
    def test_a_strategy_document_with_a_command_needs_no_pipeline(self):
        from asimov import strategies

        source = inspect_source(strategies)
        self.assertIn('"command" in document', source)


def inspect_source(module):
    import inspect

    return inspect.getsource(module)


if __name__ == "__main__":
    unittest.main()
