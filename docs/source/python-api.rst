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
4. **Error Handling**: If an error occurs, the ledger is not saved, preventing partial updates

API Reference
-------------

Project Class
~~~~~~~~~~~~~

.. autoclass:: asimov.project.Project
   :members:
   :undoc-members:
   :show-inheritance:
