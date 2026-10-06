"""
Unit tests for asimov.api.auth.

test_api.py already exercises `require_auth` indirectly through real
endpoints (missing header, invalid scheme, invalid token), but nothing
covers `load_api_keys()`'s source-priority order, the single-key
`ASIMOV_API_KEY` parsing, or the "fail securely" RuntimeError when no
keys are configured outside of testing mode - the exact path that would
turn a misconfigured deployment into an open API instead of a refusal
to start.
"""

import os
import unittest

import asimov.api.auth as auth_module
from asimov import config


class ApiAuthTestCase(unittest.TestCase):
    """Base class that isolates each test from the module's global state."""

    ENV_VARS = ("ASIMOV_API_KEYS_FILE", "ASIMOV_API_KEY", "ASIMOV_TESTING")

    def setUp(self):
        self._saved_cache = auth_module._api_keys_cache
        self._saved_env = {name: os.environ.get(name) for name in self.ENV_VARS}
        for name in self.ENV_VARS:
            os.environ.pop(name, None)
        auth_module._api_keys_cache = None

    def tearDown(self):
        auth_module._api_keys_cache = self._saved_cache
        for name, value in self._saved_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        if config.has_section("api"):
            config.remove_section("api")


class LoadApiKeysPriorityTests(ApiAuthTestCase):
    """`load_api_keys()` must honour its documented source-priority order."""

    def test_cache_takes_priority_over_everything_else(self):
        auth_module._api_keys_cache = {"cached-token": "cached-user"}
        os.environ["ASIMOV_API_KEY"] = "env-token:env-user"
        self.assertEqual(auth_module.load_api_keys(), {"cached-token": "cached-user"})

    def test_keys_file_env_var_is_read(self):
        keys_file = self._write_keys_file({"file-token": "file-user"})
        os.environ["ASIMOV_API_KEYS_FILE"] = keys_file
        self.assertEqual(auth_module.load_api_keys(), {"file-token": "file-user"})

    def test_keys_file_env_var_takes_priority_over_config_file(self):
        keys_file = self._write_keys_file({"file-token": "file-user"})
        os.environ["ASIMOV_API_KEYS_FILE"] = keys_file

        other_keys_file = self._write_keys_file(
            {"config-token": "config-user"}, name="other-keys.yaml"
        )
        config.add_section("api")
        config.set("api", "api_keys_file", other_keys_file)

        self.assertEqual(auth_module.load_api_keys(), {"file-token": "file-user"})

    def test_config_file_is_read_when_no_env_var_is_set(self):
        keys_file = self._write_keys_file({"config-token": "config-user"})
        config.add_section("api")
        config.set("api", "api_keys_file", keys_file)

        self.assertEqual(auth_module.load_api_keys(), {"config-token": "config-user"})

    def test_single_api_key_env_var_with_username(self):
        os.environ["ASIMOV_API_KEY"] = "solo-token:solo-user"
        self.assertEqual(auth_module.load_api_keys(), {"solo-token": "solo-user"})

    def test_single_api_key_env_var_without_username_defaults_to_api_user(self):
        os.environ["ASIMOV_API_KEY"] = "solo-token-no-colon"
        self.assertEqual(
            auth_module.load_api_keys(), {"solo-token-no-colon": "api-user"}
        )

    def test_missing_keys_file_falls_through_to_next_source(self):
        os.environ["ASIMOV_API_KEYS_FILE"] = "/no/such/file/keys.yaml"
        os.environ["ASIMOV_API_KEY"] = "fallback-token:fallback-user"
        self.assertEqual(
            auth_module.load_api_keys(), {"fallback-token": "fallback-user"}
        )

    def test_unreadable_yaml_falls_through_to_next_source(self):
        keys_file = os.path.join(self._tmp_dir(), "broken.yaml")
        with open(keys_file, "w") as handle:
            handle.write("not: valid: yaml: [")
        os.environ["ASIMOV_API_KEYS_FILE"] = keys_file
        os.environ["ASIMOV_API_KEY"] = "fallback-token:fallback-user"
        self.assertEqual(
            auth_module.load_api_keys(), {"fallback-token": "fallback-user"}
        )

    def test_no_keys_configured_outside_testing_mode_fails_securely(self):
        # This is the "misconfigured deployment" path: with nothing
        # configured and ASIMOV_TESTING unset, the API must refuse to
        # start rather than silently accept every request.
        with self.assertRaises(RuntimeError):
            auth_module.load_api_keys()

    def test_no_keys_configured_in_testing_mode_returns_empty_dict(self):
        os.environ["ASIMOV_TESTING"] = "1"
        self.assertEqual(auth_module.load_api_keys(), {})

    # -- helpers -----------------------------------------------------

    def _tmp_dir(self):
        import tempfile

        tmp_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp_dir, ignore_errors=True))
        return tmp_dir

    def _write_keys_file(self, keys, name="keys.yaml"):
        import yaml

        path = os.path.join(self._tmp_dir(), name)
        with open(path, "w") as handle:
            yaml.safe_dump({"api_keys": keys}, handle)
        return path


class VerifyTokenTests(ApiAuthTestCase):
    def setUp(self):
        super().setUp()
        auth_module._api_keys_cache = {"valid-token": "alice"}

    def test_valid_token_returns_username(self):
        self.assertEqual(auth_module.verify_token("valid-token"), "alice")

    def test_invalid_token_returns_none(self):
        self.assertIsNone(auth_module.verify_token("wrong-token"))

    def test_empty_token_returns_none(self):
        self.assertIsNone(auth_module.verify_token(""))

    def test_no_keys_configured_returns_none_rather_than_raising(self):
        auth_module._api_keys_cache = {}
        self.assertIsNone(auth_module.verify_token("valid-token"))


class RequireAuthMalformedHeaderTests(ApiAuthTestCase):
    """
    `require_auth` needs a real Flask request context; the malformed
    (no-space) Authorization header path isn't hit by any existing
    endpoint test, so it's covered directly here with a throwaway view.
    """

    def setUp(self):
        super().setUp()
        auth_module._api_keys_cache = {"valid-token": "alice"}

        from flask import Flask

        app = Flask(__name__)
        app.config["TESTING"] = True

        @app.route("/protected")
        @auth_module.require_auth
        def protected():
            from flask import g

            return {"user": g.current_user}

        self.client = app.test_client()

    def test_header_without_a_space_is_rejected(self):
        response = self.client.get(
            "/protected", headers={"Authorization": "Bearervalid-token"}
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["error"], "Invalid authorization header")

    def test_valid_bearer_token_is_accepted(self):
        response = self.client.get(
            "/protected", headers={"Authorization": "Bearer valid-token"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["user"], "alice")


if __name__ == "__main__":
    unittest.main()
