"""
Tests for signing in with an identity provider's token (#182).
"""

import json
import os
import shutil
import tempfile
import time
import unittest
from unittest import mock

try:
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa
except ImportError:  # pragma: no cover - the oidc extra is optional
    raise unittest.SkipTest("PyJWT is not installed")

import yaml

from asimov import access
from asimov.identity import (
    IdentityError,
    InvalidToken,
    Provider,
    Providers,
    TokenGroups,
    identity_path_for,
    load_providers,
    using_identity,
)
from asimov.membership import FileGroupDirectory
from asimov.principal import Principal
from asimov.registry import FileRegistry, ProjectEntry, SingleProjectRegistry

ISSUER = "https://idp.example.org"
AUDIENCE = "asimov-test"


def keypair(kid):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key()))
    public.update(kid=kid, use="sig", alg="RS256")
    return private, public


PRIVATE, PUBLIC = keypair("one")
OTHER, _ = keypair("one")

PROVIDER = {
    "issuer": ISSUER,
    "audience": AUDIENCE,
    "claims": {"identifier": "uid", "name": "name", "accounting": "uid", "groups": "isMemberOf"},
    "groups": [{"match": r"CO:COU:([a-z0-9._-]+):members", "group": r"\1"}],
    "jwks": {"keys": [PUBLIC]},
}


def token(key=PRIVATE, kid="one", **claims):
    now = int(time.time())
    body = {
        "iss": ISSUER, "aud": AUDIENCE, "sub": "http://idp/users/1", "uid": "albert.einstein",
        "name": "Albert Einstein", "iat": now, "exp": now + 600,
        "isMemberOf": ["CO:COU:cbc-pe:members", "CO:members:all", "CO:COU:Bad Name:members"],
    }
    body.update(claims)
    body = {k: v for k, v in body.items() if v is not None}
    return jwt.encode(body, key, algorithm="RS256", headers={"kid": kid})


class TestTokens(unittest.TestCase):
    def setUp(self):
        self.providers = Providers([Provider.from_dict(PROVIDER)])

    def test_a_good_token_says_who_and_which_groups(self):
        identity = self.providers.verify(token())
        self.assertEqual(identity.principal, Principal.person("albert.einstein"))
        self.assertEqual(identity.name, "Albert Einstein")
        self.assertEqual(identity.accounting, "albert.einstein")
        self.assertEqual(identity.groups, {"cbc-pe"})  # the others match no rule, or no name
        self.assertEqual(identity.issuer, ISSUER)

    def test_bad_tokens_are_refused(self):
        now = int(time.time())
        for name, bad in (
            ("expired", token(exp=now - 3600)),
            ("no expiry", token(exp=None)),
            ("for someone else", token(aud="another-service")),
            ("from elsewhere", token(iss="https://evil.example.org")),
            ("forged", token(key=OTHER)),
            ("unknown key", token(kid="two")),
            ("no identifier", token(uid=None)),
            ("not a token", "a.b.c"),
            ("unsigned", jwt.encode({"iss": ISSUER, "aud": AUDIENCE, "uid": "x", "exp": now + 60},
                                    None, algorithm="none")),
        ):
            with self.assertRaises(InvalidToken, msg=name):
                self.providers.verify(bad)

    def test_a_prefix_keeps_providers_apart(self):
        providers = Providers([Provider.from_dict({**PROVIDER, "prefix": "igwn:"})])
        self.assertEqual(providers.verify(token()).principal.identifier, "igwn:albert.einstein")

    def test_groups_may_be_a_comma_separated_string(self):
        identity = self.providers.verify(token(isMemberOf="CO:COU:a:members, CO:COU:b:members"))
        self.assertEqual(identity.groups, {"a", "b"})

    def test_keys_are_discovered_from_the_issuer(self):
        provider = Provider.from_dict({k: v for k, v in PROVIDER.items() if k != "jwks"})
        document = json.dumps({"issuer": ISSUER, "jwks_uri": ISSUER + "/keys"}).encode()
        opened = mock.MagicMock()
        opened.__enter__.return_value = mock.MagicMock(read=lambda *a: document)
        with mock.patch("urllib.request.urlopen", return_value=opened) as urlopen, \
                mock.patch("jwt.PyJWKClient.fetch_data", return_value={"keys": [PUBLIC]}):
            identity = Providers([provider]).verify(token())
        self.assertEqual(identity.principal.identifier, "albert.einstein")
        self.assertIn("/.well-known/openid-configuration", urlopen.call_args[0][0])


class TestConfiguration(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.path = os.path.join(self.dir, "identity.yaml")

    def write(self, data):
        with open(self.path, "w") as handle:
            yaml.safe_dump(data, handle)

    def test_loading(self):
        self.write({"providers": [PROVIDER]})
        self.assertEqual(load_providers(self.path).providers[0].issuer, ISSUER)

    def test_mistakes_are_errors(self):
        for bad in (
            {"providers": {"issuer": ISSUER}},
            {"providers": [{"issuer": ISSUER}]},
            {"providers": [{**PROVIDER, "algorithms": ["HS256"]}]},
            {"providers": [{**PROVIDER, "claims": {"email": "email"}}]},
            {"providers": [{**PROVIDER, "groups": [{"match": "("}]}]},
            {"providers": [PROVIDER, PROVIDER]},
            {"provider": []},
        ):
            self.write(bad)
            with self.assertRaises(IdentityError, msg=bad):
                load_providers(self.path)

    def test_where_the_file_is(self):
        registry = FileRegistry(os.path.join(self.dir, "registry.yaml"))
        self.assertIsNone(identity_path_for(registry))
        self.write({"providers": []})
        self.assertEqual(identity_path_for(registry), self.path)
        self.assertIsNone(identity_path_for(SingleProjectRegistry(self.dir)))

    def test_an_identity_file_alone_turns_grants_on(self):
        self.write({"providers": [PROVIDER]})
        registry = FileRegistry(os.path.join(self.dir, "registry.yaml"))
        policy = access.instance_policy(registry)
        self.assertIsInstance(policy, access.GrantPolicy)
        entry = ProjectEntry(name="p", root=self.dir, groups=["cbc-pe"])
        person = Principal.person("albert.einstein")
        self.assertIsNone(policy.authority(person, entry, access.READ))
        identity = Providers([Provider.from_dict(PROVIDER)]).verify(token())
        with using_identity(identity):
            self.assertEqual(policy.authority(person, entry, access.WRITE).group, "cbc-pe")


class TestTokenGroups(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        path = os.path.join(self.dir, "groups.yaml")
        with open(path, "w") as handle:
            yaml.safe_dump({"admins": ["root"], "groups": {"local": {"members": ["albert.einstein"]}}}, handle)
        self.directory = TokenGroups(FileGroupDirectory(path))
        self.identity = Providers([Provider.from_dict(PROVIDER)]).verify(token())

    def test_token_groups_add_to_local_ones_for_that_person_only(self):
        self.assertEqual(self.directory.groups_of("albert.einstein"), {"local"})
        with using_identity(self.identity):
            self.assertEqual(self.directory.groups_of("albert.einstein"), {"local", "cbc-pe"})
            self.assertEqual(self.directory.groups_of("someone.else"), set())
        self.assertEqual(self.directory.groups_of("albert.einstein"), {"local"})

    def test_admins_come_only_from_the_instance(self):
        self.assertTrue(self.directory.is_admin("root"))
        with using_identity(self.identity):
            self.assertFalse(self.directory.is_admin("albert.einstein"))


if __name__ == "__main__":
    unittest.main()
