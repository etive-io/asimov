"""
Tests for groups, roles and project grants (#183).
"""

import os
import shutil
import tempfile
import unittest
from unittest import mock

import yaml

from asimov import access
from asimov.membership import FileGroupDirectory, MembershipError, groups_path_for
from asimov.principal import Principal
from asimov.registry import FileRegistry, ProjectEntry, RegistryError, SingleProjectRegistry

GROUPS = {
    "admins": ["root"],
    "groups": {
        "cbc-pe": {"members": ["dw", "jane"]},
        "cbc-review": {"members": ["sam", "dw"]},
        "everyone": {"members": ["dw", "jane", "sam", "eve"]},
    },
}


class GrantsTestCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.groups_path = os.path.join(self.dir, "groups.yaml")
        self.write_groups(GROUPS)
        self.policy = access.GrantPolicy(FileGroupDirectory(self.groups_path))
        self.entry = ProjectEntry(
            name="gw-o4",
            root=self.dir,
            groups=["cbc-pe"],
            grants={"cbc-review": ["reviewer"], "everyone": "viewer"},
        )

    def write_groups(self, data):
        with open(self.groups_path, "w") as handle:
            yaml.safe_dump(data, handle)

    def authority(self, who, action, entry=None):
        principal = who if isinstance(who, Principal) else Principal.person(who)
        return self.policy.authority(principal, entry or self.entry, action)


class TestRoles(GrantsTestCase):
    def test_owning_groups_are_maintainers(self):
        self.assertEqual(self.authority("jane", access.ADMIN), access.Authority("cbc-pe", "maintainer"))
        self.assertEqual(self.authority("jane", access.EXECUTE), access.Authority("cbc-pe", "maintainer"))

    def test_the_least_role_which_allows_is_recorded(self):
        self.assertEqual(self.authority("jane", access.READ), access.Authority("everyone", "viewer"))
        self.assertEqual(self.authority("dw", access.REVIEW), access.Authority("cbc-review", "reviewer"))

    def test_viewers_only_read(self):
        self.assertIsNotNone(self.authority("eve", access.READ))
        for action in (access.WRITE, access.EXECUTE, access.REVIEW, access.ADMIN):
            self.assertIsNone(self.authority("eve", action), action)

    def test_reviewers_review_but_do_not_change_or_run(self):
        self.assertIsNotNone(self.authority("sam", access.REVIEW))
        for action in (access.WRITE, access.EXECUTE, access.ADMIN):
            self.assertIsNone(self.authority("sam", action), action)

    def test_analysts_change_and_run_but_do_not_review(self):
        entry = ProjectEntry(name="p", root=self.dir, grants={"everyone": ["analyst"]})
        for action in (access.READ, access.WRITE, access.EXECUTE):
            self.assertEqual(self.authority("eve", action, entry), access.Authority("everyone", "analyst"))
        self.assertIsNone(self.authority("eve", access.REVIEW, entry))
        self.assertIsNone(self.authority("eve", access.ADMIN, entry))

    def test_strangers_get_nothing(self):
        for action in access.ACTIONS:
            self.assertIsNone(self.authority("mallory", action))

    def test_admins_may_do_anything(self):
        for action in access.ACTIONS:
            self.assertEqual(self.authority("root", action), access.Authority(role="admin"))

    def test_an_agent_has_the_authority_of_whom_it_acts_for(self):
        agent = Principal.agent("mcp:claude", acting_for=Principal.person("sam"))
        self.assertIsNotNone(self.authority(agent, access.REVIEW))
        self.assertIsNone(self.authority(agent, access.WRITE))
        self.assertIsNone(self.authority(Principal.agent("mcp:claude"), access.READ))

    def test_the_monitor_runs_but_does_not_review_or_administer(self):
        monitor = Principal.monitor()
        for action in (access.READ, access.WRITE, access.EXECUTE):
            self.assertEqual(self.authority(monitor, action), access.Authority(role="monitor"))
        self.assertIsNone(self.authority(monitor, access.REVIEW))
        self.assertIsNone(self.authority(monitor, access.ADMIN))

    def test_membership_changes_apply_at_once(self):
        self.assertIsNone(self.authority("mallory", access.READ))
        self.write_groups({"groups": {"everyone": {"members": ["mallory"]}}})
        self.assertIsNotNone(self.authority("mallory", access.READ))

    def test_a_broken_groups_file_denies(self):
        with open(self.groups_path, "w") as handle:
            handle.write("groups: [not, a, mapping]\n")
        with self.assertLogs("asimov.access", "ERROR"):
            self.assertIsNone(self.authority("jane", access.READ))
        os.remove(self.groups_path)
        with self.assertLogs("asimov.access", "ERROR"):
            self.assertIsNone(self.authority("root", access.READ))


class TestAuthorize(GrantsTestCase):
    def test_it_returns_the_authority(self):
        found = access.authorize(Principal.person("sam"), self.entry, access.REVIEW, self.policy)
        self.assertEqual(found, access.Authority("cbc-review", "reviewer"))

    def test_any_of_several_actions_is_enough(self):
        found = access.authorize(
            Principal.person("sam"), self.entry, (access.WRITE, access.REVIEW), self.policy
        )
        self.assertEqual(found.role, "reviewer")
        with self.assertRaises(access.AccessDenied) as caught:
            access.authorize(Principal.person("eve"), self.entry, (access.WRITE, access.REVIEW), self.policy)
        self.assertIn("may not write or review", str(caught.exception))

    def test_the_policy_in_force_is_used_without_one(self):
        self.assertEqual(access.authorize(Principal.person("anyone"), self.entry, access.ADMIN), access.Authority())

    def test_unknown_actions_are_refused(self):
        with self.assertRaises(ValueError):
            access.authorize(Principal.person("dw"), self.entry, "delete")

    def test_with_authority_records_group_and_role(self):
        agent = Principal.agent("mcp:x", acting_for=Principal.person("sam"))
        recorded = access.with_authority(agent, access.Authority("cbc-review", "reviewer"))
        self.assertEqual(recorded.to_dict()["group"], "cbc-review")
        self.assertEqual(recorded.to_dict()["role"], "reviewer")
        self.assertIs(access.with_authority(agent, access.Authority()), agent)


class TestGrantsInTheRegistry(GrantsTestCase):
    def test_grants_round_trip_through_the_file(self):
        registry = FileRegistry(os.path.join(self.dir, "registry.yaml"))
        registry.add(self.entry)
        stored = registry.get("gw-o4")
        self.assertEqual(stored.grants, {"cbc-review": ["reviewer"], "everyone": ["viewer"]})

    def test_unknown_roles_are_refused(self):
        with self.assertRaises(RegistryError) as caught:
            ProjectEntry(name="p", root=self.dir, grants={"g": ["owner"]})
        self.assertIn("is not a role", str(caught.exception))
        with self.assertRaises(RegistryError):
            ProjectEntry(name="p", root=self.dir, grants=["g"])

    def test_entries_without_grants_are_unchanged(self):
        self.assertNotIn("grants", ProjectEntry(name="p", root=self.dir).to_dict())


class TestFindingTheGroupsFile(GrantsTestCase):
    def test_beside_the_registry(self):
        registry = FileRegistry(os.path.join(self.dir, "registry.yaml"))
        self.assertEqual(groups_path_for(registry), self.groups_path)
        self.assertIsInstance(access.instance_policy(registry), access.GrantPolicy)

    def test_none_without_one(self):
        os.remove(self.groups_path)
        registry = FileRegistry(os.path.join(self.dir, "registry.yaml"))
        self.assertIsNone(groups_path_for(registry))
        self.assertIsNone(access.instance_policy(registry))

    def test_the_environment_names_one(self):
        registry = FileRegistry(os.path.join(self.dir, "elsewhere", "registry.yaml"))
        with mock.patch.dict(os.environ, {"ASIMOV_GROUPS": "/nowhere/groups.yaml"}):
            self.assertEqual(groups_path_for(registry), "/nowhere/groups.yaml")

    def test_a_single_project_directory_has_none(self):
        with mock.patch.dict(os.environ, {"ASIMOV_GROUPS": self.groups_path}):
            self.assertIsNone(groups_path_for(SingleProjectRegistry(self.dir)))

    def test_bad_files_are_errors(self):
        directory = FileGroupDirectory(self.groups_path)
        for bad in (
            {"members": {}},
            {"groups": {"Bad Name": {"members": []}}},
            {"groups": {"g": {"members": "dw"}}},
            {"groups": {"g": {"owners": ["dw"]}}},
            {"admins": "root"},
        ):
            self.write_groups(bad)
            with self.assertRaises(MembershipError, msg=bad):
                directory.load()


if __name__ == "__main__":
    unittest.main()
