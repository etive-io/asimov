"""
Project management and Python API interface.

This module provides a Python API for creating and managing asimov projects.
"""

import contextlib
import os

try:
    import ConfigParser as configparser
except ImportError:
    import configparser

from asimov import logger, LOGGER_LEVEL
from asimov.context import ProjectContext, get_active_context
from asimov.event import Event
from asimov.utils import set_directory
from asimov.cli.project import make_project

logger = logger.getChild("project")
logger.setLevel(LOGGER_LEVEL)


def get_active_project():
    """
    Return the innermost ``Project`` currently active inside a
    ``with project:`` block.

    Tracked per thread and task, through the active ``ProjectContext``, so
    exiting an inner ``with project_b:`` block nested in an outer ``with
    project_a:`` block restores ``project_a``.

    Returns
    -------
    Project or None
        The active project, or ``None`` if no project context is open.
    """
    context = get_active_context()
    return None if context is None else context.project


class Project:
    """
    A class representing an asimov project.
    
    This class provides a Python API for creating and managing asimov projects,
    including creating new projects, adding subjects/events, and managing analyses.
    
    Examples
    --------
    Create a new project::
    
        from asimov.project import Project
        
        project = Project("My Project", "/path/to/project")
        
        with project:
            subject = project.add_subject(name="GW150914", ...)
            subject.add_production(name="prod_1", pipeline="bilby", ...)
    
    Load an existing project::
    
        project = Project.load("/path/to/project")
        
        with project:
            # Make changes
            pass
    """
    
    def __init__(self, name, location=None, working="working", checkouts="checkouts", 
                 results="results", logs="logs", user=None):
        """
        Initialize a new asimov project.
        
        Parameters
        ----------
        name : str
            The name of the project.
        location : str, optional
            The root directory for the project. If None, uses the current directory.
        working : str, optional
            The location to store working directories. Default is "working".
        checkouts : str, optional
            The location to store cloned git repositories. Default is "checkouts".
        results : str, optional
            The location where the results store should be created. Default is "results".
        logs : str, optional
            The location to store log files. Default is "logs".
        user : str, optional
            The user account to be used for accounting purposes. 
            Defaults to the current user if not set.
        """
        self.name = name
        self.location = location if location else os.getcwd()
        self.working = working
        self.checkouts = checkouts
        self.results = results
        self.logs = logs
        self.user = user
        
        self._context = None
        self._entered = []
        
        # Prevent accidental re-initialization of an existing project directory.
        # If the target location already exists and contains a project, refuse to
        # create a new project there, as this may overwrite an existing project.
        config_path = os.path.join(self.location, ".asimov", "asimov.conf")
        if os.path.exists(config_path):
            raise RuntimeError(
                f"Project directory '{self.location}' already contains an asimov project. "
                "If you meant to open an existing project, use Project.load(...)."
            )
        
        # Initialize the project structure
        self._initialize_project()
    
    def _initialize_project(self):
        """
        Initialize the project structure by calling the make_project function.
        """
        # Store current directory
        original_dir = os.getcwd()
        
        try:
            # Create the project
            make_project(
                name=self.name,
                root=self.location,
                working=self.working,
                checkouts=self.checkouts,
                results=self.results,
                logs=self.logs,
                user=self.user
            )
            
            logger.info(f"Created new project '{self.name}' at {self.location}")
            
        finally:
            # Return to original directory
            os.chdir(original_dir)
    
    @classmethod
    def load(cls, location):
        """
        Load an existing project from a directory.
        
        Parameters
        ----------
        location : str
            The root directory of the existing project.
            
        Returns
        -------
        Project
            A Project instance loaded from the specified location.
            
        Raises
        ------
        FileNotFoundError
            If the project directory or configuration file does not exist.
        """
        config_path = os.path.join(location, ".asimov", "asimov.conf")
        if not os.path.exists(config_path):
            raise FileNotFoundError(
                f"No project found at {location}. "
                f"Missing configuration file at {config_path}"
            )
        
        # Read the project configuration
        config = configparser.ConfigParser()
        config.read(config_path)
        
        # Create a Project instance without initializing
        project = cls.__new__(cls)
        
        try:
            project.name = config.get("project", "name")
            project.location = location
            project.working = config.get("general", "rundir_default")
            project.checkouts = config.get("general", "git_default")
            project.results = config.get("storage", "directory")
            project.logs = config.get("logging", "location")
            project.user = config.get("condor", "user")
        except (configparser.NoSectionError, configparser.NoOptionError) as e:
            raise ValueError(
                f"Project configuration at {config_path} is incomplete or malformed. "
                f"Missing configuration: {e}"
            )
        
        project._context = None
        project._entered = []
        
        logger.info(f"Loaded existing project '{project.name}' from {location}")
        
        return project
    
    @property
    def context(self):
        """
        The ``ProjectContext`` for this project.

        Holds the project's configuration, ledger and directories. Made on
        first use, after the project exists on disk.
        """
        if self._context is None:
            self._context = ProjectContext(self.location, project=self)
        return self._context

    @property
    def _in_context(self):
        return bool(self._entered)

    @property
    def ledger(self):
        """
        Get the project ledger.

        Returns
        -------
        Ledger
            The project's ledger instance.
        """
        return self.context.ledger

    def __enter__(self):
        """
        Enter the context manager, enabling transactional updates.

        Makes this project's context the active one, and opens a transaction
        on its ledger: what the block writes is saved when it ends, or not
        at all if it raises.

        Returns
        -------
        Project
            The project instance.
        """
        context = self.context
        stack = contextlib.ExitStack()
        try:
            stack.enter_context(context.activate())
            # Much of asimov still finds files relative to the working
            # directory (see issue #180), so until that is gone a project
            # block works from the project's directory.
            stack.enter_context(set_directory(self.location))
            stack.enter_context(context.transaction())

            # Ensure pipelines section exists in ledger data
            # This is needed for production.to_dict() to work correctly
            if "pipelines" not in context.ledger.data:
                context.ledger.data["pipelines"] = {}
        except BaseException:
            stack.close()
            raise

        self._entered.append(stack)
        logger.debug(f"Entered context for project '{self.name}'")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Exit the context manager, saving changes to the ledger.

        If an exception was raised in the block, nothing written in it is
        persisted, and the ledger is reloaded from what is stored on the
        next use.

        Parameters
        ----------
        exc_type : type
            The exception type, if an exception was raised.
        exc_val : Exception
            The exception value, if an exception was raised.
        exc_tb : traceback
            The exception traceback, if an exception was raised.
        """
        stack = self._entered.pop()
        try:
            suppressed = stack.__exit__(exc_type, exc_val, exc_tb)
        finally:
            if not self._entered:
                # Drop the ledger so the next access reads what is stored,
                # which after a rollback is not what it holds in memory.
                self.context.reset_ledger()
                logger.debug(f"Exited context for project '{self.name}'")
        return suppressed

    def add_subject(self, name, **kwargs):
        """
        Add a new subject (event) to the project.
        
        Parameters
        ----------
        name : str
            The name of the subject/event.
        **kwargs
            Additional keyword arguments to pass to the Event constructor.
            
        Returns
        -------
        Event
            The created event/subject.
            
        Raises
        ------
        RuntimeError
            If called outside of a context manager.
        """
        if not self._in_context:
            raise RuntimeError(
                "add_subject must be called within a context manager. "
                "Use 'with project:' to enter a transactional context."
            )
        
        # Create the event
        ledger = self.ledger
        event = Event(name=name, ledger=ledger, **kwargs)
        
        # Add to ledger without saving (save happens on context exit)
        # Temporarily disable auto-save during add_event to avoid redundant I/O
        original_save = ledger.save
        try:
            # Replace save with a no-op during add_event
            ledger.save = lambda: None
            ledger.add_event(event)
        finally:
            # Restore the original save method
            ledger.save = original_save
        
        logger.info(f"Added subject '{name}' to project '{self.name}'")
        
        return event
    
    def add_event(self, name, **kwargs):
        """
        Add a new event to the project.
        
        This is an alias for add_subject for backward compatibility.
        
        Parameters
        ----------
        name : str
            The name of the event.
        **kwargs
            Additional keyword arguments to pass to the Event constructor.
            
        Returns
        -------
        Event
            The created event.
        """
        return self.add_subject(name=name, **kwargs)
    
    def get_event(self, name=None):
        """
        Get one or all events from the project.
        
        Parameters
        ----------
        name : str, optional
            The name of the event to retrieve. If None, returns all events.
            
        Returns
        -------
        Event or list of Event
            The requested event(s).
        """
        return self.ledger.get_event(event=name)
    
    def __repr__(self):
        """
        Return a string representation of the project.
        
        Returns
        -------
        str
            A string representation of the project.
        """
        return f"<Project '{self.name}' at {self.location}>"
