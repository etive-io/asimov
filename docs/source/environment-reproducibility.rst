Environment Reproducibility
============================

Asimov automatically captures the software environment for each analysis to enable full reproducibility.

Overview
--------

When asimov builds an analysis configuration, it automatically captures:

- The Python version and executable path
- All installed Python packages (via ``pip freeze``)
- Conda environment details (if running in a conda environment)
- The timestamp when the environment was captured

This information is stored in the analysis working directory and, when the analysis completes, is also stored in the results store alongside the analysis outputs.

How It Works
------------

Environment capture happens automatically during the ``build`` phase of an analysis.
When you run:

.. code-block:: console

   $ asimov manage build

Asimov will:

1. Detect the current Python environment type (conda, virtualenv, or system Python)
2. Capture the list of installed packages
3. Save this information to the analysis working directory as:
   
   - ``environment.json`` - Metadata about the environment (Python version, environment type, timestamp)
   - ``environment-pip.txt`` - Output of ``pip freeze`` (always captured)
   - ``environment-conda.txt`` - Output of ``conda list --export`` (if in a conda environment)

When the analysis completes and results are uploaded, these environment files are automatically stored in the results store along with the analysis outputs.

Accessing Environment Information
----------------------------------

The environment files are stored in two locations:

1. **Working Directory**: In the analysis run directory (``rundir``), you can find the environment files immediately after building.

2. **Results Store**: After the analysis is uploaded, the environment files are stored in the results store and can be retrieved using asimov's storage API.

Example: Retrieving Environment Files
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

You can retrieve environment files from the results store using the asimov Python API:

.. code-block:: python

   from asimov.storage import Store
   from asimov import config
   
   # Get the results store
   store = Store(root=config.get("storage", "directory"))
   
   # List all files for an analysis
   files = store.manifest.list_resources("GW150914_095045", "prod0")
   
   # Fetch the environment metadata
   env_json = store.fetch_file("GW150914_095045", "prod0", "environment.json")
   
   # Read the environment information
   import json
   with open(env_json, 'r') as f:
       env_info = json.load(f)
       print(f"Analysis was run with Python {env_info['python_version']}")
       print(f"Environment type: {env_info['environment_type']}")
       print(f"Captured at: {env_info['timestamp']}")

Reproducing an Analysis
-----------------------

To reproduce an analysis with the exact same environment:

1. Retrieve the environment files from the results store (as shown above)
2. Create a new environment using the captured specifications:

For pip environments (Linux/macOS):

.. code-block:: console

   $ python -m venv reproduce-env
   $ source reproduce-env/bin/activate
   $ pip install -r environment-pip.txt

For pip environments (Windows):

.. code-block:: console

   > python -m venv reproduce-env
   > reproduce-env\Scripts\activate
   > pip install -r environment-pip.txt

For conda environments (all platforms):

.. code-block:: console

   $ conda create --name reproduce-env --file environment-conda.txt
   $ conda activate reproduce-env

3. Run the analysis using the same configuration files stored in the event repository

Dry Run Mode
------------

When running asimov in dry-run mode, environment capture is skipped to avoid unnecessary overhead:

.. code-block:: console

   $ asimov manage build --dryrun

In this case, no environment files will be created.

Technical Details
-----------------

Environment Capture Module
~~~~~~~~~~~~~~~~~~~~~~~~~~~

The environment capture functionality is implemented in ``asimov.environment``:

.. autoclass:: asimov.environment.EnvironmentCapture
   :members:
   :undoc-members:

.. autofunction:: asimov.environment.capture_and_save_environment

Pipeline Integration
~~~~~~~~~~~~~~~~~~~~

Environment capture is integrated into the pipeline build process via the ``before_config`` hook:

- When ``Pipeline.before_config()`` is called, it automatically invokes ``_capture_environment()``
- The captured environment file paths are stored in ``production.meta['environment']['files']``
- When results are uploaded, ``_store_environment_files()`` is called to store the files in the results store

Metadata Structure
~~~~~~~~~~~~~~~~~~

The environment metadata in ``production.meta`` has the following structure:

.. code-block:: python

   {
       'environment': {
           'captured_at': True,
           'files': {
               'metadata': '/path/to/environment.json',
               'pip': '/path/to/environment-pip.txt',
               'conda': '/path/to/environment-conda.txt'  # Only if in conda env
           }
       }
   }

Limitations
-----------

Current Limitations
~~~~~~~~~~~~~~~~~~~

1. **Environment Detection**: The current implementation captures the environment at build time. If packages are updated between building and running the analysis, those changes won't be reflected.

2. **System Dependencies**: Only Python packages are captured. System-level dependencies (e.g., LAPACK, FFTW) are not currently recorded.

3. **Container Support**: While the current implementation provides a foundation, full container-based reproducibility (e.g., using Docker or Singularity) is planned for future releases.

Future Enhancements
~~~~~~~~~~~~~~~~~~~

Planned improvements include:

- Container-based environment management (Docker/Singularity support)
- Shared environment management to avoid duplication when multiple analyses use the same environment
- System-level dependency tracking
- Automatic environment restoration from stored specifications

See Also
--------

- :ref:`Analyses <analyses>`
- :ref:`Storage API <storage>`
- :ref:`Pipeline Development <pipelines-dev>`
