"""
Tests for the Principal model (#243).
"""

import os
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch

import asimov.principal as principal_module
from asimov.cli.application import apply_page
from asimov.cli.project import make_project
from asimov.context import ProjectContext
from asimov.principal import (
    Principal,
    acting_as,
    current_principal,
    set_principal_provider,
)

DATA = os.path.join(os.path.dirname(__file__), "test_data")
BLUEPRINTS = os.path.join(os.path.dirname(__file__), "test_blueprints")


class TestPrincipal(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(Principal.person("dw").kind, "person")
        self.assertEqual(Principal.agent("sess").kind, "agent")
        self.assertEqual(Principal.monitor().kind, "monitor")

    def test_an_unknown_kind_is_refused(self):
        with self.assertRaises(ValueError):
            Principal("robot", "r2")

    def test_an_identifier_is_required(self):
        for identifier in ("", "   ", None):
            with self.subTest(identifier=identifier):
                with self.assertRaises(ValueError):
                    Principal.person(identifier)

    def test_acting_for_must_be_a_principal(self):
        with self.assertRaises(TypeError):
            Principal.agent("sess", acting_for="dw")

    def test_a_principal_is_immutable_and_hashable(self):
        person = Principal.person("dw")
        with self.assertRaises(Exception):
            person.identifier = "other"
        self.assertEqual({person, Principal.person("dw")}, {person})

    def test_local_user_is_the_operating_system_user(self):
        with patch("asimov.principal.getpass.getuser", return_value="alice"):
            self.assertEqual(Principal.local_user(), Principal.person("alice"))

    def test_local_user_survives_a_missing_password_entry(self):
        with patch("asimov.principal.getpass.getuser", side_effect=KeyError), \
                patch.dict(os.environ, {"USER": "container-user"}):
            self.assertEqual(Principal.local_user().identifier, "container-user")
        with patch("asimov.principal.getpass.getuser", side_effect=KeyError), \
                patch.dict(os.environ, {}, clear=True):
            self.assertEqual(Principal.local_user().identifier, "unknown")

    def test_on_behalf_of_follows_the_chain(self):
        person = Principal.person("dw")
        agent = Principal.agent("sess", acting_for=person)
        subagent = Principal.agent("sub", acting_for=agent)
        self.assertEqual(subagent.on_behalf_of, person)
        self.assertEqual(person.on_behalf_of, person)

    def test_a_lone_person_serialises_compactly(self):
        self.assertEqual(
            Principal.person("dw").to_dict(), {"kind": "person", "identifier": "dw"}
        )

    def test_round_trip(self):
        original = Principal.agent(
            "sess",
            acting_for=Principal.person("dw", group="cbc", role="analyst"),
            group="cbc",
            role="analyst",
        )
        self.assertEqual(Principal.from_dict(original.to_dict()), original)

    def test_from_dict_refuses_what_is_not_a_principal(self):
        for data in (None, "dw", {}, {"kind": "person"}, {"kind": "bot", "identifier": "x"}):
            with self.subTest(data=data):
                with self.assertRaises(ValueError):
                    Principal.from_dict(data)

    def test_prov_for_a_person(self):
        (node,) = Principal.person("dw").to_prov()
        self.assertEqual(node["@type"], "prov:Person")
        self.assertEqual(node["@id"], "urn:asimov:agent:person:dw")
        self.assertEqual(node["asimov:name"], "dw")
        self.assertNotIn("prov:actedOnBehalfOf", node)

    def test_prov_for_an_agent_acting_for_a_person(self):
        agent = Principal.agent("sess 1", acting_for=Principal.person("dw"), group="cbc", role="analyst")
        agent_node, person_node = agent.to_prov()
        self.assertEqual(agent_node["@type"], "prov:SoftwareAgent")
        self.assertEqual(agent_node["@id"], "urn:asimov:agent:agent:sess%201")
        self.assertEqual(agent_node["prov:actedOnBehalfOf"], {"@id": person_node["@id"]})
        self.assertEqual(agent_node["asimov:group"], "cbc")
        self.assertEqual(agent_node["asimov:role"], "analyst")
        self.assertEqual(person_node["@type"], "prov:Person")

    def test_the_monitor_is_a_software_agent(self):
        (node,) = Principal.monitor().to_prov()
        self.assertEqual(node["@type"], "prov:SoftwareAgent")

    def test_str(self):
        self.assertEqual(str(Principal.person("dw")), "dw")
        self.assertEqual(
            str(Principal.agent("sess", acting_for=Principal.person("dw"))), "sess (for dw)"
        )


class TestCurrentPrincipal(unittest.TestCase):
    def setUp(self):
        self.addCleanup(set_principal_provider, set_principal_provider(None))

    def test_defaults_to_the_local_user(self):
        with patch("asimov.principal.getpass.getuser", return_value="alice"):
            self.assertEqual(current_principal(), Principal.person("alice"))

    def test_acting_as_chooses_and_restores(self):
        outer, inner = Principal.person("a"), Principal.agent("b")
        with acting_as(outer):
            self.assertIs(current_principal(), outer)
            with acting_as(inner):
                self.assertIs(current_principal(), inner)
            self.assertIs(current_principal(), outer)
        self.assertNotEqual(current_principal(), outer)

    def test_acting_as_restores_when_the_block_raises(self):
        with self.assertRaises(ValueError):
            with acting_as(Principal.person("a")):
                raise ValueError
        self.assertNotEqual(current_principal(), Principal.person("a"))

    def test_acting_as_needs_a_principal(self):
        with self.assertRaises(TypeError):
            with acting_as("dw"):
                pass

    def test_a_provider_supplies_the_principal(self):
        supplied = Principal.person("from-idp", group="cbc", role="analyst")
        set_principal_provider(lambda: supplied)
        self.assertIs(current_principal(), supplied)

    def test_a_provider_may_decline(self):
        set_principal_provider(lambda: None)
        with patch("asimov.principal.getpass.getuser", return_value="alice"):
            self.assertEqual(current_principal(), Principal.person("alice"))

    def test_setting_a_provider_returns_the_previous_one(self):
        first = lambda: Principal.person("one")  # noqa: E731
        self.assertIsNone(set_principal_provider(first))
        self.assertIs(set_principal_provider(None), first)

    def test_acting_as_beats_the_provider(self):
        set_principal_provider(lambda: Principal.person("from-idp"))
        chosen = Principal.person("chosen")
        with acting_as(chosen):
            self.assertIs(current_principal(), chosen)

    def test_the_provider_is_asked_each_time(self):
        who = [Principal.person("one")]
        set_principal_provider(lambda: who[0])
        self.assertEqual(current_principal().identifier, "one")
        who[0] = Principal.person("two")
        self.assertEqual(current_principal().identifier, "two")

    def test_threads_have_their_own_principal(self):
        seen = {}
        both = threading.Barrier(2)

        def request(name):
            with acting_as(Principal.person(name)):
                both.wait(timeout=10)
                seen[name] = current_principal().identifier

        threads = [threading.Thread(target=request, args=(n,)) for n in ("a", "b")]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(seen, {"a": "a", "b": "b"})


class TestContextPrincipal(unittest.TestCase):
    def setUp(self):
        self.addCleanup(set_principal_provider, set_principal_provider(None))
        self.origin = os.getcwd()
        self.root = tempfile.mkdtemp()
        make_project(name="T", root=self.root, engine="yamlfile")
        os.chdir(self.origin)
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def tearDown(self):
        os.chdir(self.origin)

    def test_a_context_can_have_its_own_principal(self):
        monitor = Principal.monitor()
        ctx = ProjectContext.from_directory(self.root)
        ctx.principal = monitor
        with ctx.activate():
            self.assertIs(current_principal(), monitor)
        self.assertIsNot(current_principal(), monitor)

    def test_the_context_beats_the_provider_and_acting_as_beats_the_context(self):
        set_principal_provider(lambda: Principal.person("from-idp"))
        ctx = ProjectContext.from_directory(self.root)
        ctx.principal = Principal.monitor()
        with ctx.activate():
            self.assertEqual(current_principal().kind, "monitor")
            with acting_as(Principal.person("chosen")):
                self.assertEqual(current_principal().identifier, "chosen")

    def test_a_context_without_a_principal_defers_to_the_provider(self):
        set_principal_provider(lambda: Principal.person("from-idp"))
        ctx = ProjectContext.from_directory(self.root)
        with ctx.activate():
            self.assertEqual(current_principal().identifier, "from-idp")

    def test_the_monitor_command_acts_as_the_monitor(self):
        from asimov.cli import monitor as monitor_module

        seen = []

        def command(*args, **kwargs):
            seen.append(current_principal())

        monitor_module._as_monitor(command)()
        self.assertEqual(seen, [Principal.monitor()])
        self.assertNotEqual(current_principal(), Principal.monitor())


class TestRequestedBy(unittest.TestCase):
    """``requested by`` is recorded when an analysis is applied (#243)."""

    ENGINES = ("yamlfile", "sqlite")

    def setUp(self):
        self.addCleanup(set_principal_provider, set_principal_provider(None))
        self.origin = os.getcwd()
        self.dirs = []
        self.addCleanup(os.chdir, self.origin)

    def tearDown(self):
        os.chdir(self.origin)
        for path in self.dirs:
            shutil.rmtree(path, ignore_errors=True)

    def context(self, engine):
        root = tempfile.mkdtemp()
        self.dirs.append(root)
        make_project(name="T", root=root, engine=engine)
        os.chdir(self.origin)
        ctx = ProjectContext.from_directory(root)
        self.addCleanup(lambda: getattr(ctx.ledger, "close", lambda: None)())
        with ctx.activate():
            apply_page(os.path.join(DATA, "testing_pe.yaml"), ledger=ctx.ledger)
            apply_page(os.path.join(DATA, "test_event.yaml"), ledger=ctx.ledger)
        return ctx

    def analyses(self, ctx):
        with ctx.activate():
            return {p.name: p for p in ctx.ledger.get_event("S000000")[0].productions}

    def apply_analysis(self, ctx, filename="simple_test_pipeline.yaml"):
        with ctx.activate():
            apply_page(os.path.join(BLUEPRINTS, filename), event="S000000", ledger=ctx.ledger)

    def test_an_applied_analysis_records_who_requested_it(self):
        for engine in self.ENGINES:
            with self.subTest(engine=engine):
                ctx = self.context(engine)
                with acting_as(Principal.person("alice")):
                    self.apply_analysis(ctx)
                analysis = self.analyses(ctx)["test-simple-pipeline"]
                self.assertEqual(analysis.requested_by, Principal.person("alice"))

    def test_an_agent_is_recorded_with_who_it_acts_for(self):
        for engine in self.ENGINES:
            with self.subTest(engine=engine):
                ctx = self.context(engine)
                agent = Principal.agent("sess-1", acting_for=Principal.person("dw"))
                with acting_as(agent):
                    self.apply_analysis(ctx)
                analysis = self.analyses(ctx)["test-simple-pipeline"]
                self.assertEqual(analysis.requested_by, agent)
                self.assertEqual(analysis.requested_by.on_behalf_of, Principal.person("dw"))

    def test_the_local_user_is_recorded_when_nobody_says(self):
        ctx = self.context("yamlfile")
        with patch("asimov.principal.getpass.getuser", return_value="alice"):
            self.apply_analysis(ctx)
        analysis = self.analyses(ctx)["test-simple-pipeline"]
        self.assertEqual(analysis.requested_by, Principal.person("alice"))

    def test_a_blueprint_cannot_name_the_requester(self):
        ctx = self.context("yamlfile")
        blueprint = os.path.join(tempfile.mkdtemp(), "forged.yaml")
        self.dirs.append(os.path.dirname(blueprint))
        with open(os.path.join(BLUEPRINTS, "simple_test_pipeline.yaml")) as source:
            text = source.read()
        with open(blueprint, "w") as forged:
            forged.write(text.rstrip("\n") + "\nrequested by:\n  kind: person\n  identifier: somebody-else\n")
        with acting_as(Principal.person("alice")):
            with ctx.activate():
                apply_page(blueprint, event="S000000", ledger=ctx.ledger)
        analysis = self.analyses(ctx)["test-simple-pipeline"]
        self.assertEqual(analysis.requested_by, Principal.person("alice"))

    def _apply_text(self, ctx, text, **kwargs):
        path = os.path.join(tempfile.mkdtemp(), "blueprint.yaml")
        self.dirs.append(os.path.dirname(path))
        with open(path, "w") as f:
            f.write(text)
        with ctx.activate():
            apply_page(path, ledger=ctx.ledger, **kwargs)

    def test_a_project_analysis_records_who_requested_it(self):
        for engine in self.ENGINES:
            with self.subTest(engine=engine):
                ctx = self.context(engine)
                with acting_as(Principal.person("alice")):
                    self._apply_text(
                        ctx,
                        "kind: projectanalysis\nname: pa1\npipeline: simpletestpipeline\n"
                        "subjects: [S000000]\nanalyses:\n- - 'pipeline: simpletestpipeline'\n"
                        "status: ready\n",
                    )
                with ctx.activate():
                    (analysis,) = [a for a in ctx.ledger.project_analyses if a.name == "pa1"]
                self.assertEqual(analysis.requested_by, Principal.person("alice"))

    def test_analyses_in_a_bundle_record_who_requested_them(self):
        for engine in self.ENGINES:
            with self.subTest(engine=engine):
                ctx = self.context(engine)
                with acting_as(Principal.person("alice")):
                    self._apply_text(
                        ctx,
                        "kind: analysisbundle\nname: b\nanalyses:\n"
                        "- name: in-bundle\n  pipeline: simpletestpipeline\n  status: ready\n",
                        event="S000000",
                    )
                analysis = self.analyses(ctx)["in-bundle"]
                self.assertEqual(analysis.requested_by, Principal.person("alice"))

    def test_an_analysis_with_no_record_has_no_requester(self):
        from asimov.analysis import SimpleAnalysis

        analysis = SimpleAnalysis.__new__(SimpleAnalysis)
        analysis.meta = {}
        self.assertIsNone(analysis.requested_by)


if __name__ == "__main__":
    unittest.main()
