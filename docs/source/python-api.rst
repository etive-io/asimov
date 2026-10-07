.. _python-api:

Python API
==========

Overview
--------

In addition to the command-line interface, asimov provides a Python API that allows you to create and manage projects programmatically. This is particularly useful for:

* Creating projects from Python scripts
* Automating project setup and configuration
* Integrating asimov into larger workflows
* Creating analyses programmatically

Creating a New Project
----------------------

You can create a new asimov project directly from Python using the ``Project`` class:

.. code-block:: python

    from asimov.project import Project
    
    # Create a new project
    project = Project(
        name="My Project",
        location="/path/to/project"
    )

This creates the same directory structure and configuration files as the ``asimov init`` command.

Working with Projects
---------------------

The ``Project`` class provides a context manager interface that ensures the project ledger is properly saved after making changes:

.. code-block:: python

    from asimov.project import Project
    
    # Create a new project (see "Loading an Existing Project" below for loading existing projects)
    project = Project("My Project", location="/path/to/project")
    
    # Use the context manager to make changes
    with project:
        # Add a subject (event) to the project
        subject = project.add_subject(name="GW150914")
        
        # Add an analysis to the subject
        from asimov.analysis import GravitationalWaveTransient
        
        production = GravitationalWaveTransient(
            subject=subject,
            name="bilby_production",
            pipeline="bilby",
            status="ready",
            ledger=project.ledger
        )
        
        subject.add_production(production)
        # The ledger will be updated when exiting the context manager
        project.ledger.update_event(subject)
    
    # When the context exits, changes are automatically saved

Loading an Existing Project
----------------------------

You can load an existing asimov project using the ``Project.load()`` class method:

.. code-block:: python

    from asimov.project import Project
    
    # Load an existing project
    project = Project.load("/path/to/existing/project")
    
    # Access events in the project
    events = project.get_event()
    for event in events:
        print(f"Event: {event.name}")
        for production in event.productions:
            print(f"  - {production.name}: {production.status}")

Adding Multiple Subjects
-------------------------

You can add multiple subjects to a project within the same context:

.. code-block:: python

    from asimov.project import Project
    
    project = Project("Multi-Event Project", location="/path/to/project")
    
    with project:
        # Add multiple events
        gw150914 = project.add_subject(name="GW150914")
        gw151012 = project.add_subject(name="GW151012")
        gw151226 = project.add_subject(name="GW151226")

Accessing the Ledger
---------------------

The project's ledger can be accessed through the ``ledger`` property:

.. code-block:: python

    project = Project.load("/path/to/project")
    
    # Access the ledger
    ledger = project.ledger
    
    # Get all events
    all_events = ledger.get_event()
    
    # Get a specific event
    specific_event = ledger.get_event("GW150914")

Complete Example
----------------

Here's a complete example showing how to create a project, add events, and configure analyses:

.. code-block:: python

    from asimov.project import Project
    from asimov.analysis import GravitationalWaveTransient
    
    # Create a new project
    project = Project(
        name="GWTC-1 Reanalysis",
        location="/data/projects/gwtc1"
    )
    
    with project:
        # Add events from GWTC-1
        for event_name in ["GW150914", "GW151012", "GW151226"]:
            subject = project.add_subject(name=event_name)
            
            # Add a Bilby analysis
            bilby_prod = GravitationalWaveTransient(
                subject=subject,
                name=f"{event_name}_bilby",
                pipeline="bilby",
                status="ready",
                ledger=project.ledger
            )
            subject.add_production(bilby_prod)
            project.ledger.update_event(subject)
    
    # After exiting the context, all changes are saved
    print(f"Project created with {len(project.get_event())} events")

Context Manager Benefits
-------------------------

The context manager approach ensures that:

1. **Transactional Updates**: Changes to the ledger are grouped together and saved atomically
2. **Automatic Saving**: You don't need to manually call ``save()`` on the ledger
3. **Clean Resource Management**: The project directory is properly managed during operations
4. **Error Handling**: If an error occurs, nothing written in the block is persisted, preventing partial updates

This holds for both ledger backends. With the default database ledger the block is a single
database transaction, committed when the block ends and rolled back if it raises. After a
rollback the project's ledger is reloaded from what is stored the next time it is used, so
``project.get_event()`` no longer shows the failed block's changes. Nested ``with project:``
blocks join the outermost one, which is the one that commits.

Project Contexts
----------------

Each project has a :class:`~asimov.context.ProjectContext`, available as ``project.context``,
which holds its configuration, ledger, directories (``working_dir``, ``checkouts_dir``,
``results_dir``, ``log_dir`` and ``webdir``), results store and scheduler. Entering ``with
project:`` makes it the *active* context for the current thread or task, so ``asimov.config``
and the ledger returned by ``get_ledger()`` refer to that project.

A context can be used without a ``Project``, and without changing directory:

.. code-block:: python

    from asimov.context import ProjectContext

    ctx = ProjectContext.from_directory("/projects/o4-events")
    with ctx.activate(), ctx.transaction():
        ctx.ledger.add_event(event)

Contexts are tracked with :mod:`contextvars`, so threads and asyncio tasks each have their own
active context. ``from asimov import config`` and ``from asimov import current_ledger`` still
work: ``config`` follows the active context, and ``current_ledger`` is deprecated in favour of
``asimov.context.current_context().ledger``. With no context active, they refer to the project
in the current directory, as before.

Nothing in a ``with project:`` block depends on the current working directory, and entering
one does not change it. The paths asimov stores, such as an event's working directory or
repository, are relative to the project and are made absolute against the active context's root
with :func:`asimov.context.resolve_path`, so several projects can be served by one process.

The ``asimov init`` command and :func:`asimov.cli.project.make_project` still move into the
project they create and update the process-wide configuration, since the commands which follow
expect it. :func:`asimov.cli.project.create_project`, which ``Project(...)`` uses, does neither.
A ledger which comes from a context reads its events in that project, whether or not the context
is active.

.. note::

   The testing pipelines (``asimov.pipelines.testing``) still change into a run directory while
   they submit, so they are not safe to run for two projects at once in one process.

API Reference
-------------

Project Class
~~~~~~~~~~~~~

.. autoclass:: asimov.project.Project
   :members:
   :undoc-members:
   :show-inheritance:

Project Context Class
~~~~~~~~~~~~~~~~~~~~~

.. autoclass:: asimov.context.ProjectContext
   :members:
   :show-inheritance:
