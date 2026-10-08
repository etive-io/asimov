"""
Tests for serving several projects from the REST API (#184).
"""

import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

os.environ["ASIMOV_TESTING"] = "1"

import asimov.api.auth as auth_module  # noqa: E402
from asimov import access  # noqa: E402
from asimov.api.app import create_app  # noqa: E402
from asimov.api.blueprints import events as events_blueprint  # noqa: E402
from asimov.cli.project import make_project  # noqa: E402
from asimov.context import get_active_context  # noqa: E402
from asimov.principal import current_principal  # noqa: E402
from asimov.registry import FileRegistry, ProjectEntry, SingleProjectRegistry  # noqa: E402

AUTH = {"Authorization": "Bearer tok-alice"}


class ProjectsTestCase(unittest.TestCase):
    engine = "yamlfile"

    def setUp(self):
        self.origin = os.getcwd()
        self.addCleanup(os.chdir, self.origin)
        auth_module._api_keys_cache = {"tok-alice": "alice", "tok-bob": "bob"}
        self.addCleanup(setattr, auth_module, "_api_keys_cache", None)
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.registry = FileRegistry(os.path.join(self.dir, "registry.yaml"))
        for name in ("one", "two"):
            root = os.path.join(self.dir, name)
            make_project(name=name, root=root, engine=self.engine)
            os.chdir(self.origin)
            self.registry.add(ProjectEntry(name=name, root=root, groups=[f"{name}-group"]))
        self.client = self.make_client(self.registry)

    def make_client(self, registry):
        app = create_app(registry=registry)
        app.config["TESTING"] = True
        return app.test_client()

    def set_policy(self, policy):
        previous = access.set_policy(policy)
        self.addCleanup(access.set_policy, previous)

    def post(self, project, name):
        return self.client.post(
            f"/api/v1/projects/{project}/events/",
            data=json.dumps({"name": name}),
            content_type="application/json",
            headers=AUTH,
        )

    def names(self, project, headers=None):
        response = self.client.get(f"/api/v1/projects/{project}/events/", headers=headers)
        self.assertEqual(response.status_code, 200, response.data)
        return sorted(e["name"] for e in json.loads(response.data)["events"])


class TestRouting(ProjectsTestCase):
    def test_projects_have_separate_events(self):
        self.assertEqual(self.post("one", "GW150914").status_code, 201)
        self.assertEqual(self.post("two", "GW170817").status_code, 201)
        self.assertEqual(self.names("one"), ["GW150914"])
        self.assertEqual(self.names("two"), ["GW170817"])
        self.assertEqual(self.client.get("/api/v1/projects/one/events/GW150914").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/projects/one/events/GW170817").status_code, 404)

    def test_requests_interleaved_between_projects(self):
        for i in range(3):
            self.post("one", f"A{i}")
            self.post("two", f"B{i}")
        self.assertEqual(self.names("one"), ["A0", "A1", "A2"])
        self.assertEqual(self.names("two"), ["B0", "B1", "B2"])

    def test_the_route_runs_in_the_projects_context_as_the_caller(self):
        seen = []
        real = events_blueprint.get_ledger

        def spy():
            seen.append((get_active_context().root, current_principal().identifier))
            return real()

        with patch.object(events_blueprint, "get_ledger", spy):
            self.post("two", "GW1")
            self.client.get("/api/v1/projects/one/events/", headers=AUTH)
            self.client.get("/api/v1/projects/one/events/")
        roots = [os.path.basename(root) for root, _ in seen]
        who = [name for _, name in seen]
        self.assertEqual(roots, ["two", "one", "one"])
        self.assertEqual(who, ["alice", "alice", "anonymous"])
        self.assertIsNone(get_active_context())

    def test_analyses_routes_are_per_project_too(self):
        self.post("one", "GW1")
        here = self.client.get("/api/v1/projects/one/analyses/GW1/a")
        there = self.client.get("/api/v1/projects/two/analyses/GW1/a")
        self.assertEqual(json.loads(here.data)["error"], "Analysis not found")
        self.assertEqual(json.loads(there.data)["error"], "Event not found")

    def test_unknown_and_odd_project_names_are_404(self):
        for name in ("nope", "ONE", "..", "one%2f..", "a b", "x" * 200):
            response = self.client.get(f"/api/v1/projects/{name}/events/")
            self.assertEqual(response.status_code, 404, name)
            self.assertNotEqual(response.status_code, 500)

    def test_writes_still_need_authentication(self):
        response = self.client.post(
            "/api/v1/projects/one/events/",
            data=json.dumps({"name": "X"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.names("one"), [])

    def test_health_is_not_project_scoped(self):
        self.assertEqual(self.client.get("/api/v1/health").status_code, 200)


class TestAliases(ProjectsTestCase):
    def test_the_older_routes_are_ambiguous_with_several_projects(self):
        response = self.client.get("/api/v1/events/")
        self.assertEqual(response.status_code, 404)
        body = response.data.decode()
        self.assertNotIn("one", body)
        self.assertNotIn("two", body)

    def test_the_older_routes_serve_the_only_project(self):
        self.registry.remove("two")
        self.assertEqual(self.post("one", "GW1").status_code, 201)
        response = self.client.get("/api/v1/events/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([e["name"] for e in json.loads(response.data)["events"]], ["GW1"])
        created = self.client.post(
            "/api/v1/events/",
            data=json.dumps({"name": "GW2"}),
            content_type="application/json",
            headers=AUTH,
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(self.names("one"), ["GW1", "GW2"])

    def test_a_single_project_registry_works_the_same(self):
        client = self.make_client(SingleProjectRegistry(os.path.join(self.dir, "one"), name="solo"))
        response = client.get("/api/v1/projects/solo/events/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(client.get("/api/v1/events/").status_code, 200)


class TestAccess(ProjectsTestCase):
    def test_the_policy_is_asked_who_wants_what(self):
        seen = []

        class Spy(access.Policy):
            def allows(self, principal, entry, action):
                seen.append((principal.identifier, entry.name, action))
                return True

        self.set_policy(Spy())
        self.client.get("/api/v1/projects/one/events/", headers=AUTH)
        self.client.get("/api/v1/projects/two/events/")
        self.post("one", "X")
        self.assertEqual(
            seen,
            [
                ("alice", "one", "read"),
                ("anonymous", "two", "read"),
                ("alice", "one", "read"),
                ("alice", "one", "write"),
            ],
        )

    def test_a_project_you_may_not_read_looks_like_one_that_doesnt_exist(self):
        class OnlyTwo(access.Policy):
            def allows(self, principal, entry, action):
                return entry.name == "two"

        self.set_policy(OnlyTwo())
        denied = self.client.get("/api/v1/projects/one/events/", headers=AUTH)
        missing = self.client.get("/api/v1/projects/nope/events/", headers=AUTH)
        self.assertEqual(denied.status_code, 404)
        self.assertEqual(denied.data, missing.data)
        self.assertEqual(self.client.get("/api/v1/projects/two/events/").status_code, 200)

    def test_read_without_write_is_forbidden_to_write(self):
        class ReadOnly(access.Policy):
            def allows(self, principal, entry, action):
                return action == access.READ

        self.set_policy(ReadOnly())
        self.assertEqual(self.names("one"), [])
        response = self.post("one", "X")
        self.assertEqual(response.status_code, 403)
        self.assertIn("may not write", json.loads(response.data)["error"])
        self.assertEqual(self.names("one"), [])

    def test_the_project_list_shows_only_what_may_be_read_and_no_paths(self):
        response = self.client.get("/api/v1/projects/")
        listed = json.loads(response.data)["projects"]
        self.assertEqual([p["name"] for p in listed], ["one", "two"])
        self.assertEqual(listed[0], {"name": "one", "groups": ["one-group"]})
        self.assertNotIn(self.dir, response.data.decode())

        class OnlyTwo(access.Policy):
            def allows(self, principal, entry, action):
                return entry.name == "two"

        self.set_policy(OnlyTwo())
        listed = json.loads(self.client.get("/api/v1/projects/").data)["projects"]
        self.assertEqual([p["name"] for p in listed], ["two"])


class TestWithoutARegistry(unittest.TestCase):
    def setUp(self):
        auth_module._api_keys_cache = {"tok-alice": "alice"}
        self.addCleanup(setattr, auth_module, "_api_keys_cache", None)

    def test_project_routes_do_not_exist(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ASIMOV_REGISTRY", None)
            app = create_app()
        client = app.test_client()
        self.assertEqual(client.get("/api/v1/projects/").status_code, 404)
        self.assertEqual(client.get("/api/v1/projects/x/events/").status_code, 404)

    def test_the_environment_can_name_a_registry(self):
        directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, directory, True)
        path = os.path.join(directory, "r.yaml")
        FileRegistry(path).add(ProjectEntry(name="p", root=directory))
        with patch.dict(os.environ, {"ASIMOV_REGISTRY": path}):
            app = create_app()
        listed = json.loads(app.test_client().get("/api/v1/projects/").data)["projects"]
        self.assertEqual([p["name"] for p in listed], ["p"])


class TestSqlite(TestRouting, TestAliases, TestAccess):
    engine = "sqlite"


if __name__ == "__main__":
    unittest.main()
