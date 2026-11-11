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


class TestEnforcement(AccountingTestCase):
    """Refusing jobs which charge someone else, on a hosted project (#181)."""

    def setUp(self):
        from unittest import mock

        from asimov.registry import FileRegistry

        super().setUp()
        registry_path = os.path.join(self.dir, "registry.yaml")
        FileRegistry(registry_path).add(ProjectEntry(name="p", root=self.root, groups=["cbc-pe"]))
        patcher = mock.patch.dict(os.environ, {"ASIMOV_REGISTRY": registry_path})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.analysis_ = self.apply("a1", accounting="albert.einstein", **{
            "accounting group": "ligo.dev.o4.cbc", "accounting group user": "victim",
        })
        self.rundir = os.path.join(self.dir, "run")
        os.makedirs(self.rundir)
        self.analysis_.rundir = self.rundir

    def write(self, name, text):
        path = os.path.join(self.rundir, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as handle:
            handle.write(text)
        return path

    def good(self, name="job.sub"):
        return self.write(name, "executable = /bin/true\naccounting_group = ligo.dev.o4.cbc\n"
                                "accounting_group_user = albert.einstein\nqueue\n")

    def check(self):
        from asimov.accounting import check

        with self.context.activate():
            return check(self.analysis_)

    def test_prepare_replaces_the_blueprints_values(self):
        from asimov.accounting import prepare

        with self.context.activate():
            prepare(self.analysis_)
        self.assertEqual(self.analysis_.meta["scheduler"]["accounting group user"], "albert.einstein")

    def test_matching_jobs_are_allowed_and_the_charge_recorded(self):
        self.good()
        self.assertEqual(self.check().user, "albert.einstein")
        with self.context.activate():
            record = self.context.ledger.audit_log(action="submit")[-1]
        self.assertEqual(record.accounting["user"], "albert.einstein")
        self.assertEqual(record.accounting["requested by"], "albert")

    def test_a_job_charging_someone_else_is_refused(self):
        self.good()
        self.write("other.sub", "accounting_group = ligo.dev.o4.cbc\naccounting_group_user = victim\nqueue\n")
        with self.assertRaises(AccountingError) as caught:
            self.check()
        self.assertIn("'victim'", str(caught.exception))

    def test_every_way_of_saying_it_is_checked(self):
        for text in (
            '+AcctGroupUser = "victim"\naccounting_group = ligo.dev.o4.cbc\naccounting_group_user = albert.einstein\n',
            "accounting_group = ligo.prod.o4\naccounting_group_user = albert.einstein\n",
            "accounting_group = ligo.dev.o4.cbc\naccounting_group_user = $(who)\n",
            "accounting_group = ligo.dev.o4.cbc\n",
            "include : other.sub\naccounting_group = ligo.dev.o4.cbc\naccounting_group_user = albert.einstein\n",
        ):
            self.write("job.sub", text)
            with self.assertRaises(AccountingError, msg=text):
                self.check()

    def test_dag_nodes_outside_the_run_directory_are_found(self):
        outside = os.path.join(self.dir, "elsewhere")
        os.makedirs(outside)
        with open(os.path.join(outside, "node.sub"), "w") as handle:
            handle.write("accounting_group = ligo.dev.o4.cbc\naccounting_group_user = victim\n")
        self.good()
        self.write("top.dag", f"JOB a job.sub\nJOB b node.sub DIR {outside}\n")
        with self.assertRaises(AccountingError):
            self.check()

    def test_dagmans_own_files_and_dry_runs_are_ignored(self):
        from asimov.accounting import check

        self.good()
        self.write("top.dag.condor.sub", "accounting_group_user = anyone\n")
        self.assertIsNotNone(self.check())
        os.remove(os.path.join(self.rundir, "job.sub"))
        with self.context.activate():
            self.assertIsNone(check(self.analysis_, dryrun=True))

    def test_no_submit_files_is_refused(self):
        with self.assertRaises(AccountingError):
            self.check()

    def test_a_project_not_in_the_registry_is_left_alone(self):
        from unittest import mock

        from asimov.accounting import check

        with mock.patch.dict(os.environ, {"ASIMOV_REGISTRY": os.path.join(self.dir, "none.yaml")}):
            with self.context.activate():
                self.assertIsNone(check(self.analysis_))


class TestBillingOneAnalysis(AccountingTestCase):
    def make_entry(self, **kwargs):
        return ProjectEntry(name="p", root=self.root, **kwargs)

    def test_an_analysis_may_bill_an_allowed_group_its_requester_is_in(self):
        analysis = self.apply("a1", who="dw", **{"accounting group": "ligo.prod.o4", "billing group": "o4-prod"})
        found = self.resolve(analysis, self.make_entry(billable_groups=["o4-prod"]))
        self.assertEqual((found.user, found.billed_group, found.requested_by), ("dw.charged", "o4-prod", "dw"))

    def test_not_a_group_the_project_does_not_allow(self):
        analysis = self.apply("a1", who="dw", **{"accounting group": "ligo.prod.o4", "billing group": "o4-prod"})
        with self.assertRaises(AccountingError):
            self.resolve(analysis, self.make_entry())

    def test_not_a_group_the_requester_is_not_in(self):
        analysis = self.apply("a1", who="albert", **{"accounting group": "ligo.prod.o4", "billing group": "o4-prod"})
        with self.assertRaises(AccountingError) as caught:
            self.resolve(analysis, self.make_entry(billable_groups=["o4-prod"]))
        self.assertIn("aren't in it", str(caught.exception))


class TestCommands(AccountingTestCase):
    def test_show_and_hand_over(self):
        from click.testing import CliRunner

        from asimov.cli.accounting import accounting

        self.apply("a1", accounting="albert.einstein", **{"accounting group": "ligo.dev.x"})
        runner = CliRunner()
        with self.context.activate():
            shown = runner.invoke(accounting, ["show", "S000000", "a1"])
            self.assertEqual(shown.exit_code, 0, shown.output)
            self.assertIn("ligo.dev.x", shown.output)
            handed = runner.invoke(accounting, ["hand-over", "S000000", "a1", "jane", "--reason", "leaving"])
            self.assertEqual(handed.exit_code, 0, handed.output)
            self.assertEqual(requester(self.context.ledger, self.analysis("a1")), ("jane", "jane"))
            missing = runner.invoke(accounting, ["show", "S000000", "nope"])
            self.assertNotEqual(missing.exit_code, 0)
