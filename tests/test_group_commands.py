"""
Group-aware commands (#234): list, set, delete a group; rerun with what is
downstream. Each is exercised on both ledger engines.
"""
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from click.testing import CliRunner

from asimov import groups
from asimov.cli import analysis as analysis_cli
from asimov.cli.application import apply_page
from asimov.cli.project import make_project
from asimov.groups import GroupError
from asimov.ledger import DatabaseLedger, YAMLLedger
from asimov.pipelines.testing import SimpleTestPipeline

OTHER = (
    "kind: event\nname: Elsewhere\ninterferometers: [H1]\n---\n"
    "kind: analysis\nname: other\npipeline: simpletestpipeline\nstatus: ready\n"
    "strategy:\n  type: chain\n  length: 2\n"
)
TOY = "kind: analysis\nname: {name}\nstrategy:\n  type: toy-rounds\n  components: {components}\n  rounds: 2\n"
MANUAL = (
    "kind: analysis\nname: manual\npipeline: simpletestpipeline\nstatus: ready\n"
    "needs:\n  - component-A/step-r1\n"
)


def keys(members):
    return [m.label for m in members]


class GroupCase(unittest.TestCase):
    engine = "yamlfile"

    def setUp(self):
        os.environ["ASIMOV_TOY_STRATEGY"] = "1"
        self.cwd = os.getcwd()
        self.root = tempfile.mkdtemp()
        os.chdir(self.root)
        self.ledger = self.make_ledger()
        self.apply(TOY.format(name="toy", components="[A, B]"))
        self.apply(OTHER, subject="Elsewhere")
        self.apply(MANUAL, subject="component-A")

    def tearDown(self):
        os.environ.pop("ASIMOV_TOY_STRATEGY", None)
        os.chdir(self.cwd)
        shutil.rmtree(self.root, ignore_errors=True)

    def make_ledger(self):
        make_project(name="Test project", root=self.root, engine="yamlfile")
        return YAMLLedger(".asimov/ledger.yml")

    def reopen(self):
        return YAMLLedger(".asimov/ledger.yml")

    def apply(self, text, subject=None):
        with open("blueprint.yaml", "w") as handle:
            handle.write(text)
        return apply_page("blueprint.yaml", event=subject, ledger=self.ledger)

    def members(self, ledger=None):
        return groups.everything(ledger or self.ledger)

    def status_of(self, label, ledger=None):
        return {m.label: m.status for m in self.members(ledger or self.reopen())}[label]

    def put(self, label, status):
        member = {m.label: m for m in self.members()}[label]
        member.analysis.status = status
        groups._save(self.ledger, member)


class DatabaseCase(GroupCase):
    engine = "sqlalchemy"

    def make_ledger(self):
        self.location = f"sqlite:///{os.path.join(self.root, 'ledger.db')}"
        ledger = DatabaseLedger(engine="sqlalchemy", location=self.location)
        ledger.db.create_tables()
        return ledger

    def reopen(self):
        return DatabaseLedger(engine="sqlalchemy", location=self.location)


class Tests:
    """The tests, for both engines."""

    def test_a_group_is_exactly_the_analyses_stamped_with_it(self):
        found = groups.group_members(self.ledger, "toy")
        self.assertEqual(
            sorted(keys(found)),
            sorted(
                [f"component-{c}/step-r{r}" for c in "AB" for r in (1, 2)]
                + [f"shared/combine-r{r}" for r in (1, 2)]
            ),
        )

    def test_a_group_which_does_not_exist_is_an_error(self):
        with self.assertRaisesRegex(GroupError, "no group called 'nope'"):
            groups.group_members(self.ledger, "nope")

    def test_the_summary_counts_the_statuses(self):
        self.put("component-A/step-r1", "finished")
        self.assertEqual(
            groups.summary(groups.group_members(self.ledger, "toy")), "6 analyses: 5 ready, 1 finished"
        )

    def test_downstream_is_the_analysis_and_everything_which_depends_on_it(self):
        start = groups.find(self.ledger, "component-A", "step-r1")
        found = groups.downstream(self.ledger, start)
        self.assertEqual(
            sorted(keys(found)),
            sorted(
                [
                    "component-A/step-r1",
                    "shared/combine-r1",
                    "component-A/step-r2",
                    "component-B/step-r2",
                    "shared/combine-r2",
                    "component-A/manual",
                ]
            ),
        )

    def test_downstream_is_in_an_order_which_can_be_run(self):
        order = keys(groups.downstream(self.ledger, groups.find(self.ledger, "component-A", "step-r1")))
        self.assertEqual(order[0], "component-A/step-r1")
        self.assertLess(order.index("shared/combine-r1"), order.index("component-B/step-r2"))
        self.assertLess(order.index("component-B/step-r2"), order.index("shared/combine-r2"))

    def test_the_last_analysis_has_nothing_downstream(self):
        found = groups.downstream(self.ledger, groups.find(self.ledger, "shared", "combine-r2"))
        self.assertEqual(keys(found), ["shared/combine-r2"])

    def test_an_analysis_which_is_not_there_is_an_error(self):
        with self.assertRaises(GroupError):
            groups.find(self.ledger, "shared", "combine-r9")

    def test_set_changes_the_group_and_nothing_else(self):
        members = groups.group_members(self.ledger, "toy")
        changed = groups.set_status(self.ledger, members, "stop")
        self.assertEqual(len(changed), 6)
        reopened = self.reopen()
        self.assertEqual(self.status_of("shared/combine-r1", reopened), "stop")
        self.assertEqual(self.status_of("component-A/manual", reopened), "ready")
        self.assertEqual(self.status_of("Elsewhere/other-001", reopened), "ready")

    def test_set_refuses_a_status_which_cannot_be_set(self):
        with self.assertRaises(GroupError):
            groups.set_status(self.ledger, groups.group_members(self.ledger, "toy"), "finished")

    def test_set_leaves_alone_what_has_the_status_already(self):
        self.put("shared/combine-r1", "stop")
        changed = groups.set_status(self.ledger, groups.group_members(self.ledger, "toy"), "stop")
        self.assertEqual(len(changed), 5)

    def test_set_is_audited(self):
        groups.set_status(self.ledger, groups.group_members(self.ledger, "toy"), "stop")
        records = [r for r in self.reopen().audit_log() if r.action == "set-status"]
        self.assertEqual(len(records), 6)

    def test_rerun_resets_status_and_job_id(self):
        start = groups.find(self.ledger, "component-A", "step-r1")
        chosen = groups.downstream(self.ledger, start)
        for member in chosen:
            member.analysis.status = "finished"
            member.analysis.meta.setdefault("scheduler", {})["job id"] = 7
            groups._save(self.ledger, member)
        other = groups.find(self.ledger, "component-B", "step-r1")
        other.analysis.status = "finished"
        groups._save(self.ledger, other)

        chosen = groups.downstream(self.ledger, groups.find(self.ledger, "component-A", "step-r1"))
        groups.reset(self.ledger, chosen)

        reopened = self.reopen()
        for label in keys(chosen):
            self.assertEqual(self.status_of(label, reopened), "ready", label)
        self.assertEqual(self.status_of("component-B/step-r1", reopened), "finished")
        member = groups.find(reopened, "shared", "combine-r1")
        self.assertIsNone(member.analysis.meta.get("scheduler", {}).get("job id"))

    def test_clean_calls_the_pipelines_clean_only_when_asked(self):
        chosen = [groups.find(self.ledger, "component-A", "step-r1")]
        with patch.object(SimpleTestPipeline, "clean") as clean:
            groups.reset(self.ledger, chosen)
            clean.assert_not_called()
            groups.reset(self.ledger, chosen, clean=True)
            clean.assert_called_once()

    def test_delete_removes_the_group_only(self):
        removed = groups.delete(self.ledger, groups.group_members(self.ledger, "toy"))
        self.assertEqual(len(removed), 6)
        left = keys(self.members(self.reopen()))
        self.assertIn("component-A/manual", left)
        self.assertIn("Elsewhere/other-001", left)
        self.assertNotIn("component-A/step-r1", left)
        self.assertNotIn("shared/combine-r1", left)

    def test_delete_refuses_a_running_analysis_and_removes_nothing(self):
        self.put("component-B/step-r1", "running")
        members = groups.group_members(self.ledger, "toy")
        with self.assertRaisesRegex(GroupError, "running"):
            groups.delete(self.ledger, members)
        self.assertEqual(len(groups.group_members(self.reopen(), "toy")), 6)

    def test_delete_with_force_removes_a_running_one_too(self):
        self.put("component-B/step-r1", "running")
        groups.delete(self.ledger, groups.group_members(self.ledger, "toy"), force=True)
        self.assertEqual(groups.group_members(self.reopen(), "toy"), [])

    def test_a_deleted_group_can_be_applied_again(self):
        groups.delete(self.ledger, groups.group_members(self.ledger, "toy"))
        self.ledger = self.reopen()
        self.apply(TOY.format(name="toy", components="[A, B]"))
        self.assertEqual(len(groups.group_members(self.reopen(), "toy")), 6)


class CommandTests:
    """The commands, which ask first."""

    def run_command(self, *arguments, **kwargs):
        with patch("asimov.cli.analysis.ledger", self.ledger):
            return CliRunner().invoke(analysis_cli.analysis, list(arguments), **kwargs)

    def test_list_ends_with_the_counts(self):
        result = self.run_command("list", "--group", "toy")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("component-A/step-r1  ready", result.output)
        self.assertNotIn("Elsewhere", result.output)
        self.assertTrue(result.output.strip().endswith("6 analyses: 6 ready"))

    def test_list_of_an_unknown_group_fails(self):
        result = self.run_command("list", "--group", "nope")
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("no group", result.output)

    def test_set_dry_run_changes_nothing(self):
        result = self.run_command("set", "-g", "toy", "-s", "stop", "--dry-run")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Dry run", result.output)
        self.assertEqual(self.status_of("shared/combine-r1"), "ready")

    def test_set_asks_and_a_no_changes_nothing(self):
        result = self.run_command("set", "-g", "toy", "-s", "stop", input="n\n")
        self.assertIn("Go ahead?", result.output)
        self.assertEqual(self.status_of("shared/combine-r1"), "ready")

    def test_set_with_yes_goes_ahead(self):
        result = self.run_command("set", "-g", "toy", "-s", "stop", "--yes")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(self.status_of("shared/combine-r1"), "stop")

    def test_set_rejects_a_status_it_cannot_set(self):
        result = self.run_command("set", "-g", "toy", "-s", "finished", "--yes")
        self.assertNotEqual(result.exit_code, 0)

    def test_delete_dry_run_removes_nothing(self):
        result = self.run_command("delete", "-g", "toy", "--dry-run")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(len(groups.group_members(self.reopen(), "toy")), 6)

    def test_delete_refuses_running_without_force(self):
        self.put("shared/combine-r1", "running")
        result = self.run_command("delete", "-g", "toy", "--yes")
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("running", result.output)
        self.assertEqual(len(groups.group_members(self.reopen(), "toy")), 6)

    def test_delete_with_yes_removes_the_group(self):
        result = self.run_command("delete", "-g", "toy", "--yes")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(groups.group_members(self.reopen(), "toy"), [])

    def test_rerun_downstream_dry_run_lists_what_it_would_reset(self):
        self.put("shared/combine-r1", "finished")
        result = self.run_command("rerun", "component-A", "step-r1", "--downstream", "--dry-run")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Reset to 'ready' 6 analyses", result.output)
        self.assertIn("shared/combine-r2", result.output)
        self.assertNotIn("component-B/step-r1", result.output)
        self.assertEqual(self.status_of("shared/combine-r1"), "finished")

    def test_rerun_without_downstream_is_just_the_one(self):
        self.put("component-A/step-r1", "finished")
        self.put("shared/combine-r1", "finished")
        result = self.run_command("rerun", "component-A", "step-r1", "--yes")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(self.status_of("component-A/step-r1"), "ready")
        self.assertEqual(self.status_of("shared/combine-r1"), "finished")

    def test_rerun_refuses_when_something_downstream_is_running(self):
        self.put("shared/combine-r1", "running")
        result = self.run_command("rerun", "component-A", "step-r1", "--downstream", "--yes")
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("running", result.output)

    def test_rerun_of_an_analysis_which_is_not_there_fails(self):
        result = self.run_command("rerun", "shared", "combine-r9", "--yes")
        self.assertNotEqual(result.exit_code, 0)


class YAMLTests(Tests, CommandTests, GroupCase):
    pass


class DatabaseTests(Tests, CommandTests, DatabaseCase):
    pass


if __name__ == "__main__":
    unittest.main()
