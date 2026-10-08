"""
Checking that someone may do something to a project.

Whatever handles a request for a project (the REST API, the MCP server) asks
:func:`authorize` before it acts. What is allowed is decided by a *policy*. The
policy asimov starts with allows everything: until projects have groups with
roles (#183), whoever can reach an instance can do anything to every project in
it, and the instance must be protected by who can reach it. Putting the check
at each place a request is handled means that a real policy, once there is one,
applies without those places changing.

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
    "EXECUTE",
    "Policy",
    "READ",
    "WRITE",
    "authorize",
    "get_policy",
    "set_policy",
]

#: Look at a project.
READ = "read"
#: Change a project: apply blueprints, review, comment, label.
WRITE = "write"
#: Run things for a project: build and submit.
EXECUTE = "execute"
#: Change the registry's entry for the project.
ADMIN = "admin"

ACTIONS = (READ, WRITE, EXECUTE, ADMIN)


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


class AllowAll(Policy):
    """Allows everything. This is what asimov starts with."""

    def allows(self, principal, entry, action):
        return True


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


def authorize(principal, entry, action):
    """
    Check that ``principal`` may do ``action`` to the project in ``entry``.

    Raises
    ------
    AccessDenied
        If the policy doesn't allow it. The message doesn't say what else the
        principal could do.
    ValueError
        If ``action`` isn't one of the actions.
    """
    if action not in ACTIONS:
        raise ValueError(f"{action!r} is not an action: use one of {', '.join(ACTIONS)}.")
    if not _policy.allows(principal, entry, action):
        raise AccessDenied(f"{principal.identifier} may not {action} the project {entry.name!r}.")
