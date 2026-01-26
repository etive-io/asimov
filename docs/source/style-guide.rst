.. _style-guide:

================================
Asimov Documentation Style Guide
================================

:Version: 1.0
:Last Updated: 2026-01-26
:Status: Official

Introduction
============

Purpose
-------

This style guide ensures consistency, clarity, and accessibility across all asimov documentation. Following these guidelines helps:

- **Users** find information quickly and understand it easily
- **Contributors** write documentation that matches existing content
- **Maintainers** review and approve documentation efficiently

Scope
-----

This guide applies to all documentation in:

- User guides (``docs/source/user-guide/``)
- Tutorials (``docs/source/tutorials/``)
- Reference documentation (``docs/source/api/``, ``docs/source/``)
- README files
- Docstrings in Python code

Principles
----------

1. **Clarity over cleverness** - Simple, direct language wins
2. **Consistency** - Follow established patterns
3. **Accessibility** - Make content understandable to diverse audiences
4. **Accuracy** - Technical correctness is essential
5. **Completeness** - Provide enough context to be useful

Voice and Tone
===============

General Guidelines
------------------

**Voice** is the consistent personality of the documentation (formal, friendly, technical).
**Tone** adapts to the context (instructional, informative, cautionary).

Voice by Document Type
-----------------------

Tutorials and Getting Started Guides
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Voice:** Friendly, encouraging, instructional

**Person:** Second person ("you")

**Tense:** Present tense

**Style:** Conversational but clear

✅ **Good Examples:**

.. code-block:: text

   You can create a new project by running `asimov init`.

   Let's add an event to your project. You'll need to provide a name for the event.

   Great! Your analysis is now configured. Next, we'll submit it to the cluster.

❌ **Bad Examples:**

.. code-block:: text

   One can create a new project by running `asimov init`.  ← Too formal

   The user should provide a name for the event.  ← Third person

   An analysis has been configured by the previous steps.  ← Passive voice

User Guides
~~~~~~~~~~~

**Voice:** Professional, instructional, clear

**Person:** Second person ("you")

**Tense:** Present tense

**Style:** Direct and actionable

✅ **Good Examples:**

.. code-block:: text

   To add an event, run the following command:

   Configure your project by editing the `.asimov/asimov.conf` file.

   You must specify the interferometers before building the analysis.

❌ **Bad Examples:**

.. code-block:: text

   We add an event by running...  ← First person plural

   One might want to configure the project...  ← Uncertain, vague

   The project can be configured.  ← Passive, no clear actor

Reference Documentation (API, Configuration)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Voice:** Formal, precise, comprehensive

**Person:** Third person or passive voice

**Tense:** Present tense

**Style:** Technical and concise

✅ **Good Examples:**

.. code-block:: text

   The ledger stores configuration data in a hierarchical structure.

   This parameter accepts a string or list of strings.

   Returns a list of Event objects matching the query.

❌ **Bad Examples:**

.. code-block:: text

   You store configuration data in the ledger.  ← Too informal for reference

   We return a list of Event objects.  ← First person

   This is a really important parameter!  ← Overly casual

Docstrings (Python API)
~~~~~~~~~~~~~~~~~~~~~~~~

**Voice:** Technical, precise, imperative

**Person:** Imperative mood (commands) or third person

**Tense:** Present tense

**Style:** Concise and structured

✅ **Good Example:**

.. code-block:: python

   def create_event(name: str, interferometers: List[str]) -> Event:
       """
       Create a new Event object.

       Parameters
       ----------
       name : str
           The name of the event (e.g., "GW150914_095045")
       interferometers : List[str]
           List of interferometer codes (e.g., ["H1", "L1", "V1"])

       Returns
       -------
       Event
           The newly created event object

       Raises
       ------
       ValueError
           If the name is empty or interferometers list is empty

       Examples
       --------
       >>> event = create_event("GW150914_095045", ["H1", "L1"])
       >>> event.name
       'GW150914_095045'
       """

❌ **Bad Examples:**

.. code-block:: python

   def create_event(name, interferometers):
       """
       This function creates an event.  ← Vague, missing details
       """

   def create_event(name, interferometers):
       """
       You can use this to create events in your project.  ← Too informal
       The name should be a string and interferometers should be a list.  ← Unclear types
       """

Tone Guidelines
---------------

Instructional Tone (Tutorials, How-To Guides)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- Use encouraging language
- Acknowledge effort ("Great!", "Well done!")
- Guide the reader step-by-step
- Explain the "why" not just the "how"

✅ **Good:**

.. code-block:: text

   Now that you've created your project, let's add an event. This will tell asimov
   what data to analyze.

❌ **Bad:**

.. code-block:: text

   Execute the event creation command. This is required.

Informative Tone (Explanations, Concepts)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- Be clear and objective
- Focus on understanding
- Use examples to illustrate concepts
- Build from simple to complex

✅ **Good:**

.. code-block:: text

   The ledger maintains a hierarchical structure where settings cascade from project
   to event to analysis. This allows you to set defaults once and override them only
   when needed.

❌ **Bad:**

.. code-block:: text

   The ledger is hierarchical. Settings cascade.

Cautionary Tone (Warnings, Important Notes)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- Be specific about risks
- Explain consequences
- Provide alternatives when possible
- Don't overuse warnings (they lose impact)

✅ **Good:**

.. warning::
   Running ``asimov manage cancel`` will permanently stop the job and remove it
   from the queue. This action cannot be undone. To temporarily pause a job,
   use ``asimov manage stop`` instead.

❌ **Bad:**

.. warning::
   Be careful with this command!

Terminology Standards
======================

Preferred Terms
---------------

Use these terms consistently throughout documentation:

.. list-table::
   :header-rows: 1
   :widths: 20 20 40

   * - ✅ Preferred
     - ❌ Avoid
     - Context
   * - Analysis
     - Production
     - Current term (v0.4.0+)
   * - SimpleAnalysis
     - Production
     - When referring to analysis type
   * - Event
     - Subject (outside specific context)
     - General usage
   * - Pipeline
     - Analysis pipeline
     - Unless disambiguation needed
   * - Ledger
     - Database, config file
     - Asimov's central data store
   * - Repository
     - Repo (in formal docs)
     - Event repository
   * - Store
     - Results store
     - Read-only results archive
   * - HTCondor
     - Condor
     - Official name
   * - asimov
     - Asimov, ASIMOV
     - Command and package name
   * - Parameter estimation
     - PE (on first use)
     - Define acronym first

Deprecated Terms
----------------

When referring to old terminology, always mark as deprecated:

✅ **Good:**

.. code-block:: text

   SimpleAnalysis (formerly called "Production" in versions prior to 0.4.0)

   The ``productions:`` key in the ledger (deprecated; use ``analyses:`` in new code)

❌ **Bad:**

.. code-block:: text

   Production (also known as SimpleAnalysis)  ← Makes old term seem current

Acronyms and Abbreviations
---------------------------

First Use Rule
~~~~~~~~~~~~~~

**Always spell out acronyms on first use** in each document, with the acronym in parentheses.

✅ **Good:**

.. code-block:: text

   The Power Spectral Density (PSD) is estimated using Bayeswave. The PSD is then
   used in parameter estimation.

   Asimov submits jobs to High Throughput Computing (HTC) clusters using HTCondor.

❌ **Bad:**

.. code-block:: text

   The PSD is estimated using Bayeswave.  ← Undefined acronym

   The Power Spectral Density is estimated... Later, the PSD is used...  ← Inconsistent

Common Acronyms
~~~~~~~~~~~~~~~

These should still be defined on first use:

.. list-table::
   :header-rows: 1
   :widths: 15 40 30

   * - Acronym
     - Full Term
     - Notes
   * - API
     - Application Programming Interface
     -
   * - CBC
     - Compact Binary Coalescence
     - GW-specific
   * - CLI
     - Command Line Interface
     -
   * - DAG
     - Directed Acyclic Graph
     - HTCondor concept
   * - GW
     - Gravitational Wave
     - Domain-specific
   * - HTC
     - High Throughput Computing
     -
   * - IFO
     - Interferometer
     - GW-specific
   * - INI
     - Initialization file
     - Config file format
   * - PE
     - Parameter Estimation
     - GW analysis type
   * - PSD
     - Power Spectral Density
     - Signal processing
   * - ROQ
     - Reduced Order Quadrature
     - Advanced technique
   * - YAML
     - YAML Ain't Markup Language
     - File format

Domain-Specific Terms
----------------------

Gravitational Wave Terms
~~~~~~~~~~~~~~~~~~~~~~~~

When using GW-specific terminology, consider your audience:

**In GW-specific documentation** (ligo-cookbook, GW tutorials):

- Use GW terms naturally
- Define specialized terms once
- Assume basic GW knowledge

**In general documentation** (user guides, core concepts):

- Minimize GW-specific terms
- Define ALL GW terms when used
- Provide generic alternatives

✅ **Good (general docs):**

.. code-block:: text

   Events represent occurrences that need analysis. For gravitational wave (GW)
   analysis, an event might be a compact binary coalescence (CBC) detection like
   GW150914.

✅ **Good (GW-specific docs):**

.. code-block:: text

   For CBC events, you'll need to specify the calibration envelopes and PSD
   estimates for each interferometer (IFO).

❌ **Bad (general docs):**

.. code-block:: text

   Add your CBC event to the ledger.  ← Assumes GW context

Capitalization
--------------

.. list-table::
   :header-rows: 1
   :widths: 20 25 40

   * - Term
     - Capitalization
     - Example
   * - asimov
     - lowercase
     - ``asimov init``
   * - Event (the class)
     - Capitalized
     - "Create an Event object"
   * - event (the concept)
     - lowercase
     - "add an event to the ledger"
   * - Ledger (asimov's)
     - Capitalized
     - "The Ledger stores configuration"
   * - ledger (generic)
     - lowercase
     - "a ledger of transactions"
   * - Pipeline (the class)
     - Capitalized
     - "The Pipeline interface"
   * - pipeline (instance)
     - lowercase
     - "the bilby pipeline"

Document Structure
==================

File Organization
-----------------

Headers
~~~~~~~

Use underline-style headers in reStructuredText:

.. code-block:: rst

   ====================
   Top Level Heading
   ====================

   Section Heading
   ===============

   Subsection Heading
   ------------------

   Subsubsection Heading
   ~~~~~~~~~~~~~~~~~~~~~

   Paragraph Heading
   ^^^^^^^^^^^^^^^^^

Header Hierarchy
~~~~~~~~~~~~~~~~

✅ **Good:**

.. code-block:: rst

   Getting Started
   ===============

   Creating a Project
   ------------------

   Running asimov init
   ~~~~~~~~~~~~~~~~~~~

❌ **Bad:**

.. code-block:: rst

   Getting Started
   ===============

   Running asimov init  ← Skipped a level
   ~~~~~~~~~~~~~~~~~~~

Document Template
-----------------

Every new documentation page should follow this structure:

.. code-block:: rst

   .. _reference-label:

   ===================
   Document Title
   ===================

   Brief introduction (1-2 paragraphs) explaining what this document covers and who it's for.

   .. contents:: Table of Contents
      :depth: 2
      :local:

   Prerequisites
   -------------

   List any prerequisites:

   - Required knowledge
   - Required setup
   - Related documents to read first

   Main Content Section
   --------------------

   Organized sections with clear headings.

   Examples
   --------

   Practical examples demonstrating concepts.

   Troubleshooting
   ---------------

   Common issues and solutions (if applicable).

   See Also
   --------

   - :ref:`related-document-1`
   - :ref:`related-document-2`

Section Order
-------------

Organize content in this order:

1. **Introduction** - What this is about
2. **Prerequisites** - What you need to know/have
3. **Concepts** - Theory and background (if needed)
4. **How-To** - Step-by-step instructions
5. **Examples** - Concrete demonstrations
6. **Reference** - Detailed specifications
7. **Troubleshooting** - Common problems
8. **See Also** - Related documentation

Formatting Conventions
======================

Inline Code
-----------

Use double backticks for inline code:

- Command names: ``asimov``
- File names: ``ledger.yml``
- Function names: ``create_event()``
- Variable names: ``event_name``
- Configuration keys: ``interferometers``
- Short code snippets: ``status = "ready"``

✅ **Good:**

.. code-block:: text

   Run ``asimov init`` to create a project.

   Set the ``status`` field to ``ready`` in your configuration.

   The ``create_event()`` function returns an Event object.

❌ **Bad:**

.. code-block:: text

   Run asimov init to create a project.  ← No code formatting

   Set the status field to "ready".  ← Quotes without code formatting

File Paths
----------

Use inline code with absolute or relative paths clearly indicated:

✅ **Good:**

.. code-block:: text

   The ledger is located at ``.asimov/ledger.yml`` (relative to project root).

   Edit the configuration at ``/home/user/project/.asimov/asimov.conf``.

❌ **Bad:**

.. code-block:: text

   The ledger is at .asimov/ledger.yml  ← No code formatting

Emphasis
--------

- **Bold** for UI elements, important terms, strong emphasis
- *Italic* for emphasis, introducing new terms
- ``code`` for technical terms, commands, code

✅ **Good:**

.. code-block:: text

   Click the **Submit** button to start the analysis.

   The *ledger* is asimov's central database that stores all project information.

   Use the ``--force`` flag to override this check.

❌ **Bad:**

.. code-block:: text

   Click the "Submit" button.  ← Use bold for UI

   The ledger is asimov's central database.  ← Introduce new term with italic

   Use the -force flag.  ← Use code for flags

Lists
-----

Unordered Lists
~~~~~~~~~~~~~~~

Use ``-`` or ``*`` for consistency (pick one):

✅ **Good:**

.. code-block:: rst

   - First item
   - Second item

     - Nested item
     - Another nested item

   - Third item

❌ **Bad:**

.. code-block:: rst

   * First item
   + Second item
   - Third item  ← Inconsistent bullets

Ordered Lists
~~~~~~~~~~~~~

Use Arabic numerals with periods:

✅ **Good:**

.. code-block:: rst

   1. First step
   2. Second step
   3. Third step

Or use ``#.`` for auto-numbering:

.. code-block:: rst

   #. First step
   #. Second step
   #. Third step

Tables
------

Use list-table directive for complex tables:

.. code-block:: rst

   .. list-table:: Feature Comparison
      :header-rows: 1
      :widths: 20 25 25 30

      * - Feature
        - SimpleAnalysis
        - SubjectAnalysis
        - ProjectAnalysis
      * - Scope
        - Single event
        - Single event
        - Multiple events
      * - Input
        - Event data
        - Analysis results
        - All project data
      * - Use case
        - PE run
        - Compare waveforms
        - Population study

For simple tables, use grid or simple table syntax:

.. code-block:: rst

   =======  =================
   Column1  Column2
   =======  =================
   Value1   Value2
   Value3   Value4
   =======  =================

Horizontal Rules
----------------

Use at least 4 dashes to separate major sections:

.. code-block:: rst

   ----

Code Examples
=============

General Principles
------------------

1. **Complete** - Examples should be runnable
2. **Realistic** - Use realistic but simple data
3. **Explained** - Always explain what the code does
4. **Tested** - Verify examples work before documenting

Bash/Shell Commands
-------------------

Format
~~~~~~

.. code-block:: rst

   .. code-block:: bash

      $ command argument
      output line 1
      output line 2

Guidelines
~~~~~~~~~~

✅ **Good:**

.. code-block:: bash

   $ asimov init "My Project"
   ● New project created successfully!

   $ asimov apply -f event.yaml
   ● Successfully applied GW150914_095045

**Requirements:**

- Include ``$`` prompt for commands
- Show expected output
- Use realistic examples
- One command per block (unless piped)

❌ **Bad:**

.. code-block:: bash

   asimov init "My Project"  ← No prompt
   asimov apply -f event.yaml  ← No output shown

Multi-line Commands
~~~~~~~~~~~~~~~~~~~

Use ``\`` for line continuation:

✅ **Good:**

.. code-block:: bash

   $ asimov production create GW150914 bilby \
       --approximant IMRPhenomXPHM \
       --comment "Higher mode analysis" \
       --needs Prod0

❌ **Bad:**

.. code-block:: bash

   $ asimov production create GW150914 bilby --approximant IMRPhenomXPHM --comment "Higher mode analysis" --needs Prod0

Python Code
-----------

Format
~~~~~~

.. code-block:: rst

   .. code-block:: python

      from asimov import Project

      project = Project.load()
      for event in project.events:
          print(event.name)

Guidelines
~~~~~~~~~~

✅ **Good:**

.. code-block:: python

   from asimov.project import Project
   from asimov.event import Event

   # Load the project
   project = Project.load()

   # Create a new event
   event = Event(
       name="GW150914_095045",
       interferometers=["H1", "L1"]
   )

   # Add event to project
   project.add_event(event)

**Requirements:**

- Include necessary imports
- Add comments explaining steps
- Use realistic variable names
- Follow PEP 8 style

❌ **Bad:**

.. code-block:: python

   p = Project.load()  ← Unclear variable name
   e = Event("GW150914_095045", ["H1", "L1"])  ← No explanation, unclear constructor
   p.add_event(e)

YAML Examples
-------------

Format
~~~~~~

.. code-block:: rst

   .. code-block:: yaml

      key: value
      nested:
        key: value

Guidelines
~~~~~~~~~~

✅ **Good:**

.. code-block:: yaml

   kind: analysis
   name: Prod0
   pipeline: bilby
   waveform:
     approximant: IMRPhenomXPHM
   comment: Parameter estimation with higher modes
   needs:
     - PSD_Generation

**Requirements:**

- Proper indentation (2 spaces)
- Include relevant context
- Show complete valid YAML
- Explain non-obvious keys

❌ **Bad:**

.. code-block:: yaml

   kind: analysis
   name: Prod0
   ...  ← Incomplete example

Interactive Examples
--------------------

For Python REPL examples, use ``>>>`` and ``...`` prompts:

.. code-block:: python

   >>> from asimov.project import Project
   >>> project = Project.load()
   >>> project.name
   'My Project'
   >>> for event in project.events:
   ...     print(event.name)
   ...
   GW150914_095045
   GW151012_095443

Syntax Highlighting
-------------------

Always specify the language for code blocks:

**Supported languages:**

- ``bash`` / ``shell`` / ``console`` - Shell commands
- ``python`` - Python code
- ``yaml`` - YAML configuration
- ``json`` - JSON data
- ``ini`` - INI configuration
- ``rst`` - reStructuredText
- ``text`` - Plain text

Admonitions
===========

Admonitions are special callout boxes. Use them strategically - too many reduces their impact.

Types and Usage
---------------

.. note::

   **Use for:** Helpful information, tips, context

   You can also use the ``olivaw`` command as an alias for ``asimov``. Both commands
   are identical.

.. warning::

   **Use for:** Potential problems, data loss risks, irreversible actions

   Running ``asimov manage cancel`` will permanently remove the job from the queue.
   This action cannot be undone.

.. important::

   **Use for:** Critical information users must know

   All analysis configurations must be committed to git before submission.
   Uncommitted changes will not be included in the analysis.

.. tip::

   **Use for:** Best practices, efficiency suggestions

   Use ``asimov start`` to automate monitoring instead of running ``asimov monitor``
   manually every few minutes.

.. danger::

   **Use for:** Severe consequences, security issues

   Use sparingly - only for serious risks.

   Never commit credentials or API tokens to git. Use environment variables or
   a credential manager instead.

.. deprecated:: 0.4.0

   **Use for:** Deprecated features

   The ``asimov production`` command is deprecated. Use ``asimov analysis`` instead.

.. versionadded:: 0.7.0

   **Use for:** New features

   Support for MongoDB ledger backend.

Admonition Guidelines
---------------------

**Best Practices:**

- Keep admonitions concise (2-4 sentences)
- Use one admonition type per callout
- Don't nest admonitions
- Place admonitions close to related content
- Don't overuse - max 2-3 per page

Links and References
====================

Internal Cross-References
--------------------------

Use labels and ``:ref:`` for internal links:

.. code-block:: rst

   .. _my-section-label:

   Section Title
   =============

   Content here.

   Later in the document:
   See :ref:`my-section-label` for details.

✅ **Good:**

.. code-block:: rst

   For more information, see the :ref:`getting-started` guide.

   The :ref:`analysis-guide` explains how to configure analyses.

**Benefits:**

- Works across file renames
- Shows correct section title
- Validates at build time

External Links
--------------

Inline Links
~~~~~~~~~~~~

.. code-block:: rst

   See the `HTCondor documentation <https://htcondor.readthedocs.io/>`_ for details.

Named Links
~~~~~~~~~~~

For links used multiple times:

.. code-block:: rst

   See the `HTCondor documentation`_ for more information.

   .. _HTCondor documentation: https://htcondor.readthedocs.io/

API References
--------------

Use Sphinx autodoc roles for API references:

.. code-block:: rst

   See :class:`asimov.event.Event` for the Event class API.

   The :func:`asimov.project.Project.load` method loads a project.

   Use the :meth:`Event.add_analysis` method to add analyses.

File References
---------------

For files in the repository:

✅ **Good:**

.. code-block:: text

   See the example configuration in ``examples/config.yaml``.

   The default template is in ``asimov/templates/bilby.ini``.

**Use relative paths from documentation root.**

Language and Grammar
====================

General Writing Guidelines
---------------------------

Active vs Passive Voice
~~~~~~~~~~~~~~~~~~~~~~~

**Prefer active voice** in tutorials and user guides:

✅ **Active (Good):**

.. code-block:: text

   Run the command to create a project.
   Asimov submits the job to HTCondor.

❌ **Passive (Avoid):**

.. code-block:: text

   The command should be run to create a project.
   The job is submitted to HTCondor by asimov.

**Passive voice is acceptable** in reference documentation:

✅ **Passive (Acceptable):**

.. code-block:: text

   Configuration files are generated from templates.
   Results are stored in the read-only archive.

Present Tense
~~~~~~~~~~~~~

Use present tense for current state and actions:

✅ **Good:**

.. code-block:: text

   Asimov creates a new directory for the project.
   The ledger stores configuration data.

❌ **Bad:**

.. code-block:: text

   Asimov will create a new directory.  ← Future tense
   The ledger stored configuration data.  ← Past tense

Conciseness
~~~~~~~~~~~

Be concise but complete:

✅ **Good:**

.. code-block:: text

   To add an event, run ``asimov event create --name EVENT_NAME``.

❌ **Wordy:**

.. code-block:: text

   If you would like to add an event to your project, you can do this by running
   the ``asimov event create`` command with the ``--name`` flag followed by the name
   you want to give to your event.

❌ **Too terse:**

.. code-block:: text

   Add event: ``asimov event create --name EVENT_NAME``.  ← Missing context

Grammar and Punctuation
------------------------

Oxford Comma
~~~~~~~~~~~~

✅ **Use the Oxford comma:**

.. code-block:: text

   Asimov supports bilby, bayeswave, and RIFT.

❌ **Don't omit it:**

.. code-block:: text

   Asimov supports bilby, bayeswave and RIFT.

Sentence Structure
~~~~~~~~~~~~~~~~~~

- Start with the subject when possible
- Keep sentences under 25 words when possible
- Break complex ideas into multiple sentences
- Use lists for multiple items

✅ **Good:**

.. code-block:: text

   The ledger stores three types of data: project defaults, event metadata, and
   analysis specifications. Each type serves a specific purpose in the workflow.

❌ **Bad:**

.. code-block:: text

   The ledger stores project defaults, event metadata, and analysis specifications,
   each of which serves a specific purpose in the workflow, and these are organized
   hierarchically.  ← Too long, too complex

Contractions
~~~~~~~~~~~~

**Avoid contractions** in formal documentation:

✅ **Good:**

.. code-block:: text

   You cannot run the analysis without specifying interferometers.

❌ **Bad:**

.. code-block:: text

   You can't run the analysis without specifying interferometers.

**Exception:** Conversational tutorials may use contractions sparingly for a friendlier tone.

Accessibility
=============

Inclusive Language
------------------

Avoid Idioms and Colloquialisms
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

❌ **Avoid:**

.. code-block:: text

   This is a piece of cake.
   We'll get the ball rolling.
   That's a whole other kettle of fish.

✅ **Use instead:**

.. code-block:: text

   This is straightforward.
   Let's begin.
   That's a separate issue.

Avoid Cultural References
~~~~~~~~~~~~~~~~~~~~~~~~~~

❌ **Avoid:**

.. code-block:: text

   This is like comparing apples and oranges.

✅ **Use instead:**

.. code-block:: text

   These are not directly comparable.

Use Gender-Neutral Language
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

✅ **Good:**

.. code-block:: text

   The user should configure their environment.
   They can specify custom settings.

❌ **Bad:**

.. code-block:: text

   The user should configure his environment.
   He can specify custom settings.

Alternative Text for Images
----------------------------

Always provide alt text:

.. code-block:: rst

   .. figure:: images/workflow-diagram.png
      :alt: Asimov workflow diagram showing the progression from ledger to event to
            analysis to pipeline to results

      The asimov workflow

Screen Reader Compatibility
----------------------------

- Use semantic headings (don't skip levels)
- Use descriptive link text (not "click here")
- Provide text alternatives for visual information
- Use tables for tabular data (not layout)

✅ **Good:**

.. code-block:: rst

   See the :ref:`installation-guide` for setup instructions.

❌ **Bad:**

.. code-block:: rst

   `Click here <installation.html>`_ for more information.

File Organization
=================

File Naming
-----------

Documentation Files
~~~~~~~~~~~~~~~~~~~

Use lowercase with hyphens:

✅ **Good:**

- ``getting-started.rst``
- ``user-guide-events.rst``
- ``api-reference.rst``

❌ **Bad:**

- ``GettingStarted.rst`` ← CamelCase
- ``user_guide_events.rst`` ← Underscores
- ``API-Reference.rst`` ← Mixed case

Directory Structure
-------------------

.. code-block:: text

   docs/
   ├── source/
   │   ├── index.rst                 # Homepage
   │   ├── getting-started.rst       # Quick start
   │   ├── installation.rst          # Installation
   │   ├── concepts.rst              # Core concepts
   │   ├── glossary.rst              # Terminology
   │   ├── style-guide.rst           # This document
   │   ├── user-guide/               # User guides
   │   │   ├── projects.rst
   │   │   ├── events.rst
   │   │   └── analyses.rst
   │   ├── tutorials/                # Step-by-step tutorials
   │   │   ├── first-analysis.rst
   │   │   └── multi-event-study.rst
   │   ├── advanced/                 # Advanced topics
   │   │   ├── custom-pipelines.rst
   │   │   └── ledger-backends.rst
   │   ├── api/                      # API reference
   │   │   ├── project.rst
   │   │   ├── event.rst
   │   │   └── pipeline.rst
   │   └── gw-features/              # GW-specific features
   │       ├── gracedb.rst
   │       └── calibration.rst

File Headers
------------

Every documentation file should start with:

.. code-block:: rst

   .. _unique-reference-label:

   =================
   Document Title
   =================

   Brief description of what this document covers.

   .. contents:: Table of Contents
      :depth: 2
      :local:

Metadata
--------

Include metadata for tracking when appropriate:

.. code-block:: rst

   :Author: Your Name
   :Date: 2026-01-26
   :Version: 1.0

Review Checklist
================

Before submitting documentation, verify:

Content
-------

- [ ] Information is accurate and tested
- [ ] Examples are complete and runnable
- [ ] All steps are in logical order
- [ ] Prerequisites are clearly stated
- [ ] Troubleshooting covers common issues

Style
-----

- [ ] Voice matches document type (tutorial/guide/reference)
- [ ] Consistent terminology (Analysis not Production)
- [ ] Present tense used throughout
- [ ] Active voice in user-facing docs
- [ ] No contractions in formal docs

Formatting
----------

- [ ] Headers follow hierarchy (no skipped levels)
- [ ] Code blocks have syntax highlighting
- [ ] Inline code uses double backticks
- [ ] Lists use consistent bullet style
- [ ] Tables are properly formatted

Code Examples
-------------

- [ ] Include shell prompt (``$``) for commands
- [ ] Show expected output
- [ ] Python examples include imports
- [ ] YAML examples are properly indented
- [ ] Examples have been tested

Acronyms and Terms
------------------

- [ ] All acronyms defined on first use
- [ ] Technical terms explained
- [ ] GW-specific terms identified (if in general docs)
- [ ] Preferred terminology used consistently

Links and References
--------------------

- [ ] All internal links use ``:ref:``
- [ ] External links are valid
- [ ] Cross-references are accurate
- [ ] API references use proper Sphinx roles

Accessibility
-------------

- [ ] No idioms or cultural references
- [ ] Gender-neutral language
- [ ] Images have alt text
- [ ] Link text is descriptive
- [ ] Headings are semantic

Technical
---------

- [ ] File named with lowercase and hyphens
- [ ] Reference label is unique
- [ ] Added to appropriate TOC tree
- [ ] Sphinx builds without warnings
- [ ] All links valid (``make linkcheck``)

Complete Example: Tutorial Page
================================

.. code-block:: rst

   .. _tutorial-first-analysis:

   ==========================
   Your First Analysis
   ==========================

   This tutorial guides you through creating and running your first analysis with
   asimov. You'll learn how to set up a project, add an event, configure an
   analysis, and submit it to a computing cluster.

   .. contents:: In this tutorial
      :depth: 2
      :local:

   Prerequisites
   -------------

   Before starting, ensure you have:

   - Asimov installed (see :ref:`installation-guide`)
   - Access to an HTCondor cluster
   - Basic familiarity with command-line interfaces

   Estimated time: 30 minutes

   Creating a Project
   ------------------

   First, create a new directory and initialize it as an asimov project:

   .. code-block:: bash

      $ mkdir my-analysis
      $ cd my-analysis
      $ asimov init "My First Project"
      ● New project created successfully!

   This creates the project structure with a ledger file and directories for
   storing results.

   .. note::
      The project name can include spaces and should be descriptive. This name
      appears in reports and web pages.

   Adding an Event
   ---------------

   Next, add an event to analyze. For this tutorial, we'll create a simple event
   manually:

   .. code-block:: bash

      $ asimov event create --name TestEvent
      ● Successfully created event TestEvent

   Verify the event was added:

   .. code-block:: bash

      $ asimov report status
      TestEvent

      No analyses configured.

   Configuring an Analysis
   -----------------------

   Now add an analysis to the event. Create a file called ``analysis.yaml``:

   .. code-block:: yaml

      kind: analysis
      name: Test0
      pipeline: bilby
      waveform:
        approximant: IMRPhenomXPHM
      status: ready

   Apply this configuration:

   .. code-block:: bash

      $ asimov apply -f analysis.yaml -e TestEvent
      ● Successfully applied Test0 to TestEvent

   Building and Submitting
   ------------------------

   Build the analysis configuration:

   .. code-block:: bash

      $ asimov manage build
      ● Working on TestEvent
         Working on analysis Test0
      Analysis config Test0 created.

   Submit to the cluster:

   .. code-block:: bash

      $ asimov manage submit
      ● Submitted TestEvent/Test0

   The job is now running on the cluster!

   Monitoring Progress
   -------------------

   Check the status of your analysis:

   .. code-block:: bash

      $ asimov monitor
      TestEvent
      - Test0[bilby]
        ● Test0 is running (condor id: 12345678)

   .. tip::
      Use ``asimov start`` to automatically monitor your analyses every 15 minutes.

   Next Steps
   ----------

   Congratulations! You've completed your first asimov analysis. Next, try:

   - :ref:`user-guide-events` - Learn more about configuring events
   - :ref:`user-guide-analyses` - Explore advanced analysis options
   - :ref:`tutorial-multi-event` - Run analyses on multiple events

   Troubleshooting
   ---------------

   **Problem:** "HTCondor not available" error

   **Solution:** Ensure HTCondor is installed and you have access to submit jobs:

   .. code-block:: bash

      $ condor_q

   If this fails, contact your system administrator.

   **Problem:** Analysis stuck in "wait" status

   **Solution:** Check that the status is set to "ready" in your configuration.

   See Also
   --------

   - :ref:`cli-reference` - Complete command reference
   - :ref:`troubleshooting` - Common problems and solutions

Quick Reference
===============

Voice Quick Reference
---------------------

.. list-table::
   :header-rows: 1
   :widths: 20 15 15 25

   * - Document Type
     - Person
     - Tense
     - Style
   * - Tutorial
     - Second (you)
     - Present
     - Friendly, instructional
   * - User Guide
     - Second (you)
     - Present
     - Professional, clear
   * - Reference
     - Third/Passive
     - Present
     - Formal, precise
   * - Docstring
     - Imperative/Third
     - Present
     - Technical, concise

Common Phrases
--------------

.. list-table::
   :header-rows: 1
   :widths: 30 40

   * - ❌ Avoid
     - ✅ Use Instead
   * - simply, just, easy
     - (omit or be specific)
   * - click here
     - descriptive link text
   * - he/she/his/her
     - they/their
   * - in order to
     - to
   * - utilize
     - use
   * - prior to
     - before
   * - subsequent to
     - after
   * - in the event that
     - if

Terminology Quick Reference
----------------------------

.. list-table::
   :header-rows: 1
   :widths: 25 25 35

   * - Current Term
     - Deprecated
     - Notes
   * - Analysis
     - Production
     - v0.4.0+
   * - SimpleAnalysis
     - Production
     - Analysis type
   * - asimov
     - olivaw (command alias)
     - Prefer asimov in docs
   * - HTCondor
     - Condor
     - Official product name

Feedback
========

This style guide is a living document. If you have suggestions for improvements:

1. Open an issue on GitHub with label ``documentation``
2. Include specific examples
3. Explain the rationale for the change

Questions? Contact the documentation maintainer or ask in the community chat.

----

:Last Updated: 2026-01-26
:Maintained By: Asimov Documentation Team
