"""
The context an asimov operation runs in: one project, explicitly.

Asimov grew up assuming one process serves one project, found from the
current directory. A :class:`ProjectContext` gathers what that project is
(its configuration, ledger, directories, storage and scheduler) into one
object which can be passed around, and the *active* context is tracked with
a :class:`contextvars.ContextVar`, so each thread or asyncio task has its
own.

Code which is handed no context gets the *ambient* one: the project in the
current working directory, which is exactly what the command line has
always done. ``asimov.config`` and ``asimov.current_ledger`` are shims which
read the active context, so existing code does not change.

Examples
--------
Operate on a particular project without changing directory::

    from asimov.context import ProjectContext

    ctx = ProjectContext.from_directory("/projects/o4-events")
    with ctx.activate():
        ...  # asimov.config and get_ledger() now refer to this project

    with ctx.transaction():
        ctx.ledger.add_event(event)   # persisted when the block ends...
        raise RuntimeError            # ...unless it raises, which undoes it

The Python and REST APIs take a project through this object.
"""

import configparser
import contextlib
import os
from contextvars import ContextVar

__all__ = [
    "ProjectContext",
    "ConfigProxy",
    "read_config",
    "current_context",
    "get_active_context",
    "NoProjectError",
]

_PACKAGE = "asimov"

# The context set by ``ProjectContext.activate()`` in this thread or task.
_active_context: ContextVar = ContextVar("asimov_project_context", default=None)


class NoProjectError(RuntimeError):
    """There is no asimov project to operate on."""


def _config_locations(root):
    """
    Where configuration is read from, lowest precedence first.

    The project's own file replaces the one in the current directory which
    the process-wide configuration reads.
    """
    return [
        f"/etc/{_PACKAGE}",
        os.path.join(os.path.expanduser("~"), f".{_PACKAGE}"),
        os.path.join(os.path.expanduser("~"), ".config", _PACKAGE, f"{_PACKAGE}.conf"),
        os.path.join(root, ".asimov", f"{_PACKAGE}.conf"),
    ]


def default_config_text():
    """The text of the configuration which ships with asimov."""
    try:
        from importlib.resources import files
    except ImportError:  # pragma: no cover
        from importlib_resources import files
    return files(_PACKAGE).joinpath(f"{_PACKAGE}.conf").read_bytes().decode("utf8")


def read_config(root=None):
    """
    Read the configuration for the project at ``root``.

    Layers the defaults which ship with asimov, then the system, user and
    finally the project's own ``.asimov/asimov.conf``. With no ``root`` the
    current directory is used, which is what importing asimov does.

    Parameters
    ----------
    root : str, optional
        The project's root directory.

    Returns
    -------
    configparser.ConfigParser
    """
    root = os.curdir if root is None else root
    parser = configparser.ConfigParser()
    parser.read_string(default_config_text())
    parser.read(_config_locations(root))
    return parser


class ConfigProxy:
    """
    Stands in for a ``ConfigParser``, reading whichever one is active.

    ``asimov.config`` is one of these. It forwards every operation to the
    configuration of the active :class:`ProjectContext`, or to the process
    default when none is active, so module-level ``from asimov import
    config`` keeps working while following the project in force.
    """

    def __init__(self, default):
        object.__setattr__(self, "_default", default)

    def _target(self):
        context = _active_context.get()
        return self._default if context is None else context.config

    def __getattr__(self, name):
        return getattr(self._target(), name)

    def __setattr__(self, name, value):
        setattr(self._target(), name, value)

    def __delattr__(self, name):
        delattr(self._target(), name)

    def __getitem__(self, key):
        return self._target()[key]

    def __setitem__(self, key, value):
        self._target()[key] = value

    def __delitem__(self, key):
        del self._target()[key]

    def __contains__(self, key):
        return key in self._target()

    def __iter__(self):
        return iter(self._target())

    def __len__(self):
        return len(self._target())

    def __repr__(self):
        return f"<ConfigProxy for {self._target()!r}>"


class ProjectContext:
    """
    One asimov project: its configuration, ledger, directories and services.

    Parameters
    ----------
    root : str
        The project's root directory.
    config : configparser.ConfigParser, optional
        The project's configuration. Read from ``root`` if not given.
    ledger : Ledger, optional
        The project's ledger. Opened from the configuration on first use if
        not given.
    project : asimov.project.Project, optional
        The ``Project`` this context belongs to, if it was made by one.
    """

    def __init__(self, root, config=None, ledger=None, project=None):
        self._root = os.path.abspath(root)
        self.config = config if config is not None else read_config(self._root)
        if not self.config.has_section("project"):
            self.config.add_section("project")
        self.config.set("project", "root", self.root)
        self.project = project
        self._ledger = ledger
        self._storage = None
        self._scheduler = None

    @classmethod
    def from_directory(cls, path=None):
        """
        The context for the project in ``path`` (default: the current directory).

        Raises
        ------
        NoProjectError
            If there is no project there.
        """
        path = os.path.abspath(os.curdir if path is None else path)
        if not os.path.exists(os.path.join(path, ".asimov", f"{_PACKAGE}.conf")):
            raise NoProjectError(f"There is no asimov project in {path}")
        return cls(path)

    @property
    def root(self):
        """The project's root directory, as an absolute path."""
        return self._root

    def path(self, section, option, fallback):
        """A configured directory, resolved against the project root."""
        value = self.config.get(section, option, fallback=fallback) or fallback
        return value if os.path.isabs(value) else os.path.join(self.root, value)

    @property
    def working_dir(self):
        """Where analyses run."""
        return self.path("general", "rundir_default", "working")

    @property
    def checkouts_dir(self):
        """Where git repositories are cloned."""
        return self.path("general", "git_default", "checkouts")

    @property
    def results_dir(self):
        """The results store."""
        return self.path("storage", "directory", "results")

    @property
    def log_dir(self):
        """Where log files are written."""
        return self.path("logging", "location", "logs")

    @property
    def webdir(self):
        """Where pages and post-processing output are published."""
        return self.path("general", "webroot", "pages")

    @property
    def ledger(self):
        """The project's ledger, opened on first use."""
        if self._ledger is None:
            self._ledger = self._open_ledger()
        return self._ledger

    def reset_ledger(self):
        """Forget the open ledger, so the next use reads it afresh."""
        self._ledger = None

    def _open_ledger(self):
        """
        Open the ledger which this project's own configuration names.

        A project file without a ``[ledger]`` section predates the database
        ledgers, so it is a YAML one.
        """
        project_file = configparser.ConfigParser()
        project_file.read(os.path.join(self.root, ".asimov", f"{_PACKAGE}.conf"))
        engine = project_file.get("ledger", "engine", fallback="yamlfile")
        location = project_file.get("ledger", "location", fallback=None)

        if engine == "yamlfile":
            from asimov.ledger import YAMLLedger

            location = location or os.path.join(".asimov", "ledger.yml")
            if not os.path.isabs(location):
                location = os.path.join(self.root, location)
            return YAMLLedger(location=location)

        from asimov.ledger import DatabaseLedger

        database_url = None
        if location:
            database_url = (
                location
                if "://" in location
                else f"sqlite:///{os.path.join(self.root, location)}"
            )
        return DatabaseLedger(engine=engine, location=database_url)

    @property
    def storage(self):
        """The project's results store."""
        if self._storage is None:
            from asimov.storage import Store

            self._storage = Store(root=self.results_dir)
        return self._storage

    @property
    def scheduler(self):
        """The scheduler this project's jobs are submitted to."""
        if self._scheduler is None:
            from asimov.scheduler_utils import get_configured_scheduler

            self._scheduler = get_configured_scheduler(self.config)
        return self._scheduler

    @contextlib.contextmanager
    def activate(self):
        """
        Make this the active context in the current thread or task.

        While active, ``asimov.config`` and ``get_ledger()`` refer to this
        project. Contexts nest: leaving the block restores whichever was
        active before.
        """
        token = _active_context.set(self)
        try:
            yield self
        finally:
            _active_context.reset(token)

    @contextlib.contextmanager
    def transaction(self):
        """
        Make the changes to the ledger in the block all happen, or none.

        On leaving the block the ledger is saved and, for a database ledger,
        committed. If the block raises, nothing it wrote is persisted, and
        what the ledger had cached is dropped so the next read comes from
        what is actually stored. Blocks nest by joining the outermost one.

        This does not make the context active; use :meth:`activate` for
        that.
        """
        ledger = self.ledger
        with ledger.transaction():
            yield self
            ledger.save()

    def __repr__(self):
        return f"<{type(self).__name__} {self.root}>"


class AmbientContext(ProjectContext):
    """
    The project in the current working directory, whichever that is now.

    This is what the command line uses, and what code gets when no context
    has been activated. It follows the process-wide configuration, and
    finds its ledger the way ``import asimov`` always has: quietly, and
    leaving it ``None`` if there is no project here.
    """

    def __init__(self, config):
        self.config = config
        self.project = None
        self._ledger = None
        self._ledger_tried = False
        self._storage = None
        self._scheduler = None

    @property
    def root(self):
        return os.getcwd()

    @property
    def ledger(self):
        if self._ledger is None and not self._ledger_tried:
            self._ledger_tried = True
            self._ledger = self._probe_ledger()
        return self._ledger

    def reset_ledger(self):
        self._ledger = None
        self._ledger_tried = False

    def _probe_ledger(self):
        import logging

        log = logging.getLogger(_PACKAGE)
        try:
            engine = self.config.get("ledger", "engine")
            if engine == "yamlfile":
                from asimov.ledger import YAMLLedger

                return YAMLLedger(self.config.get("ledger", "location"))
            if engine == "gitlab":
                log.error("The gitlab interface has been removed from v0.6 of asimov")
                return None
            if engine in {"tinydb", "sqlalchemy", "sqlite", "postgresql", "mysql"}:
                from asimov.ledger import DatabaseLedger

                # A file-backed database is only attached to if it exists:
                # AsimovSQLDatabase will otherwise create one in whatever
                # directory this happens to be probed from. That suits an
                # explicit `asimov init`, not a check for "is there a
                # project here?". Network URLs have no path to check.
                location = self.config.get("ledger", "location", fallback=None)
                if location and "://" not in location and not os.path.exists(location):
                    return None
                return DatabaseLedger(engine=engine)
        except FileNotFoundError:
            return None
        except Exception as e:
            log.debug("Could not initialise ledger at startup: %s", e)
        return None


_ambient = None


def _install_ambient(config):
    """Create the ambient context over the process-wide configuration."""
    global _ambient
    _ambient = AmbientContext(config)
    return _ambient


def get_active_context():
    """The context activated in this thread or task, or ``None``."""
    return _active_context.get()


def current_context():
    """The active context, or the ambient one (the current directory's project)."""
    context = _active_context.get()
    return context if context is not None else _ambient
