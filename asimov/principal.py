"""
Who, or what, is making a change.

A :class:`Principal` names the party behind an action on a project: a
person, an agent (for example an MCP client) or the monitor, and who they
are acting for. Audit records (#143), the accounting identity charged for
an analysis (#181), guardrails (#145) and attribution of agent writes (#68)
all need the same answer, so they share this definition.

A principal says *who*. It makes no decision about what they may do, and
does no authentication: the identity layer which will supply principals with
a group and role (#182, #183) plugs in through
:func:`set_principal_provider`, and a deployment with no such layer gets the
local user.

Examples
--------
The principal an action is attributed to::

    from asimov.principal import current_principal

    current_principal()                # the local user, on the command line

An agent acting for a person, for the length of a request::

    from asimov.principal import Principal, acting_as

    agent = Principal.agent("claude-session-1", acting_for=Principal.person("dw"))
    with acting_as(agent):
        ...  # changes made here are attributed to the agent, for dw
"""

import contextlib
import getpass
import os
import urllib.parse
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Callable, Optional

__all__ = [
    "KINDS",
    "Principal",
    "acting_as",
    "current_principal",
    "default_principal",
    "set_principal_provider",
]

#: The kinds of principal.
KINDS = ("person", "agent", "monitor")

_PROV_TYPES = {
    "person": "prov:Person",
    "agent": "prov:SoftwareAgent",
    "monitor": "prov:SoftwareAgent",
}


@dataclass(frozen=True)
class Principal:
    """
    The party making a change, and who they act for.

    Parameters
    ----------
    kind : str
        ``"person"``, ``"agent"`` or ``"monitor"``.
    identifier : str
        Names the principal within its kind: a user name, an agent or session
        name.
    acting_for : Principal, optional
        Who this principal is acting on behalf of. An agent acts for the
        person who asked it to.
    group : str, optional
        The group which gave this principal its authority. Set by the
        identity layer (#183), and recorded as it was at the time.
    role : str, optional
        The role held through that group, likewise.
    """

    kind: str
    identifier: str
    acting_for: Optional["Principal"] = None
    group: Optional[str] = None
    role: Optional[str] = None

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError(
                f"A principal's kind must be one of {', '.join(KINDS)}, not {self.kind!r}"
            )
        if not isinstance(self.identifier, str) or not self.identifier.strip():
            raise ValueError("A principal needs an identifier")
        if self.acting_for is not None and not isinstance(self.acting_for, Principal):
            raise TypeError("acting_for must be a Principal")

    @classmethod
    def person(cls, identifier, **kwargs):
        """A person."""
        return cls("person", identifier, **kwargs)

    @classmethod
    def agent(cls, identifier, **kwargs):
        """An agent, such as an MCP client. Say who it acts for with ``acting_for``."""
        return cls("agent", identifier, **kwargs)

    @classmethod
    def monitor(cls):
        """The monitor, which acts on behalf of nobody in particular."""
        return cls("monitor", "asimov-monitor")

    @classmethod
    def local_user(cls):
        """The person running asimov, by their operating system user name."""
        return cls.person(_local_username())

    @property
    def on_behalf_of(self):
        """The person ultimately responsible: follows ``acting_for`` to its end."""
        principal = self
        while principal.acting_for is not None:
            principal = principal.acting_for
        return principal

    def to_dict(self):
        """
        The principal as plain data, for storing in a ledger.

        Fields which aren't set are left out, so a lone person is just
        ``{"kind": "person", "identifier": "dw"}``.
        """
        data = {"kind": self.kind, "identifier": self.identifier}
        if self.acting_for is not None:
            data["acting for"] = self.acting_for.to_dict()
        if self.group is not None:
            data["group"] = self.group
        if self.role is not None:
            data["role"] = self.role
        return data

    @classmethod
    def from_dict(cls, data):
        """
        Rebuild a principal from :meth:`to_dict`.

        Raises
        ------
        ValueError
            If ``data`` isn't a principal.
        """
        if not isinstance(data, dict) or "kind" not in data or "identifier" not in data:
            raise ValueError(f"This is not a principal: {data!r}")
        acting_for = data.get("acting for")
        return cls(
            kind=data["kind"],
            identifier=data["identifier"],
            acting_for=None if acting_for is None else cls.from_dict(acting_for),
            group=data.get("group"),
            role=data.get("role"),
        )

    @property
    def prov_id(self):
        """The identifier of this principal as a PROV agent."""
        quoted = urllib.parse.quote(self.identifier, safe="")
        return f"urn:asimov:agent:{self.kind}:{quoted}"

    def to_prov(self):
        """
        The principal as W3C PROV agents, in the form of the provenance export.

        Returns
        -------
        list of dict
            JSON-LD nodes for this principal, followed by those it acts for.
            Each is a ``prov:Person`` or ``prov:SoftwareAgent`` and refers
            to the next with ``prov:actedOnBehalfOf``.
        """
        node = {
            "@id": self.prov_id,
            "@type": _PROV_TYPES[self.kind],
            "asimov:name": self.identifier,
            "asimov:kind": self.kind,
        }
        if self.group is not None:
            node["asimov:group"] = self.group
        if self.role is not None:
            node["asimov:role"] = self.role
        nodes = [node]
        if self.acting_for is not None:
            node["prov:actedOnBehalfOf"] = {"@id": self.acting_for.prov_id}
            nodes.extend(self.acting_for.to_prov())
        return nodes

    def __str__(self):
        if self.acting_for is not None:
            return f"{self.identifier} (for {self.acting_for})"
        return self.identifier


def _local_username():
    """The operating system user name, which may not be in the password database."""
    try:
        return getpass.getuser()
    except (KeyError, OSError, ImportError):
        return os.environ.get("USER") or os.environ.get("LOGNAME") or "unknown"


# The principal chosen by ``acting_as()`` in this thread or task.
_acting_as: ContextVar = ContextVar("asimov_acting_as", default=None)

# What supplies the principal when nothing has said who is acting.
_provider: Optional[Callable[[], Optional[Principal]]] = None


def set_principal_provider(provider):
    """
    Set what supplies the principal when none has been chosen.

    This is the plug point for an identity layer (#182, #183): for a
    request, it returns who made it, with group and role. It is called each
    time a principal is needed, so it can look at the request in progress.
    It may return ``None`` to leave the choice to the default.

    Parameters
    ----------
    provider : callable or None
        A function taking no arguments and returning a :class:`Principal`
        or ``None``. ``None`` removes the provider.

    Returns
    -------
    callable or None
        The provider this replaces.
    """
    global _provider
    previous, _provider = _provider, provider
    return previous


def default_principal():
    """The principal when nobody has said: the local user."""
    return Principal.local_user()


def current_principal():
    """
    Who is making the change now.

    In order: the principal chosen by :func:`acting_as`; the active
    project's own (``ProjectContext.principal``, which the monitor sets);
    what the provider from :func:`set_principal_provider` returns; and the
    local user.

    Returns
    -------
    Principal
    """
    chosen = _acting_as.get()
    if chosen is not None:
        return chosen

    from asimov.context import get_active_context

    context = get_active_context()
    if context is not None and context.principal is not None:
        return context.principal

    if _provider is not None:
        supplied = _provider()
        if supplied is not None:
            return supplied

    return default_principal()


@contextlib.contextmanager
def acting_as(principal):
    """
    Attribute what happens in the block to ``principal``.

    Applies to the current thread or task only, so requests handled side by
    side, even for the same project, are each attributed to their own caller.
    Blocks nest.

    Parameters
    ----------
    principal : Principal
        Who is acting.
    """
    if not isinstance(principal, Principal):
        raise TypeError("acting_as needs a Principal")
    token = _acting_as.set(principal)
    try:
        yield principal
    finally:
        _acting_as.reset(token)
