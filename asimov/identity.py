"""
Who a request is from, from an OpenID Connect token (#182).

An identity provider (IdP), such as CILogon for IGWN, logs a person in and
gives their client a signed token (a JWT). The client sends it to asimov as
``Authorization: Bearer <token>``. asimov never sees a password: it checks the
token's signature against the provider's published keys, and that it was
issued by the provider, for asimov, and hasn't expired. Then it reads who the
person is, and which groups they are in, from the token's *claims*.

Which claims mean what differs between providers, so each provider has a
*claim mapping*. Providers are listed in ``identity.yaml`` beside the registry
(or the file named by ``$ASIMOV_IDENTITY``)::

    providers:
      - issuer: https://cilogon.org
        audience: asimov-prod
        claims:
          identifier: sub            # the person's name in asimov
          name: name                 # shown to people
          accounting: uid            # for accounting_group_user (#181)
          groups: isMemberOf         # a list of group names
        groups:                      # how those become asimov groups
          - match: '^CO:COU:([a-z0-9._-]+):members$'
            group: '\\1'

A provider's keys are found from ``issuer`` by OIDC discovery
(``/.well-known/openid-configuration``), or given by ``jwks_uri``, or written
in the file as ``jwks`` for an instance which can't reach the provider.

Groups which no rule matches are ignored. Those which match are added, for
that request, to the groups the person is in locally (``groups.yaml``, see
:mod:`asimov.membership`), so membership follows each login.

Checking tokens needs PyJWT: ``pip install asimov[oidc]``.
"""

import contextlib
import dataclasses
import json
import os
import re
import urllib.request
from contextvars import ContextVar
from typing import Dict, List, Optional, Tuple

import yaml

from asimov.membership import GROUP_NAME
from asimov.principal import Principal

__all__ = [
    "ClaimMapping",
    "Identity",
    "IdentityError",
    "InvalidToken",
    "Provider",
    "Providers",
    "current_identity",
    "identity_path_for",
    "load_providers",
    "using_identity",
]

#: How far clocks may disagree, in seconds, when checking a token's times.
LEEWAY = 30

#: Signature algorithms accepted unless a provider says otherwise. Never "none",
#: and never a shared-secret algorithm, since the keys are public.
ALGORITHMS = ("RS256", "RS384", "RS512", "ES256", "ES384", "PS256")


class IdentityError(ValueError):
    """The identity configuration doesn't make sense."""


class InvalidToken(Exception):
    """A token isn't one asimov accepts. The message says why, for the log."""


@dataclasses.dataclass(frozen=True)
class ClaimMapping:
    """Which of a provider's claims say what."""

    identifier: str = "sub"
    name: Optional[str] = "name"
    accounting: Optional[str] = None
    groups: Optional[str] = None


@dataclasses.dataclass(frozen=True)
class Identity:
    """
    Who a token says the request is from.

    Attributes
    ----------
    principal : Principal
        The person.
    name : str or None
        Their name, for showing.
    accounting : str or None
        The name they are charged under (#181).
    groups : frozenset of str
        The asimov groups their token's groups map to.
    issuer : str
        The provider which vouched for them.
    """

    principal: Principal
    name: Optional[str]
    accounting: Optional[str]
    groups: frozenset
    issuer: str


@dataclasses.dataclass
class Provider:
    """
    One identity provider, and how to read its tokens.

    Parameters
    ----------
    issuer : str
        Exactly the ``iss`` its tokens carry.
    audience : str
        The ``aud`` its tokens for asimov carry: usually asimov's client ID.
    claims : ClaimMapping
    groups : list of (re.Pattern, str)
        Rules turning a group claim value into an asimov group: the first
        whose pattern matches wins, and its template (``\\1`` for the first
        bracket) is the group.
    prefix : str
        Put in front of every identifier from this provider, so that two
        providers' people can't be mistaken for each other.
    jwks_uri, jwks
        Where its signing keys are, or the keys themselves.
    algorithms : tuple of str
    """

    issuer: str
    audience: str
    claims: ClaimMapping = dataclasses.field(default_factory=ClaimMapping)
    groups: List[Tuple[re.Pattern, str]] = dataclasses.field(default_factory=list)
    prefix: str = ""
    jwks_uri: Optional[str] = None
    jwks: Optional[Dict] = None
    algorithms: Tuple[str, ...] = ALGORITHMS
    _keys: object = dataclasses.field(default=None, repr=False, compare=False)

    @classmethod
    def from_dict(cls, data):
        """A provider from its entry in the identity file."""
        if not isinstance(data, dict):
            raise IdentityError("Each provider must be a mapping.")
        known = {"issuer", "audience", "claims", "groups", "prefix", "jwks_uri", "jwks", "algorithms"}
        unknown = set(data) - known
        if unknown:
            raise IdentityError(f"A provider has unknown keys: {', '.join(sorted(unknown))}.")
        for key in ("issuer", "audience"):
            if not isinstance(data.get(key), str) or not data[key]:
                raise IdentityError(f"Each provider needs an {key}.")
        claims = data.get("claims") or {}
        if not isinstance(claims, dict) or set(claims) - {"identifier", "name", "accounting", "groups"}:
            raise IdentityError(
                f"The claims of {data['issuer']} may only give identifier, name, accounting and groups."
            )
        rules = []
        for rule in data.get("groups") or []:
            if not isinstance(rule, dict) or set(rule) != {"match", "group"}:
                raise IdentityError(f"Each group rule of {data['issuer']} needs a 'match' and a 'group'.")
            try:
                rules.append((re.compile(rule["match"]), str(rule["group"])))
            except re.error as error:
                raise IdentityError(f"{rule['match']!r} is not a pattern: {error}")
        algorithms = tuple(data.get("algorithms") or ALGORITHMS)
        bad = [a for a in algorithms if a not in ALGORITHMS]
        if bad:
            raise IdentityError(f"{', '.join(bad)} is not allowed: use {', '.join(ALGORITHMS)}.")
        return cls(
            issuer=data["issuer"],
            audience=data["audience"],
            claims=ClaimMapping(**claims),
            groups=rules,
            prefix=str(data.get("prefix") or ""),
            jwks_uri=data.get("jwks_uri"),
            jwks=data.get("jwks"),
            algorithms=algorithms,
        )

    def signing_key(self, token):
        """The key the token says it was signed with, from this provider's keys."""
        jwt = _jwt()
        if self.jwks is not None:
            header = jwt.get_unverified_header(token)
            keys = jwt.PyJWKSet.from_dict(self.jwks).keys
            for key in keys:
                if key.key_id == header.get("kid") or (len(keys) == 1 and "kid" not in header):
                    return key.key
            raise InvalidToken("The token was signed with a key the provider doesn't list.")
        if self._keys is None:
            self._keys = jwt.PyJWKClient(self.jwks_uri or _discover(self.issuer), cache_keys=True)
        try:
            return self._keys.get_signing_key_from_jwt(token).key
        except jwt.PyJWKClientError as error:
            raise InvalidToken(f"The provider's keys could not be used: {error}")

    def map_group(self, value):
        """The asimov group a group claim value is, or ``None``."""
        for pattern, template in self.groups:
            found = pattern.fullmatch(value)
            if found:
                group = found.expand(template)
                return group if GROUP_NAME.match(group) else None
        return None

    def identify(self, claims):
        """The :class:`Identity` in a token's checked claims."""
        mapping = self.claims
        identifier = claims.get(mapping.identifier)
        if not isinstance(identifier, str) or not identifier.strip():
            raise InvalidToken(f"The token has no {mapping.identifier!r} claim to identify the person.")
        values = claims.get(mapping.groups) if mapping.groups else None
        if isinstance(values, str):
            values = values.split(",")
        groups = set()
        for value in values or []:
            group = self.map_group(str(value).strip()) if isinstance(value, str) else None
            if group:
                groups.add(group)

        def text(claim):
            value = claims.get(claim) if claim else None
            return value if isinstance(value, str) else None

        return Identity(
            principal=Principal.person(self.prefix + identifier),
            name=text(mapping.name),
            accounting=text(mapping.accounting),
            groups=frozenset(groups),
            issuer=self.issuer,
        )


class Providers:
    """The identity providers an instance trusts."""

    def __init__(self, providers):
        self.providers = list(providers)
        issuers = [p.issuer for p in self.providers]
        if len(set(issuers)) != len(issuers):
            raise IdentityError("Each issuer may be listed only once.")

    def __bool__(self):
        return bool(self.providers)

    def verify(self, token):
        """
        Check ``token`` and say who it is from.

        Returns
        -------
        Identity

        Raises
        ------
        InvalidToken
            If it isn't a token from one of the providers, for asimov, signed
            by the provider, and in date.
        """
        jwt = _jwt()
        try:
            unverified = jwt.decode(token, options={"verify_signature": False})
        except jwt.PyJWTError as error:
            raise InvalidToken(f"This is not a token: {error}")
        issuer = unverified.get("iss")
        provider = next((p for p in self.providers if p.issuer == issuer), None)
        if provider is None:
            raise InvalidToken(f"Tokens from {issuer!r} are not accepted.")
        try:
            claims = jwt.decode(
                token,
                provider.signing_key(token),
                algorithms=list(provider.algorithms),
                audience=provider.audience,
                issuer=provider.issuer,
                leeway=LEEWAY,
                options={"require": ["exp", "iss", "aud"]},
            )
        except jwt.PyJWTError as error:
            raise InvalidToken(f"The token from {issuer} was refused: {error}")
        return provider.identify(claims)


def _jwt():
    try:
        import jwt
    except ImportError:  # pragma: no cover - depends on the environment
        raise IdentityError("Checking identity tokens needs PyJWT: pip install asimov[oidc]")
    return jwt


def _discover(issuer):
    """The provider's key set URL, from its OIDC discovery document."""
    url = issuer.rstrip("/") + "/.well-known/openid-configuration"
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            document = json.load(response)
    except (OSError, ValueError) as error:
        raise InvalidToken(f"The provider {issuer} could not be asked for its keys: {error}")
    if document.get("issuer") != issuer or not document.get("jwks_uri"):
        raise InvalidToken(f"The provider {issuer} did not describe itself properly.")
    return document["jwks_uri"]


def load_providers(path):
    """
    The providers in an identity file.

    Raises
    ------
    IdentityError
    """
    try:
        with open(path) as handle:
            data = yaml.safe_load(handle) or {}
    except (OSError, yaml.YAMLError) as error:
        raise IdentityError(f"The identity file {path} could not be read: {error}")
    if not isinstance(data, dict) or set(data) - {"providers"}:
        raise IdentityError(f"The identity file {path} may only have 'providers'.")
    listed = data.get("providers") or []
    if not isinstance(listed, list):
        raise IdentityError(f"The providers in {path} must be a list.")
    providers = Providers(Provider.from_dict(p) for p in listed)
    if providers:
        _jwt()
    return providers


def identity_path_for(registry):
    """
    The identity file of the instance serving ``registry``, if there is one.

    ``$ASIMOV_IDENTITY`` if it is set, otherwise ``identity.yaml`` beside a
    registry file, if that exists. Serving a single project directory has none.
    """
    path = getattr(registry, "path", None)
    if not path:
        return None
    given = os.environ.get("ASIMOV_IDENTITY")
    if given:
        return given
    beside = os.path.join(os.path.dirname(path), "identity.yaml")
    return beside if os.path.exists(beside) else None


# The identity the request in progress in this thread or task proved.
_identity: ContextVar = ContextVar("asimov_identity", default=None)


def current_identity():
    """The identity the request in progress proved with a token, if any."""
    return _identity.get()


@contextlib.contextmanager
def using_identity(identity):
    """Make ``identity`` the current one in the block (``None`` for none)."""
    token = _identity.set(identity)
    try:
        yield identity
    finally:
        _identity.reset(token)


class TokenGroups:
    """
    A group directory which adds the groups the current request's token gave.

    Wraps the instance's own directory (:mod:`asimov.membership`), so a person
    is in their local groups and, for the request their token came with, the
    groups it maps to.
    """

    def __init__(self, directory=None):
        self.directory = directory

    def groups_of(self, identifier):
        groups = set(self.directory.groups_of(identifier)) if self.directory else set()
        identity = current_identity()
        if identity is not None and identity.principal.identifier == identifier:
            groups |= identity.groups
        return groups

    def is_admin(self, identifier):
        # Being an instance admin is decided by the instance, never by a token.
        return bool(self.directory) and self.directory.is_admin(identifier)
