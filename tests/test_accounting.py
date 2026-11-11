"""
Tests for working out who an analysis's jobs are charged to (#181).
"""

import os
import shutil
import tempfile
import unittest

import yaml

from asimov.accounting import AccountingError, hand_over, requester, resolve
from asimov.cli.application import apply_page
from asimov.cli.project import make_project
from asimov.context import ProjectContext
from asimov.identity import Identity, using_identity
from asimov.membership import FileGroupDirectory
from asimov.principal import Principal, acting_as
from asimov.registry import ProjectEntry

DATA = os.path.join(os.path.dirname(__file__), "test_data")


def analysis_page(name, **scheduler):
    page = {"kind": "analysis", "name": name, "pipeline": "simpletestpipeline", "event": "S000000"}
    if scheduler:
        page["scheduler"] = scheduler
    return yaml.safe_dump(page)


class AccountingTestCase(unittest.TestCase):
    def setUp(self):
        self.origin = os.getcwd()
        self.addCleanup(os.chdir, self.origin)
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.root = os.path.join(self.dir, "p")
        make_project(name="p", root=self.root, engine="yamlfile")
        os.chdir(self.origin)
        self.context = ProjectContext.from_directory(self.root)
        with self.context.activate():
            apply_page(os.path.join(DATA, "testing_pe.yaml"), ledger=self.context.ledger)
            apply_page(os.path.join(DATA, "test_event.yaml"), ledger=self.context.ledger)
        self.groups_path = os.path.join(self.dir, "groups.yaml")
        with open(self.groups_path, "w") as handle:
            yaml.safe_dump({"groups": {
                "cbc-pe": {"members": ["albert"], "accounting tags": ["ligo.dev.*"]},
                "o4-prod": {"members": ["dw"], "accounting contact": "dw.charged",
                            "accounting tags": ["ligo.prod.*"]},
            }}, handle)
        self.directory = FileGroupDirectory(self.groups_path)
        self.entry = ProjectEntry(name="p", root=self.root)

    def apply(self, name, who="albert", accounting=None, **scheduler):
        path = os.path.join(self.dir, f"{name}.yaml")
        with open(path, "w") as handle:
            handle.write(analysis_page(name, **scheduler))
        identity = None
        if accounting:
            identity = Identity(Principal.person(who), None, accounting, frozenset(), "https://idp")
        with self.context.activate(), acting_as(Principal.person(who)), using_identity(identity):
            apply_page(path, ledger=self.context.ledger)
        return self.analysis(name)

    def analysis(self, name):
        self.context.reload_ledger()
        with self.context.activate():
            event = self.context.ledger.get_event("S000000")[0]
            return next(a for a in event.productions if a.name == name)

    def resolve(self, analysis, entry=None, directory="default"):
        directory = self.directory if directory == "default" else directory
        with self.context.activate():
            return resolve(self.context.ledger, analysis, entry or self.entry, directory)


class TestRequester(AccountingTestCase):
    def test_whoever_applied_it_is_charged_under_their_token_name(self):
        analysis = self.apply("a1", accounting="albert.einstein", **{"accounting group": "ligo.dev.o4.cbc"})
        found = self.resolve(analysis)
        self.assertEqual((found.user, found.tag, found.requested_by), ("albert.einstein", "ligo.dev.o4.cbc", "albert"))

    def test_without_a_token_name_their_identifier_is_used(self):
        analysis = self.apply("a1", **{"accounting group": "ligo.dev.x"})
        self.assertEqual(self.resolve(analysis).user, "albert")

    def test_a_blueprint_cannot_choose_who_is_charged(self):
        analysis = self.apply("a1", **{"accounting group": "ligo.dev.x", "accounting group user": "victim"})
        self.assertEqual(self.resolve(analysis).user, "albert")

    def test_a_handover_moves_the_charge(self):
        analysis = self.apply("a1", **{"accounting group": "ligo.dev.x"})
        with self.context.activate(), acting_as(Principal.person("dw")):
            hand_over(self.context.ledger, analysis, "jane", accounting="jane.doe", reason="leaving")
        with self.context.activate():
            self.assertEqual(requester(self.context.ledger, analysis), ("jane", "jane.doe"))

    def test_an_analysis_nobody_requested_cannot_be_charged(self):
        from unittest import mock

        analysis = self.apply("a1", **{"accounting group": "ligo.dev.x"})
        with mock.patch.object(type(self.context.ledger), "audit_log", return_value=[]):
            with self.assertRaises(AccountingError) as caught:
                self.resolve(analysis)
        self.assertIn("hand it over", str(caught.exception))


class TestGroupsAndTags(AccountingTestCase):
    def test_a_tag_must_be_granted_to_one_of_the_requesters_groups(self):
        analysis = self.apply("a1", **{"accounting group": "ligo.prod.o4.cbc"})
        with self.assertRaises(AccountingError) as caught:
            self.resolve(analysis)
        self.assertIn("may not use the accounting tag", str(caught.exception))

    def test_a_billed_group_charges_its_contact_and_uses_its_tags(self):
        analysis = self.apply("a1", **{"accounting group": "ligo.prod.o4.cbc"})
        entry = ProjectEntry(name="p", root=self.root, billing_group="o4-prod")
        found = self.resolve(analysis, entry)
        self.assertEqual(found.user, "dw.charged")
        self.assertEqual((found.requested_by, found.billed_group), ("albert", "o4-prod"))
        self.assertEqual(found.to_dict()["billed group"], "o4-prod")

    def test_a_billed_group_needs_a_contact(self):
        analysis = self.apply("a1", **{"accounting group": "ligo.dev.x"})
        entry = ProjectEntry(name="p", root=self.root, billing_group="cbc-pe")
        with self.assertRaises(AccountingError):
            self.resolve(analysis, entry)

    def test_tags_are_unrestricted_until_a_group_lists_some(self):
        with open(self.groups_path, "w") as handle:
            yaml.safe_dump({"groups": {"cbc-pe": {"members": ["albert"]}}}, handle)
        analysis = self.apply("a1", **{"accounting group": "anything.goes"})
        self.assertEqual(self.resolve(analysis).tag, "anything.goes")


class TestSingleUser(AccountingTestCase):
    def test_without_groups_the_analysis_and_config_decide_as_before(self):
        analysis = self.apply("a1", **{"accounting group": "ligo.dev.x", "accounting group user": "me"})
        found = self.resolve(analysis, directory=None)
        self.assertEqual((found.user, found.tag, found.requested_by), ("me", "ligo.dev.x", None))


class TestGroupsFile(unittest.TestCase):
    def test_bad_accounting_settings_are_errors(self):
        from asimov.membership import MembershipError

        directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, directory, True)
        path = os.path.join(directory, "groups.yaml")
        for bad in ({"accounting contact": ""}, {"accounting tags": "ligo.*"}, {"billing": "x"}):
            with open(path, "w") as handle:
                yaml.safe_dump({"groups": {"g": {"members": [], **bad}}}, handle)
            with self.assertRaises(MembershipError, msg=bad):
                FileGroupDirectory(path).load()


if __name__ == "__main__":
    unittest.main()
