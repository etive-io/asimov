"""
Checking that someone may do something to a project.

Whatever handles a request for a project (the REST API, the MCP server) asks
:func:`authorize` before it acts. What is allowed is decided by a *policy*.

The policy asimov starts with, :class:`AllowAll`, allows everything: whoever can
reach an instance can do anything to every project in it, and the instance must
be protected by who can reach it.

An instance with a groups file (see :mod:`asimov.membership`) uses
:class:`GrantPolicy` instead (#183). People belong to groups, and groups hold
roles on projects: nobody is granted a project directly. The groups which own a
project (its registry entry's ``groups``) hold the maintainer role on it; its
``grants`` give other groups other roles::

    projects:
      gw-o4:
        root: /data/gw-o4
        groups: [cbc-pe]
        grants: {cbc-review: [reviewer], ligo-all: [viewer]}

=============  ==========================================================
Role           May
=============  ==========================================================
viewer         read
reviewer       read; review and comment
analyst        read; apply blueprints, comment, label; build and submit
maintainer     everything an analyst or reviewer may, and change the
               project's registry entry and grants
=============  ==========================================================

Instance admins, listed in the groups file, may do anything to any project.
An agent has the authority of the person it acts for, never more. The group
and role which allowed an action are returned by :func:`authorize`, so that
the audit trail can record them as they were at the time (#143).

Examples
--------
A policy which lets only the members of a project's groups write to it::

    class Members(Policy):
        def allows(self, principal, entry, action):
            return action == READ or my_groups(principal) & set(entry.groups)

    set_policy(Members())
"""

__all__ = [
    "ADMIN",
    "AccessDenied",
    "AllowAll",
    "Authority",
    "EXECUTE",
    "GrantPolicy",
    "Policy",
    "READ",
    "REVIEW",
    "ROLES",
    "WRITE",
    "authorize",
    "get_policy",
    "instance_policy",
    "set_policy",
    "with_authority",
]

import dataclasses
import logging
from typing import Optional

logger = logging.getLogger(__name__)

#: Look at a project.
READ = "read"
#: Change a project: apply blueprints, review, comment, label.
WRITE = "write"
#: Run things for a project: build and submit.
EXECUTE = "execute"
#: Review analyses: set their review status, and comment on them.
REVIEW = "review"
#: Change the registry's entry for the project, and its grants.
ADMIN = "admin"

ACTIONS = (READ, WRITE, EXECUTE, REVIEW, ADMIN)

#: What each role may do, from the least to the most a role allows. When
#: several roles would allow an action, the first is the one recorded.
ROLES = {
    "viewer": frozenset({READ}),
    "reviewer": frozenset({READ, REVIEW}),
    "analyst": frozenset({READ, WRITE, EXECUTE}),
    "maintainer": frozenset(ACTIONS),
}

#: The role the groups which own a project hold on it.
OWNER_ROLE = "maintainer"


@dataclasses.dataclass(frozen=True)
class Authority:
    """
    What allowed an action: a role, held through a group.

    Both are ``None`` when a policy allows something without either, as
    :class:`AllowAll` does. An instance admin has ``role="admin"`` and no
    group.
    """

    group: Optional[str] = None
    role: Optional[str] = None


class AccessDenied(PermissionError):
    """The principal may not do that to the project."""


class Policy:
    """Decides what principals may do to projects."""

    def allows(self, principal, entry, action):
        """
        Whether ``principal`` may do ``action`` to the project in ``entry``.

        Parameters
        ----------
        principal : asimov.principal.Principal
        entry : asimov.registry.ProjectEntry
        action : str
            One of :data:`READ`, :data:`WRITE`, :data:`EXECUTE`, :data:`ADMIN`.

        Returns
        -------
        bool
        """
        raise NotImplementedError

    def authority(self, principal, entry, action):
        """
        What allows ``principal`` to do ``action`` to the project, if anything.

        A policy which knows about groups and roles overrides this. By
        default it is :meth:`allows`, with no group or role.

        Returns
        -------
        Authority or None
            ``None`` if the action isn't allowed.
        """
        return Authority() if self.allows(principal, entry, action) else None


class AllowAll(Policy):
    """Allows everything. This is what asimov starts with."""

    def allows(self, principal, entry, action):
        return True


class GrantPolicy(Policy):
    """
    Allows what the roles a person's groups hold on a project allow.

    Parameters
    ----------
    directory : asimov.membership.GroupDirectory
        Says which groups a person is in, and who the instance admins are.

    Notes
    -----
    The principal's authority is that of the person it acts for in the end
    (:attr:`~asimov.principal.Principal.on_behalf_of`): an agent acting for
    nobody has none. The monitor, which is the instance itself, may read,
    change and run what is in a project, but not review it or administer it.
    """

    MONITOR = frozenset({READ, WRITE, EXECUTE})

    def __init__(self, directory):
        self.directory = directory

    def allows(self, principal, entry, action):
        return self.authority(principal, entry, action) is not None

    def roles(self, entry):
        """The roles each group holds on the project in ``entry``."""
        held = {group: set(roles) for group, roles in getattr(entry, "grants", {}).items()}
        for group in entry.groups:
            held.setdefault(group, set()).add(OWNER_ROLE)
        return held

    def authority(self, principal, entry, action):
        person = principal.on_behalf_of
        if person.kind == "monitor":
            return Authority(role="monitor") if action in self.MONITOR else None
        if person.kind != "person":
            return None
        try:
            if self.directory.is_admin(person.identifier):
                return Authority(role="admin")
            member_of = self.directory.groups_of(person.identifier)
        except Exception:
            # A groups file which can't be read denies, rather than allows.
            logger.exception("Could not read the instance's groups; denying %s", action)
            return None
        held = self.roles(entry)
        for role, allowed in ROLES.items():
            if action not in allowed:
                continue
            for group in sorted(member_of & set(held)):
                if role in held[group]:
                    return Authority(group=group, role=role)
        return None


def instance_policy(registry):
    """
    The policy for an instance serving ``registry``, if it has a groups file.

    Parameters
    ----------
    registry : asimov.registry.ProjectRegistry

    Returns
    -------
    GrantPolicy or None
        ``None`` if the instance has no groups file, in which case the policy
        in force (:func:`get_policy`) applies.
    """
    from asimov.membership import FileGroupDirectory, groups_path_for

    path = groups_path_for(registry)
    if path is None:
        return None
    return GrantPolicy(FileGroupDirectory(path))


_policy = AllowAll()


def get_policy():
    """The policy in force."""
    return _policy


def set_policy(policy):
    """
    Put a policy in force.

    Returns
    -------
    Policy
        The policy it replaced.
    """
    global _policy
    previous, _policy = _policy, policy
    return previous


def authorize(principal, entry, action, policy=None):
    """
    Check that ``principal`` may do ``action`` to the project in ``entry``.

    Parameters
    ----------
    principal : asimov.principal.Principal
    entry : asimov.registry.ProjectEntry
    action : str or tuple of str
        One of the actions, or several, any one of which is enough (as
        commenting needs :data:`WRITE` or :data:`REVIEW`).
    policy : Policy, optional
        The policy to ask. Defaults to the one in force (:func:`get_policy`);
        a server for an instance with groups passes its own.

    Returns
    -------
    Authority
        What allowed it, to be recorded with what is done.

    Raises
    ------
    AccessDenied
        If the policy doesn't allow it. The message doesn't say what else the
        principal could do.
    ValueError
        If ``action`` isn't one of the actions.
    """
    wanted = (action,) if isinstance(action, str) else tuple(action)
    for one in wanted:
        if one not in ACTIONS:
            raise ValueError(f"{one!r} is not an action: use one of {', '.join(ACTIONS)}.")
    policy = policy if policy is not None else _policy
    for one in wanted:
        found = policy.authority(principal, entry, one)
        if found is not None:
            return found
    raise AccessDenied(
        f"{principal.identifier} may not {' or '.join(wanted)} the project {entry.name!r}."
    )


def with_authority(principal, authority):
    """``principal``, recording the group and role in ``authority``, if any."""
    if authority is None or (authority.group is None and authority.role is None):
        return principal
    return dataclasses.replace(principal, group=authority.group, role=authority.role)
