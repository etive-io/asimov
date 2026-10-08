"""
A registry of the projects an asimov instance serves.

An instance which serves several projects (see #179) needs to know which
there are and where each one lives. The registry holds that: for each project
a name, the directory it lives in, the groups which own it, and optionally
where its ledger is, where its results are stored, which scheduler it submits
to, and limits on how much it may submit.

Everything which handles a request for a project (the REST API, the MCP
server) asks the registry for the project's :class:`~asimov.context.ProjectContext`
with :meth:`ProjectRegistry.resolve`, and then checks that the caller may do
what they are asking with :func:`asimov.access.authorize`.

Two registries are provided. :class:`FileRegistry` keeps the projects in a YAML
file, and is the one to use for an instance. :class:`SingleProjectRegistry`
wraps one project directory, which is how an instance with one project, or a
project used from the command line, looks the same as one with many.

Examples
--------
Register a project and use it::

    registry = FileRegistry("/etc/asimov/registry.yaml")
    registry.add(ProjectEntry(name="gw-o4", root="/data/gw-o4", groups=["cbc-pe"]))
    with registry.resolve("gw-o4").activate() as project:
        print(project.ledger.get_event())
"""

import abc
import contextlib
import copy
import dataclasses
import os
import re
import tempfile
from typing import Dict, List, Optional

import yaml

__all__ = [
    "AmbiguousProject",
    "FileRegistry",
    "ProjectEntry",
    "ProjectExists",
    "ProjectRegistry",
    "ReadOnlyRegistry",
    "RegistryError",
    "SingleProjectRegistry",
    "UnknownProject",
    "default_registry_path",
    "mask_secrets",
]

#: What a project may be called: it appears in URLs and file names.
NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")

#: The scheduler limits a registry entry's ``quotas`` set on the project. They
#: are the ``[scheduler]`` settings which :mod:`asimov.throttle` reads, so a
#: project's quotas hold for everything which submits for it.
SCHEDULER_QUOTAS = ("max_queued", "max_submit_per_pass", "submit_interval")


class RegistryError(ValueError):
    """Something is wrong with a request to the registry."""


class UnknownProject(RegistryError):
    """There is no project with that name."""

    def __init__(self, name, known):
        self.name = name
        self.known = sorted(known)
        listing = ", ".join(self.known) if self.known else "none"
        super().__init__(f"There is no project called {name!r}. The projects are: {listing}.")


class AmbiguousProject(RegistryError):
    """No project was named, and there is more than one."""

    def __init__(self, known):
        self.known = sorted(known)
        super().__init__(
            "Say which project: " + ", ".join(self.known) + "."
            if self.known
            else "There are no projects."
        )


class ProjectExists(RegistryError):
    """There is already a project with that name."""


class ReadOnlyRegistry(RegistryError):
    """This registry can't be changed."""


def mask_secrets(value):
    """
    ``value`` with the password in any URL in it hidden, for showing to people.

    Parameters
    ----------
    value : str, dict, list or other
        What to mask. Dictionaries and lists are masked all the way down.
    """
    if isinstance(value, str):
        return re.sub(r"(://[^:/@\s]+:)[^@\s]+@", r"\1***@", value)
    if isinstance(value, dict):
        return {k: mask_secrets(v) for k, v in value.items()}
    if isinstance(value, list):
        return [mask_secrets(v) for v in value]
    return value


@dataclasses.dataclass
class ProjectEntry:
    """
    One project in a registry.

    Parameters
    ----------
    name : str
        What the project is called: lower case letters, digits, ``.``, ``_``
        and ``-``, and up to 64 of them. It appears in URLs.
    root : str
        The project's directory.
    groups : list of str
        The groups which own the project.
    ledger : dict, optional
        ``engine`` and ``location`` of the project's ledger, if they aren't
        the ones in the project's own configuration. ``location`` may be a
        database URL, and may refer to environment variables (``$NAME``), so
        that a password needn't be written in the registry.
    storage : str, optional
        Where the project's results are stored.
    scheduler : str, optional
        The scheduler it submits to (its ``[scheduler] type``).
    quotas : dict, optional
        How much it may submit: ``max_queued``, ``max_submit_per_pass`` and
        ``submit_interval`` are applied to the project (see
        :mod:`asimov.throttle`). Others are kept.
    """

    name: str
    root: str
    groups: List[str] = dataclasses.field(default_factory=list)
    ledger: Optional[Dict[str, str]] = None
    storage: Optional[str] = None
    scheduler: Optional[str] = None
    quotas: Dict[str, object] = dataclasses.field(default_factory=dict)

    def __post_init__(self):
        self.validate()

    def validate(self):
        """
        Check the entry makes sense.

        Raises
        ------
        RegistryError
            If it doesn't.
        """
        if not isinstance(self.name, str) or not NAME.match(self.name):
            raise RegistryError(
                f"{self.name!r} is not a project name: use lower case letters, digits, "
                "'.', '_' and '-', starting with a letter or digit, and at most 64 of them."
            )
        if not self.root or not isinstance(self.root, str):
            raise RegistryError(f"Project {self.name!r} needs a root directory.")
        if isinstance(self.groups, str) or not all(isinstance(g, str) for g in self.groups):
            raise RegistryError(f"The groups of {self.name!r} must be a list of names.")
        if self.ledger is not None:
            if not isinstance(self.ledger, dict) or not set(self.ledger) <= {"engine", "location"}:
                raise RegistryError(
                    f"The ledger of {self.name!r} must give an 'engine' and/or a 'location'."
                )
        if not isinstance(self.quotas, dict):
            raise RegistryError(f"The quotas of {self.name!r} must be a mapping.")
        for key in SCHEDULER_QUOTAS:
            value = self.quotas.get(key)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0):
                raise RegistryError(f"The quota {key} of {self.name!r} must be a number, not {value!r}.")

    def to_dict(self, mask=False):
        """
        The entry as plain data, without its name.

        Parameters
        ----------
        mask : bool
            Hide passwords in URLs, so that the result can be shown.
        """
        data = {"root": self.root, "groups": list(self.groups)}
        for key in ("ledger", "storage", "scheduler"):
            value = getattr(self, key)
            if value:
                data[key] = copy.deepcopy(value)
        if self.quotas:
            data["quotas"] = copy.deepcopy(self.quotas)
        return mask_secrets(data) if mask else data

    @classmethod
    def from_dict(cls, name, data, base=None):
        """
        An entry from the plain data ``to_dict`` makes.

        Parameters
        ----------
        name : str
        data : dict
        base : str, optional
            The directory a relative ``root`` is relative to.
        """
        if not isinstance(data, dict):
            raise RegistryError(f"The entry for {name!r} must be a mapping.")
        unknown = set(data) - {"root", "groups", "ledger", "storage", "scheduler", "quotas"}
        if unknown:
            raise RegistryError(f"The entry for {name!r} has unknown keys: {', '.join(sorted(unknown))}.")
        root = data.get("root")
        if isinstance(root, str) and base and not os.path.isabs(root):
            root = os.path.join(base, root)
        return cls(
            name=name,
            root=root,
            groups=list(data.get("groups") or []),
            ledger=data.get("ledger"),
            storage=data.get("storage"),
            scheduler=data.get("scheduler"),
            quotas=dict(data.get("quotas") or {}),
        )

    def context(self):
        """
        The :class:`~asimov.context.ProjectContext` for this project.

        A new one each time: a context holds a ledger, which one request
        shouldn't share with another. The entry's ledger, storage, scheduler
        and quotas are applied to it.

        Raises
        ------
        asimov.context.NoProjectError
            If there is no project in the entry's directory.
        """
        from asimov.context import ProjectContext

        ledger = None
        if self.ledger:
            ledger = {k: os.path.expandvars(v) for k, v in self.ledger.items()}
        context = ProjectContext.from_directory(self.root)
        context.ledger_settings = ledger or {}
        config = context.config
        if self.storage:
            _set(config, "storage", "directory", os.path.expandvars(self.storage))
        if self.scheduler:
            _set(config, "scheduler", "type", self.scheduler)
        for key in SCHEDULER_QUOTAS:
            if self.quotas.get(key) is not None:
                _set(config, "scheduler", key, str(self.quotas[key]))
        return context


def _set(config, section, option, value):
    if not config.has_section(section):
        config.add_section(section)
    config.set(section, option, value)


class ProjectRegistry(abc.ABC):
    """What a registry of projects offers."""

    @abc.abstractmethod
    def list(self):
        """
        The projects, in name order.

        Returns
        -------
        list of ProjectEntry
        """

    @abc.abstractmethod
    def add(self, entry):
        """
        Add a project.

        Raises
        ------
        ProjectExists
            If there is already a project with that name.
        ReadOnlyRegistry
            If the registry can't be changed.
        """

    @abc.abstractmethod
    def remove(self, name):
        """
        Remove a project from the registry. The project itself is left alone.

        Raises
        ------
        UnknownProject
        ReadOnlyRegistry
        """

    def names(self):
        """The names of the projects, in order."""
        return [entry.name for entry in self.list()]

    def get(self, name=None):
        """
        The entry for a project.

        Parameters
        ----------
        name : str, optional
            The project. It may be left out if there is only one.

        Raises
        ------
        UnknownProject
            If there is no such project.
        AmbiguousProject
            If no name is given and there are several projects.
        """
        entries = self.list()
        if name is None:
            if len(entries) == 1:
                return entries[0]
            raise AmbiguousProject([e.name for e in entries])
        for entry in entries:
            if entry.name == name:
                return entry
        raise UnknownProject(name, [e.name for e in entries])

    def resolve(self, name=None):
        """
        The :class:`~asimov.context.ProjectContext` for a project.

        See :meth:`ProjectEntry.context`. This doesn't check that anyone may
        use the project: see :func:`asimov.access.authorize`.

        Raises
        ------
        UnknownProject, AmbiguousProject
            As :meth:`get`.
        """
        return self.get(name).context()


class SingleProjectRegistry(ProjectRegistry):
    """
    A registry of one project, in a directory. It can't be changed.

    Parameters
    ----------
    root : str
        The project's directory.
    name : str, optional
        What to call the project. Defaults to the name in its configuration
        (made lower case, with ``-`` for spaces), or the directory's name.
    """

    def __init__(self, root, name=None):
        self.root = os.path.abspath(root)
        self._name = name

    def _project_name(self):
        if self._name:
            return self._name
        import configparser

        parser = configparser.ConfigParser()
        parser.read(os.path.join(self.root, ".asimov", "asimov.conf"))
        raw = parser.get("project", "name", fallback=None) or os.path.basename(self.root)
        cleaned = re.sub(r"[^a-z0-9._-]+", "-", raw.lower()).strip("-._") or "project"
        return cleaned[:64]

    def list(self):
        return [ProjectEntry(name=self._project_name(), root=self.root)]

    def add(self, entry):
        raise ReadOnlyRegistry("This registry holds one project and can't be changed.")

    def remove(self, name):
        raise ReadOnlyRegistry("This registry holds one project and can't be changed.")


def default_registry_path():
    """
    Where the instance's registry is kept.

    ``$ASIMOV_REGISTRY`` if it is set, otherwise ``asimov/registry.yaml`` in
    the user's configuration directory.
    """
    given = os.environ.get("ASIMOV_REGISTRY")
    if given:
        return given
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "asimov", "registry.yaml")


class FileRegistry(ProjectRegistry):
    """
    A registry kept in a YAML file.

    The file is read each time it is used, so that a change made by another
    process is seen, and written all at once, so that a reader never sees half
    of it. A relative ``root`` in it is relative to the file's directory.

    ::

        projects:
          gw-o4:
            root: /data/projects/gw-o4
            groups: [cbc-pe]
            ledger: {engine: sqlite, location: "sqlite:///data/gw-o4/ledger.db"}
            storage: /results/gw-o4
            scheduler: htcondor
            quotas: {max_queued: 100}

    Parameters
    ----------
    path : str, optional
        The file. Defaults to :func:`default_registry_path`.
    """

    def __init__(self, path=None):
        self.path = os.path.abspath(path or default_registry_path())

    def _load(self):
        try:
            with open(self.path) as handle:
                data = yaml.safe_load(handle) or {}
        except FileNotFoundError:
            return {}
        except yaml.YAMLError as error:
            raise RegistryError(f"The registry {self.path} is not valid YAML: {error}")
        if not isinstance(data, dict) or not isinstance(data.get("projects", {}), dict):
            raise RegistryError(f"The registry {self.path} must have a 'projects' mapping.")
        return data.get("projects") or {}

    def list(self):
        base = os.path.dirname(self.path)
        return sorted(
            (ProjectEntry.from_dict(name, data, base=base) for name, data in self._load().items()),
            key=lambda entry: entry.name,
        )

    @contextlib.contextmanager
    def _locked(self):
        """Hold a lock, so that two changes made at once both happen."""
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        try:
            import fcntl
        except ImportError:  # pragma: no cover - not POSIX
            yield
            return
        with open(self.path + ".lock", "w") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def _save(self, projects):
        scratch = tempfile.NamedTemporaryFile(
            "w", dir=os.path.dirname(self.path), prefix=".registry-", delete=False
        )
        try:
            with scratch:
                yaml.safe_dump({"projects": projects}, scratch, sort_keys=True)
            os.replace(scratch.name, self.path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.remove(scratch.name)
            raise

    def add(self, entry):
        entry.validate()
        with self._locked():
            projects = self._load()
            if entry.name in projects:
                raise ProjectExists(f"There is already a project called {entry.name!r}.")
            projects[entry.name] = entry.to_dict()
            self._save(projects)

    def remove(self, name):
        with self._locked():
            projects = self._load()
            if name not in projects:
                raise UnknownProject(name, list(projects))
            del projects[name]
            self._save(projects)
