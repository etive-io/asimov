.. _configuration:

===========================
Asimov Configuration Guide
===========================

Asimov uses configuration files to customize its behavior for different environments and use cases. This guide explains all available configuration options and how to use them effectively.

Configuration File Locations
=============================

Asimov searches for configuration files in the following locations (in order of precedence):

1. ``asimov.conf`` in the current working directory (project-specific)
2. ``~/.config/asimov/asimov.conf`` (user-specific)
3. ``/etc/asimov/asimov.conf`` (system-wide)
4. Default configuration embedded in asimov

Settings from files with higher precedence override those with lower precedence.

Configuration Format
====================

Configuration files use the INI format with sections and key-value pairs:

.. code-block:: ini

   [section]
   key = value
   another_key = another value

Comments can be added with ``#`` or ``;``:

.. code-block:: ini

   # This is a comment
   ; This is also a comment
   key = value  # Inline comment

Configuration Sections
======================

``[general]``
-------------

General asimov settings.

``git_default``
   Default location for git operations.
   
   - **Default**: ``.`` (current directory)
   - **Example**: ``git_default = /home/user/repos``

``rundir_default``
   Default name for run directories.
   
   - **Default**: ``working``
   - **Example**: ``rundir_default = run_dir``

``calibration``
   Default calibration version identifier.
   
   - **Default**: ``C01``
   - **Example**: ``calibration = C02``

``calibration_directory``
   Default directory name for calibration files.
   
   - **Default**: ``C01_offline``
   - **Example**: ``calibration_directory = C02_offline``

``webroot``
   Root directory for web page output.
   
   - **Default**: ``pages/``
   - **Example**: ``webroot = /var/www/html/asimov/``

``logger``
   Logging output destination.
   
   - **Options**: ``file``, ``console``, ``both``
   - **Default**: ``file``

``[logging]``
-------------

Logging configuration.

``level``
   Minimum logging level to record.
   
   - **Options**: ``debug``, ``info``, ``warning``, ``error``, ``critical``
   - **Default**: ``info``
   - **Example**: ``level = debug``

``logging level``
   Alternative name for ``level`` (for backwards compatibility).

``print level``
   Minimum level for console output (when logger includes console).
   
   - **Options**: Same as ``level``
   - **Default**: ``info``

``location``
   Directory for log files.
   
   - **Default**: ``logs``
   - **Example**: ``location = /var/log/asimov``

``[project]``
-------------

Project-specific settings. This section is typically empty in the default configuration and can be used to store custom project metadata.

``[report]``
------------

Settings for HTML report generation.

``timezone``
   Timezone for timestamps in reports.
   
   - **Default**: ``Europe/London``
   - **Example**: ``timezone = America/New_York``
   - Uses standard timezone names (e.g., ``US/Pacific``, ``UTC``)

``[asimov start]``
------------------

Settings for the ``asimov start`` daemon mode.

``accounting``
   Default HTCondor accounting group for daemon-submitted jobs.
   
   - **Default**: ``ligo.dev.o4.cbc.pe.lalinference``
   - **Example**: ``accounting = ligo.prod.o4.cbc.pe.bilby``

``[pipelines]``
---------------

Global settings for all pipelines.

``environment``
   Path to conda environment or setup script for pipeline execution.
   
   - **Default**: ``/cvmfs/oasis.opensciencegrid.org/ligo/sw/conda/envs/igwn-py39``
   - **Example**: ``environment = /home/user/conda/envs/pe``

Pipeline-Specific Sections
---------------------------

Each pipeline can have its own configuration section with pipeline-specific settings.

``[bilby]``
~~~~~~~~~~~

Settings specific to the bilby pipeline (inherits from ``[pipelines]``).

``environment``
   Conda environment for bilby jobs (overrides global ``environment``).

``[rift]``
~~~~~~~~~~

Settings specific to the RIFT pipeline.

``environment``
   Conda environment for RIFT jobs.
   
   - **Example**: ``environment = /cvmfs/oasis.opensciencegrid.org/ligo/sw/conda/envs/igwn-py39``

``[bayeswave]``
~~~~~~~~~~~~~~~

Settings specific to the BayesWave pipeline.

``environment``
   Conda environment for BayesWave jobs.

``[lalinference]``
~~~~~~~~~~~~~~~~~~

Settings specific to the LALInference pipeline (deprecated in v0.7).

``environment``
   Conda environment for LALInference jobs.

``[ledger]``
------------

Ledger storage backend configuration.

``engine``
   Ledger storage engine to use.
   
   - **Options**: ``yamlfile``, ``gitlab``, ``tinydb``, ``mongodb``
   - **Default**: ``yamlfile``

``location``
   Location of the ledger.
   
   - For ``yamlfile``: Path to YAML file (default: ``ledger.yaml``)
   - For ``gitlab``: GitLab project path (e.g., ``group/project``)
   - For ``tinydb``: Path to TinyDB database file
   - For ``mongodb``: MongoDB connection string

**YAML File Example:**

.. code-block:: ini

   [ledger]
   engine = yamlfile
   location = .asimov/ledger.yml

**GitLab Example:**

.. code-block:: ini

   [ledger]
   engine = gitlab
   location = pe-group/o4-events

**TinyDB Example:**

.. code-block:: ini

   [ledger]
   engine = tinydb
   location = .asimov/ledger.json

**MongoDB Example:**

.. code-block:: ini

   [ledger]
   engine = mongodb
   location = mongodb://localhost:27017/asimov

``[storage]``
-------------

Configuration for result storage.

``root``
   Root directory for all storage operations.
   
   - **Default**: ``""`` (current directory)
   - **Example**: ``root = /data/pe_results``

``results_store``
   Directory for storing completed results (relative to ``root``).
   
   - **Default**: ``results/``
   - **Example**: ``results_store = archive/``

The final storage path is constructed as ``{root}/{results_store}/``.

``[condor]``
------------

HTCondor integration settings.

``cache_time``
   Time (in seconds) to cache Condor query results.
   
   - **Default**: ``900`` (15 minutes)
   - **Example**: ``cache_time = 600``

``cron_minute``
   Cron expression for automatic monitoring schedule.
   
   - **Default**: ``*/15`` (every 15 minutes)
   - **Example**: ``cron_minute = */30`` (every 30 minutes)

``accounting``
   Default HTCondor accounting group.
   
   - **Default**: ``ligo.dev.o4.cbc.pe.bilby``
   - **Example**: ``accounting = ligo.prod.o4.cbc.pe.bilby``

``scheduler``
   HTCondor scheduler hostname(s).
   
   - **Example**: ``scheduler = ldas-pcdev5.ligo.caltech.edu``
   - Can specify multiple schedulers comma-separated

``collector``
   HTCondor collector hostname.
   
   - **Example**: ``collector = collector.ligo.org``

``[pesummary]``
---------------

PESummary post-processing configuration.

``executable``
   Path to the PESummary executable.
   
   - **Default**: ``/cvmfs/oasis.opensciencegrid.org/ligo/sw/conda/envs/igwn-py39/bin/summarypages``
   - **Example**: ``executable = /home/user/conda/envs/pe/bin/summarypages``

``accounting``
   HTCondor accounting group for PESummary jobs.
   
   - **Example**: ``accounting = ligo.dev.o4.cbc.pe.lalinference``

``[gracedb]``
-------------

GraceDB integration settings.

``url``
   GraceDB API endpoint URL.
   
   - **Default**: ``https://gracedb.ligo.org/api/``
   - **Example** (development): ``url = https://gracedb-dev.ligo.org/api/``

``service_url``
   Alternative name for ``url``.

``[mattermost]``
----------------

Mattermost notification settings.

``webhook_url``
   Incoming webhook URL for Mattermost notifications.
   
   - **Example**: ``webhook_url = https://chat.ligo.org/hooks/xxxxx``

``channel``
   Default channel for notifications.
   
   - **Example**: ``channel = parameter-estimation``

``username``
   Bot username for notifications.
   
   - **Example**: ``username = asimov-bot``

``[theme]``
-----------

Report theming configuration.

``name``
   Name of the theme directory for HTML reports.
   
   - **Default**: ``report-theme``
   - **Example**: ``name = custom-theme``

The theme directory should be located in the asimov package or in the project directory.

``[templating]``
----------------

Template configuration (used by the ``config.rst`` guide).

``directory``
   Directory containing configuration file templates.
   
   - **Example**: ``directory = config-templates``

Templates are Liquid template files used to generate pipeline configuration files.

Environment Variables
=====================

Asimov also respects certain environment variables:

``ASIMOV_CONFIG``
   Path to configuration file (overrides default search paths).
   
   .. code-block:: bash
   
      export ASIMOV_CONFIG=/path/to/my/config.ini
      asimov manage build

``LIGO_USERNAME``
   LIGO.ORG username for authentication.

``LIGO_PASSWORD``
   LIGO.ORG password (not recommended; use kinit instead).

Configuration Hierarchy
========================

Configuration settings are applied in the following order (later overrides earlier):

1. **Default configuration** embedded in asimov
2. **System-wide configuration** (``/etc/asimov/asimov.conf``)
3. **User configuration** (``~/.config/asimov/asimov.conf``)
4. **Project configuration** (``./asimov.conf`` in current directory)
5. **Environment variables** (where applicable)
6. **Command-line arguments** (highest precedence)

Example Configurations
======================

Minimal Local Configuration
----------------------------

For a simple local project:

.. code-block:: ini

   [general]
   logger = console
   
   [logging]
   level = info
   
   [ledger]
   engine = yamlfile
   location = .asimov/ledger.yml
   
   [storage]
   root = .
   results_store = results/

Production Cluster Configuration
---------------------------------

For production use on an HTCondor cluster:

.. code-block:: ini

   [general]
   logger = file
   calibration = C02
   calibration_directory = C02_offline
   
   [logging]
   level = warning
   location = /home/pe/logs/asimov
   
   [ledger]
   engine = gitlab
   location = ligo-pe/o4-catalog
   
   [storage]
   root = /data/pe_results
   results_store = o4/
   
   [condor]
   accounting = ligo.prod.o4.cbc.pe.bilby
   scheduler = ldas-pcdev5.ligo.caltech.edu
   cache_time = 300
   
   [pipelines]
   environment = /cvmfs/oasis.opensciencegrid.org/ligo/sw/conda/envs/igwn-py39
   
   [pesummary]
   accounting = ligo.prod.o4.cbc.pe.lalinference
   
   [mattermost]
   webhook_url = https://chat.ligo.org/hooks/xxxxx
   channel = o4-parameter-estimation
   
   [gracedb]
   url = https://gracedb.ligo.org/api/

Development Configuration
--------------------------

For development and testing:

.. code-block:: ini

   [general]
   logger = both
   
   [logging]
   level = debug
   print level = info
   location = dev_logs/
   
   [ledger]
   engine = yamlfile
   location = test_ledger.yml
   
   [storage]
   root = /tmp/asimov_test
   results_store = results/
   
   [condor]
   accounting = ligo.dev.o4.cbc.pe.bilby
   cache_time = 60
   
   [gracedb]
   url = https://gracedb-dev.ligo.org/api/

Multi-Environment Setup
------------------------

You can maintain different configurations for different environments:

**Production** (``~/.config/asimov/production.conf``):

.. code-block:: ini

   [condor]
   accounting = ligo.prod.o4.cbc.pe.bilby
   
   [gracedb]
   url = https://gracedb.ligo.org/api/

**Development** (``~/.config/asimov/development.conf``):

.. code-block:: ini

   [condor]
   accounting = ligo.dev.o4.cbc.pe.bilby
   
   [gracedb]
   url = https://gracedb-dev.ligo.org/api/

Then use:

.. code-block:: bash

   export ASIMOV_CONFIG=~/.config/asimov/production.conf
   asimov manage submit

Troubleshooting Configuration
==============================

Viewing Active Configuration
-----------------------------

To see which configuration values are active, you can use Python:

.. code-block:: python

   from asimov import config
   
   # View all sections
   print(config.sections())
   
   # View specific value
   print(config.get('ledger', 'engine'))
   
   # View all values in a section
   print(dict(config.items('condor')))

Common Issues
-------------

**Configuration not found**

If asimov can't find your configuration file:

1. Check file permissions (must be readable)
2. Verify the file location is in the search path
3. Use ``ASIMOV_CONFIG`` environment variable to specify exact path

**Settings not taking effect**

If your settings aren't being applied:

1. Check configuration hierarchy - a higher-precedence file may override your settings
2. Verify section and key names are correct (case-sensitive)
3. Check for syntax errors in INI file

**Pipeline environment issues**

If pipelines can't find executables:

1. Verify ``environment`` path is correct
2. Ensure the environment contains required packages
3. Check conda environment activation works manually

Best Practices
==============

1. **Use project-specific configuration** for project settings (in ``./asimov.conf``)
2. **Use user configuration** for personal preferences (in ``~/.config/asimov/``)
3. **Use system configuration** for cluster-wide defaults (in ``/etc/asimov/``)
4. **Keep sensitive information** (like webhooks) in user configuration, not in project files committed to git
5. **Document custom settings** with comments in configuration files
6. **Test configuration changes** in development before applying to production
7. **Version control** project configuration files (but not user/system configs)

See Also
========

- :ref:`ledger`: Ledger format and metadata hierarchy
- :ref:`pipelines-dev`: Creating custom pipelines
- :ref:`storage`: Result storage system

