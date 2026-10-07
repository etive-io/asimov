"""
Plugin strategies (#232): ``strategy: {type: <name>}`` selects a strategy which
a plugin registers, and which expands the blueprint into a graph of analyses.

The matrix strategy is not changed (``test_strategies.py`` passes unmodified);
the first group here checks that a ``strategy:`` is still told apart from a
plugin one the way the issue says.
"""
import logging
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import yaml

from asimov.cli.application import apply_page
from asimov.cli.project import make_project
from asimov.ledger import YAMLLedger
from asimov.strategies import (
    Strategy,
    StrategyContext,
    StrategyError,
    expand_strategy,
    is_plugin_strategy,
    strategy_plugins,
    strategy_stamp,
)
from asimov.strategies_builtin import ChainStrategy

EVENT = "kind: event\nname: EvA\ninterferometers: [H1]\n"


class FakeEntryPoint:
    def __init__(self, name, target=None, error=None):
        self.name = name
        self._target = target
        self._error = error

    def load(self):
        if self._error:
            raise self._error
        return self._target


def plugins(**strategies):
    """Make ``strategy_plugins`` find these strategies, by name."""
    return patch(
        "asimov.strategies.entry_points",
        return_value=[FakeEntryPoint(name, cls) for name, cls in strategies.items()],
    )


def blueprint(**strategy):
    return {
        "kind": "analysis",
        "name": "fit",
        "pipeline": "simpletestpipeline",
        "status": "ready",
        "strategy": strategy,
    }


def PIPELINE(name):
    """The least a document needs to be applied."""
    return {"name": name, "pipeline": "simpletestpipeline"}


class Emit(Strategy):
    """A strategy which emits whatever its test sets."""

    documents = None
    seen = None

    def expand(self, blueprint, context):
        type(self).seen = (blueprint, context)
        return type(self).documents(blueprint, context)


class WhichStrategyTests(unittest.TestCase):
    def test_a_type_which_is_a_string_selects_a_plugin(self):
        self.assertTrue(is_plugin_strategy({"type": "chain", "length": 2}))

    def test_a_matrix_strategy_is_not_one(self):
        self.assertFalse(is_plugin_strategy({"waveform.approximant": ["a", "b"]}))

    def test_a_matrix_parameter_called_type_is_still_a_matrix(self):
        self.assertFalse(is_plugin_strategy({"type": ["a", "b"]}))
        documents = expand_strategy({"name": "x-{type}", "strategy": {"type": ["a", "b"]}})
        self.assertEqual([d["name"] for d in documents], ["x-a", "x-b"])

    def test_things_which_are_not_mappings_are_not_one(self):
        for value in (None, "chain", ["chain"], 3):
            self.assertFalse(is_plugin_strategy(value))

    def test_no_strategy_is_left_alone(self):
        document = {"name": "x"}
        self.assertEqual(expand_strategy(document), [document])


class RegistryTests(unittest.TestCase):
    def test_the_chain_strategy_is_registered_by_entry_point(self):
        self.assertIs(strategy_plugins()["chain"], ChainStrategy)

    def test_an_unknown_type_names_the_installed_strategies(self):
        with plugins(alpha=Emit, beta=Emit):
            with self.assertRaisesRegex(StrategyError, "Unknown strategy type 'nope'.*alpha, beta"):
                expand_strategy(blueprint(type="nope"))

    def test_with_none_installed_it_says_so(self):
        with plugins():
            with self.assertRaisesRegex(StrategyError, "installed strategies are: none"):
                expand_strategy(blueprint(type="nope"))

    def test_a_plugin_which_fails_to_load_is_skipped_with_a_warning(self):
        broken = FakeEntryPoint("broken", error=ImportError("no module"))
        working = FakeEntryPoint("working", Emit)
        with patch("asimov.strategies.entry_points", return_value=[broken, working]):
            with self.assertLogs("asimov.strategies", level="WARNING") as logged:
                found = strategy_plugins()
        self.assertEqual(list(found), ["working"])
        self.assertIn("broken", logged.output[0])


class ChainStrategyTests(unittest.TestCase):
    def expand(self, **spec):
        return expand_strategy(blueprint(type="chain", **spec))

    def test_it_makes_a_chain_each_needing_the_one_before(self):
        documents = self.expand(length=3)
        self.assertEqual([d["name"] for d in documents], ["fit-001", "fit-002", "fit-003"])
        self.assertNotIn("needs", documents[0])
        self.assertEqual(documents[1]["needs"], ["fit-001"])
        self.assertEqual(documents[2]["needs"], ["fit-002"])

    def test_the_length_defaults_to_three(self):
        self.assertEqual(len(self.expand()), 3)

    def test_the_rest_of_the_blueprint_is_copied(self):
        for document in self.expand(length=2):
            self.assertEqual(document["pipeline"], "simpletestpipeline")
            self.assertEqual(document["status"], "ready")

    def test_the_first_keeps_the_needs_of_the_blueprint(self):
        document = blueprint(type="chain", length=2)
        document["needs"] = ["other"]
        documents = expand_strategy(document)
        self.assertEqual(documents[0]["needs"], ["other"])
        self.assertEqual(documents[1]["needs"], ["fit-001"])

    def test_each_is_stamped_with_the_strategy_and_the_blueprint_name(self):
        for document in self.expand(length=2):
            self.assertEqual(document["strategy"], {"type": "chain", "id": "fit"})
            self.assertEqual(strategy_stamp(document), {"type": "chain", "id": "fit"})

    def test_it_is_the_same_each_time(self):
        self.assertEqual(self.expand(length=4), self.expand(length=4))

    def test_the_blueprint_is_not_changed(self):
        document = blueprint(type="chain", length=2)
        before = yaml.dump(document)
        expand_strategy(document)
        self.assertEqual(yaml.dump(document), before)

    def test_bad_options_are_refused(self):
        for options in ({"length": 0}, {"length": "3"}, {"length": True}, {"length": 2.5},
                        {"width": 2}):
            with self.subTest(options=options), self.assertRaises(StrategyError):
                self.expand(**options)


class WhatAPluginReturnsTests(unittest.TestCase):
    def expand(self, make):
        Emit.documents = staticmethod(make)
        with plugins(emit=Emit):
            return expand_strategy(blueprint(type="emit"))

    def test_a_valid_result_is_stamped(self):
        documents = self.expand(lambda b, c: [PIPELINE("a"), PIPELINE("b")])
        self.assertEqual([d["strategy"] for d in documents], [{"type": "emit", "id": "fit"}] * 2)

    def test_a_plugin_cannot_omit_or_forge_the_stamp(self):
        documents = self.expand(lambda b, c: [{**PIPELINE("a"), "strategy": {"type": "other", "id": "x"}}])
        self.assertEqual(documents[0]["strategy"], {"type": "emit", "id": "fit"})

    def test_an_exception_in_the_plugin_is_reported_as_a_strategy_error(self):
        def fail(b, c):
            raise RuntimeError("boom")

        with self.assertRaisesRegex(StrategyError, "'emit' could not be expanded: boom"):
            self.expand(fail)

    def test_validate_runs_before_expand(self):
        class Strict(Emit):
            def validate(self, spec):
                raise ValueError("bad spec")

        Emit.documents = staticmethod(lambda b, c: self.fail("expanded"))
        with plugins(emit=Strict), self.assertRaisesRegex(StrategyError, "bad spec"):
            expand_strategy(blueprint(type="emit"))

    def test_the_plugin_is_given_copies(self):
        def change(b, c):
            b["name"] = "changed"
            return [PIPELINE("a")]

        original = blueprint(type="emit")
        Emit.documents = staticmethod(change)
        with plugins(emit=Emit):
            expand_strategy(original)
        self.assertEqual(original["name"], "fit")

    def test_things_which_cannot_be_applied_are_refused(self):
        bad = {
            "nothing": lambda b, c: [],
            "not a list": lambda b, c: {"name": "a"},
            "not documents": lambda b, c: ["a"],
            "no name": lambda b, c: [{"pipeline": "x"}],
            "no pipeline": lambda b, c: [{"name": "a"}],
            "duplicate": lambda b, c: [PIPELINE("a"), PIPELINE("a")],
            "not an analysis": lambda b, c: [{**PIPELINE("a"), "kind": "event"}],
        }
        for label, make in bad.items():
            with self.subTest(label), self.assertRaises(StrategyError):
                self.expand(make)

    def test_a_kind_of_analysis_is_accepted_and_removed(self):
        documents = self.expand(lambda b, c: [{**PIPELINE("a"), "kind": "Analysis"}])
        self.assertNotIn("kind", documents[0])

    def test_the_blueprint_needs_a_name_to_identify_the_group(self):
        document = blueprint(type="chain")
        del document["name"]
        with self.assertRaisesRegex(StrategyError, "needs the blueprint to have a name"):
            expand_strategy(document)


class ContextTests(unittest.TestCase):
    def test_without_a_ledger_the_project_is_empty(self):
        context = StrategyContext()
        self.assertEqual(context.subjects(), [])
        self.assertEqual(context.analyses("EvA"), [])
        self.assertEqual(context.project, {})
        self.assertIsNone(context.event)

    def test_the_plugin_is_given_the_context(self):
        context = StrategyContext(event="EvA")
        Emit.documents = staticmethod(lambda b, c: [PIPELINE("a")])
        with plugins(emit=Emit):
            expand_strategy(blueprint(type="emit"), context)
        self.assertIs(Emit.seen[1], context)

    def test_it_has_a_logger(self):
        self.assertIsInstance(StrategyContext().logger, logging.Logger)


class AppliedStrategyCase(unittest.TestCase):
    """A real project to apply blueprints to."""

    def setUp(self):
        self.cwd = os.getcwd()
        self.root = tempfile.mkdtemp()
        os.chdir(self.root)
        make_project(name="Test project", root=self.root, engine="yamlfile")
        self.ledger = YAMLLedger(".asimov/ledger.yml")
        self.write("event.yaml", EVENT)
        apply_page("event.yaml", ledger=self.ledger)

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, name, text):
        with open(name, "w") as handle:
            handle.write(text)

    def apply(self, text, **kwargs):
        self.write("blueprint.yaml", text)
        apply_page("blueprint.yaml", event="EvA", ledger=self.ledger, **kwargs)

    def analyses(self):
        fresh = YAMLLedger(".asimov/ledger.yml")
        return {a.name: a for a in fresh.get_event("EvA")[0].productions}

    CHAIN = """kind: analysis
name: fit
pipeline: simpletestpipeline
status: ready
strategy:
  type: chain
  length: {length}
"""


class ApplyTests(AppliedStrategyCase):
    def test_the_analyses_are_made_with_their_needs(self):
        self.apply(self.CHAIN.format(length=3))
        analyses = self.analyses()
        self.assertEqual(sorted(analyses), ["fit-001", "fit-002", "fit-003"])
        self.assertEqual(analyses["fit-001"].dependencies, [])
        self.assertEqual(analyses["fit-002"].dependencies, ["fit-001"])
        self.assertEqual(analyses["fit-003"].dependencies, ["fit-002"])

    def test_the_stamp_is_in_the_ledger_and_survives_a_round_trip(self):
        self.apply(self.CHAIN.format(length=2))
        for analysis in self.analyses().values():
            self.assertEqual(analysis.meta["strategy"], {"type": "chain", "id": "fit"})
        ledger = YAMLLedger(".asimov/ledger.yml")
        ledger.update_event(ledger.get_event("EvA")[0])
        for analysis in self.analyses().values():
            self.assertEqual(analysis.meta["strategy"], {"type": "chain", "id": "fit"})
            self.assertEqual(
                analysis.to_dict()[analysis.name]["strategy"], {"type": "chain", "id": "fit"}
            )

    def test_applying_it_again_changes_nothing_and_is_not_an_error(self):
        self.apply(self.CHAIN.format(length=3))
        before = yaml.safe_load(open(".asimov/ledger.yml"))
        with patch("asimov.cli.application.click.echo") as echo:
            self.apply(self.CHAIN.format(length=3))
        self.assertEqual(yaml.safe_load(open(".asimov/ledger.yml")), before)
        text = " ".join(str(call.args[0]) for call in echo.call_args_list)
        self.assertNotIn("an analysis already exists", text)
        self.assertIn("3 of 3 analyses already existed", text)

    def test_raising_the_length_adds_only_the_new_analyses(self):
        self.apply(self.CHAIN.format(length=2))
        first = self.analyses()["fit-001"].to_dict()
        with patch("asimov.cli.application.click.echo") as echo:
            self.apply(self.CHAIN.format(length=4))
        analyses = self.analyses()
        self.assertEqual(sorted(analyses), ["fit-001", "fit-002", "fit-003", "fit-004"])
        self.assertEqual(analyses["fit-001"].to_dict(), first)
        self.assertEqual(analyses["fit-004"].dependencies, ["fit-003"])
        text = " ".join(str(call.args[0]) for call in echo.call_args_list)
        self.assertIn("2 of 4 analyses already existed", text)

    def test_an_analysis_which_is_not_from_a_strategy_is_still_an_error_when_repeated(self):
        plain = "kind: analysis\nname: plain\npipeline: simpletestpipeline\nstatus: ready\n"
        self.apply(plain)
        with patch("asimov.cli.application.click.echo") as echo:
            self.apply(plain)
        text = " ".join(str(call.args[0]) for call in echo.call_args_list)
        self.assertIn("an analysis already exists with this name", text)

    def test_name_and_iterate_do_not_rename_a_strategys_analyses(self):
        self.apply(self.CHAIN.format(length=2))
        self.apply(self.CHAIN.format(length=2), iterate=True)
        self.assertEqual(sorted(self.analyses()), ["fit-001", "fit-002"])

    def test_an_unknown_type_applies_nothing(self):
        with self.assertRaisesRegex(StrategyError, "Unknown strategy type"):
            self.apply(self.CHAIN.format(length=2).replace("chain", "nonesuch"))
        self.assertEqual(self.analyses(), {})

    def test_a_plugin_which_fails_applies_nothing_of_that_blueprint(self):
        def fail(b, c):
            raise RuntimeError("boom")

        Emit.documents = staticmethod(fail)
        with plugins(emit=Emit), self.assertRaises(StrategyError):
            self.apply(self.CHAIN.format(length=2).replace("chain", "emit"))
        self.assertEqual(self.analyses(), {})

    def test_bad_options_apply_nothing(self):
        with self.assertRaises(StrategyError):
            self.apply(self.CHAIN.format(length=0))
        self.assertEqual(self.analyses(), {})

    def test_the_plugin_sees_the_analyses_which_exist(self):
        seen = {}

        def look(blueprint, context):
            seen["event"] = context.event
            seen["analyses"] = context.analyses()
            seen["subjects"] = context.subjects()
            return [PIPELINE("new")]

        Emit.documents = staticmethod(look)
        self.apply("kind: analysis\nname: old\npipeline: simpletestpipeline\nstatus: ready\n")
        with plugins(emit=Emit):
            self.apply(self.CHAIN.format(length=1).replace("chain", "emit"))
        self.assertEqual(seen, {"event": "EvA", "analyses": ["old"], "subjects": ["EvA"]})

    def test_the_matrix_strategy_is_not_stamped(self):
        self.apply(
            "kind: analysis\nname: m-{waveform.approximant}\npipeline: simpletestpipeline\n"
            "status: ready\nstrategy:\n  waveform.approximant: [A, B]\n"
        )
        analyses = self.analyses()
        self.assertEqual(sorted(analyses), ["m-A", "m-B"])
        for analysis in analyses.values():
            self.assertNotIn("strategy", analysis.meta)


if __name__ == "__main__":
    unittest.main()
