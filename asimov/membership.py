"""
Who belongs to which group, for an instance which serves several projects (#183).

People join groups, and groups hold roles on projects (see :mod:`asimov.access`).
This module says which groups a person is in. For now the groups are local ones,
kept by the instance's admins in a YAML file next to the registry::

    admins: [dw]
    groups:
      cbc-pe:
        members: [dw, jane]
      cbc-review:
        members: [sam]

Membership is flat: a group can't be a member of another. Groups from an
identity provider's token claims (#182) will plug in as another
:class:`GroupDirectory`.

The file is ``$ASIMOV_GROUPS`` if that is set, otherwise ``groups.yaml`` in the
directory of the registry file. While there is no such file, the instance
allows everything, as it did before groups existed.
"""

import contextlib
import os
import re
import tempfile

import yaml

__all__ = [
    "FileGroupDirectory",
    "GroupDirectory",
    "MembershipError",
    "default_groups_path",
    "groups_path_for",
]

#: What a group may be called: as for a project.
GROUP_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


class MembershipError(ValueError):
    """The groups file doesn't make sense."""


class GroupDirectory:
    """Says which groups a person is in, and whether they are an instance admin."""

    def groups_of(self, identifier):
        """
        The groups the person called ``identifier`` is in.

        Returns
        -------
        set of str
        """
        raise NotImplementedError

    def is_admin(self, identifier):
        """Whether the person called ``identifier`` is an instance admin."""
        return False


class FileGroupDirectory(GroupDirectory):
    """
    Groups kept in a YAML file.

    The file is read each time it is used, so a change to membership applies
    to the next request without a restart. A file which can't be read, or
    doesn't make sense, raises :class:`MembershipError`, so that a mistake in
    it denies access rather than allowing it.

    Parameters
    ----------
    path : str
    """

    def __init__(self, path):
        self.path = os.path.abspath(path)

    def load(self):
        """
        The admins and groups in the file.

        Returns
        -------
        tuple of (set of str, dict of str to set of str)
            The admins, and the members of each group.

        Raises
        ------
        MembershipError
        """
        try:
            with open(self.path) as handle:
                data = yaml.safe_load(handle) or {}
        except (OSError, yaml.YAMLError) as error:
            raise MembershipError(f"The groups file {self.path} could not be read: {error}")
        if not isinstance(data, dict) or set(data) - {"admins", "groups"}:
            raise MembershipError(
                f"The groups file {self.path} may only have 'admins' and 'groups'."
            )
        admins = data.get("admins") or []
        if not isinstance(admins, list) or not all(isinstance(a, str) for a in admins):
            raise MembershipError(f"The admins in {self.path} must be a list of names.")
        groups = data.get("groups") or {}
        if not isinstance(groups, dict):
            raise MembershipError(f"The groups in {self.path} must be a mapping.")
        members = {}
        for name, group in groups.items():
            if not isinstance(name, str) or not GROUP_NAME.match(name):
                raise MembershipError(f"{name!r} in {self.path} is not a group name.")
            if not isinstance(group, dict) or set(group) - {"members", "description"}:
                raise MembershipError(
                    f"The group {name!r} in {self.path} may only have 'members' and 'description'."
                )
            listed = group.get("members") or []
            if not isinstance(listed, list) or not all(isinstance(m, str) for m in listed):
                raise MembershipError(f"The members of {name!r} in {self.path} must be a list of names.")
            members[name] = set(listed)
        return set(admins), members

    def change_members(self, group, add=(), remove=()):
        """
        Add people to ``group`` and take people out of it, creating it if needed.

        The file is written all at once, under a lock, so that two changes
        made together both happen.

        Returns
        -------
        set of str
            The group's members afterwards.
        """
        if not GROUP_NAME.match(group):
            raise MembershipError(f"{group!r} is not a group name.")
        import fcntl

        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path + ".lock", "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if os.path.exists(self.path):
                admins, members = self.load()
                with open(self.path) as handle:
                    data = yaml.safe_load(handle) or {}
            else:
                admins, members, data = set(), {}, {}
            people = (members.get(group, set()) | set(add)) - set(remove)
            groups = data.setdefault("groups", {}) or {}
            data["groups"] = groups
            entry = groups.setdefault(group, {}) or {}
            groups[group] = entry
            entry["members"] = sorted(people)
            scratch = tempfile.NamedTemporaryFile(
                "w", dir=os.path.dirname(self.path), prefix=".groups-", delete=False
            )
            try:
                with scratch:
                    yaml.safe_dump(data, scratch, sort_keys=True)
                os.replace(scratch.name, self.path)
            except BaseException:
                with contextlib.suppress(OSError):
                    os.remove(scratch.name)
                raise
        return people

    def groups_of(self, identifier):
        _, members = self.load()
        return {name for name, people in members.items() if identifier in people}

    def is_admin(self, identifier):
        admins, _ = self.load()
        return identifier in admins


def default_groups_path(registry_path):
    """Where the groups file of the registry at ``registry_path`` is, or would be."""
    return os.environ.get("ASIMOV_GROUPS") or os.path.join(
        os.path.dirname(os.path.abspath(registry_path)), "groups.yaml"
    )


def groups_path_for(registry):
    """
    The groups file of the instance serving ``registry``, if there is one.

    Only a registry kept in a file (:class:`~asimov.registry.FileRegistry`)
    has one: serving a single project directory allows everything, as running
    the command line in it does. The file is ``$ASIMOV_GROUPS`` if it is set
    (it needn't exist yet: a missing file denies everything, rather than
    allowing it), otherwise ``groups.yaml`` beside the registry's file, if
    that exists.

    Returns
    -------
    str or None
    """
    path = getattr(registry, "path", None)
    if not path:
        return None
    given = os.environ.get("ASIMOV_GROUPS")
    if given:
        return given
    beside = os.path.join(os.path.dirname(path), "groups.yaml")
    return beside if os.path.exists(beside) else None
