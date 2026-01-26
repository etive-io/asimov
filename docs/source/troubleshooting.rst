.. _troubleshooting:

====================
Troubleshooting Guide
====================

This guide helps diagnose and resolve common issues when using asimov. For each problem, we provide symptoms, causes, and solutions.

Getting Help
============

If you can't find a solution in this guide:

1. Check the :ref:`FAQ <faq>` for common questions
2. Review the relevant documentation section
3. Search the `issue tracker <https://github.com/etive-io/asimov/issues>`_
4. Ask in the LIGO/Virgo/KAGRA collaboration Mattermost channels
5. Open a new issue with a minimal reproducible example

Installation and Setup Issues
==============================

"This isn't an asimov project"
------------------------------

**Symptom:**

.. code-block:: text

   This isn't an asimov project

**Cause:**

You're trying to run asimov commands outside of a valid asimov project directory (one that contains a ``.asimov/`` subdirectory).

**Solutions:**

1. Change to your project directory:

   .. code-block:: bash
   
      cd /path/to/my-project

2. Initialize a new project if needed:

   .. code-block:: bash
   
      asimov init "My Project"

3. Check if ``.asimov/`` directory exists:

   .. code-block:: bash
   
      ls -la .asimov

Git Not Configured
------------------

**Symptom:**

.. code-block:: text

   fatal: unable to auto-detect email address

**Cause:**

Git is not configured with your user information.

**Solution:**

Configure git:

.. code-block:: bash

   git config --global user.email "you@example.com"
   git config --global user.name "Your Name"

Missing Dependencies
--------------------

**Symptom:**

.. code-block:: text

   ModuleNotFoundError: No module named 'htcondor'

**Cause:**

Required dependencies are not installed.

**Solution:**

Reinstall asimov with all dependencies:

.. code-block:: bash

   pip install --upgrade asimov

Or for development:

.. code-block:: bash

   pip install -e .[docs]

Configuration Issues
====================

Configuration File Not Found
----------------------------

**Symptom:**

Asimov uses default settings instead of your custom configuration.

**Diagnosis:**

Check which configuration files asimov is reading:

.. code-block:: python

   from asimov import config
   print([f for f in ['/etc/asimov/asimov.conf', 
                      '~/.config/asimov/asimov.conf',
                      './asimov.conf'] if os.path.exists(f)])

**Solutions:**

1. Ensure your config file is in the right location
2. Check file permissions (must be readable)
3. Use environment variable to specify location:

   .. code-block:: bash
   
      export ASIMOV_CONFIG=/path/to/asimov.conf

Settings Not Taking Effect
---------------------------

**Symptom:**

Configuration changes don't affect asimov behavior.

**Diagnosis:**

1. Check for syntax errors in INI file
2. Verify section and key names (case-sensitive)
3. Look for higher-precedence configuration overriding your settings

**Solution:**

View active configuration:

.. code-block:: python

   from asimov import config
   # Show all sections
   print(config.sections())
   # Show specific value
   print(config.get('ledger', 'engine'))

Ledger Issues
=============

Ledger File Corrupted
---------------------

**Symptom:**

.. code-block:: text

   yaml.scanner.ScannerError: while scanning...

**Cause:**

YAML syntax error in ledger file.

**Solutions:**

1. Validate YAML syntax:

   .. code-block:: bash
   
      python -c "import yaml; yaml.safe_load(open('.asimov/ledger.yml'))"

2. Check recent changes in git:

   .. code-block:: bash
   
      cd .asimov
      git diff ledger.yml

3. Restore from backup:

   .. code-block:: bash
   
      cd .asimov
      git checkout HEAD~1 ledger.yml

Ledger Merge Conflicts
-----------------------

**Symptom:**

Merge conflict markers in ledger file:

.. code-block:: text

   <<<<<<< HEAD
   status: running
   =======
   status: finished
   >>>>>>> branch

**Solution:**

1. Manually resolve conflicts in ``.asimov/ledger.yml``
2. Remove conflict markers
3. Commit the resolution:

   .. code-block:: bash
   
      cd .asimov
      git add ledger.yml
      git commit -m "Resolve ledger conflict"

Cannot Access GitLab Ledger
----------------------------

**Symptom:**

.. code-block:: text

   gitlab.exceptions.GitlabAuthenticationError

**Cause:**

Missing or invalid GitLab credentials.

**Solution:**

1. Set GitLab token:

   .. code-block:: bash
   
      export GITLAB_TOKEN=your-token-here

2. Or use SSH authentication with ``git@git.ligo.org``

3. Verify GitLab access:

   .. code-block:: bash
   
      curl -H "PRIVATE-TOKEN: $GITLAB_TOKEN" https://git.ligo.org/api/v4/user

Job Submission Issues
=====================

HTCondor Authentication Failed
-------------------------------

**Symptom:**

.. code-block:: text

   RuntimeError: Failed to authenticate with HTCondor

**Cause:**

Missing or expired credentials.

**Solutions:**

1. Refresh Kerberos ticket:

   .. code-block:: bash
   
      kinit username@LIGO.ORG

2. Get SciToken:

   .. code-block:: bash
   
      htgettoken --audience https://htcondor.ligo.org

3. Check token validity:

   .. code-block:: bash
   
      htokendecode

Cannot Connect to Scheduler
----------------------------

**Symptom:**

.. code-block:: text

   RuntimeError: Failed to contact scheduler

**Cause:**

HTCondor scheduler is unreachable or configuration is incorrect.

**Solutions:**

1. Verify scheduler configuration:

   .. code-block:: bash
   
      condor_status -schedd

2. Check network connectivity:

   .. code-block:: bash
   
      ping ldas-pcdev5.ligo.caltech.edu

3. Set correct scheduler in configuration:

   .. code-block:: ini
   
      [condor]
      scheduler = ldas-pcdev5.ligo.caltech.edu

Job Submission Failed
---------------------

**Symptom:**

.. code-block:: text

   PipelineException: Failed to submit DAG

**Diagnosis:**

Check the DAG submit file and logs:

.. code-block:: bash

   # Find the DAG submit directory
   cd checkouts/GW150914_095045/Prod0/
   
   # Check DAG file syntax
   condor_submit_dag -no_submit dag.dag

**Common causes and solutions:**

1. **Missing executable**: Ensure pipeline executables are in PATH or specified with absolute path

2. **Insufficient permissions**: Check write permissions in run directory

3. **Invalid accounting group**: Verify accounting group in configuration:

   .. code-block:: ini
   
      [condor]
      accounting = ligo.dev.o4.cbc.pe.bilby

4. **Resource request too large**: Reduce memory/CPU requests in ledger

Job Monitoring Issues
=====================

Jobs Stuck in Held State
-------------------------

**Symptom:**

Jobs show status "held" in condor_q and asimov reports "stuck".

**Diagnosis:**

Check hold reason:

.. code-block:: bash

   condor_q -hold <job_id>

**Common causes and solutions:**

1. **Memory exceeded**: Increase memory request in ledger metadata

   .. code-block:: yaml
   
      scheduler:
        request memory: 8GB

2. **Disk quota exceeded**: Clean up temporary files or increase disk request

3. **Missing input files**: Verify all input files exist and are accessible

4. **Credential expired**: Refresh credentials and release job:

   .. code-block:: bash
   
      htgettoken
      condor_release <job_id>

Jobs Not Starting
-----------------

**Symptom:**

Jobs remain in idle state indefinitely.

**Diagnosis:**

Check job requirements:

.. code-block:: bash

   condor_q -better-analyze <job_id>

**Solutions:**

1. Relax requirements in submit file
2. Increase job priority
3. Check if accounting group has available resources

Monitoring Daemon Not Working
------------------------------

**Symptom:**

``asimov start`` doesn't seem to monitor jobs.

**Diagnosis:**

Check if daemon is running:

.. code-block:: bash

   ps aux | grep asimov

**Solutions:**

1. Stop and restart daemon:

   .. code-block:: bash
   
      asimov stop
      asimov start

2. Run monitor manually to see errors:

   .. code-block:: bash
   
      asimov monitor --once

3. Check log files:

   .. code-block:: bash
   
      cat logs/asimov.log

Job Status Not Updating
------------------------

**Symptom:**

Job finished but asimov still shows "running".

**Cause:**

Completion detection failed or cache not refreshed.

**Solutions:**

1. Force status update:

   .. code-block:: bash
   
      asimov monitor --once

2. Check completion criteria for pipeline (see pipeline documentation)

3. Manually update status:

   .. code-block:: bash
   
      asimov production update EVENT PROD --status finished

Pipeline Issues
===============

Configuration File Generation Failed
-------------------------------------

**Symptom:**

.. code-block:: text

   PipelineException: Failed to generate configuration

**Diagnosis:**

Check template and metadata:

.. code-block:: bash

   # View the metadata
   asimov report status --format yaml --event EVENT

**Common causes:**

1. **Missing required metadata**: Add required fields to ledger
2. **Template error**: Check Liquid template syntax
3. **Invalid values**: Verify metadata types (numbers vs strings)

**Solution:**

Add missing metadata in ledger:

.. code-block:: yaml

   productions:
     - Prod0:
         pipeline: bilby
         approximant: IMRPhenomXPHM
         # Add any missing required fields

Pipeline Executable Not Found
------------------------------

**Symptom:**

.. code-block:: text

   FileNotFoundError: [Errno 2] No such file or directory: 'bilby_pipe'

**Cause:**

Pipeline software not installed or not in PATH.

**Solutions:**

1. Install pipeline:

   .. code-block:: bash
   
      conda install -c conda-forge bilby_pipe

2. Set correct environment in configuration:

   .. code-block:: ini
   
      [pipelines]
      environment = /path/to/conda/env

3. Verify executable exists:

   .. code-block:: bash
   
      which bilby_pipe

DAG File Syntax Error
---------------------

**Symptom:**

.. code-block:: text

   ERROR: parse error on line X

**Cause:**

Generated DAG file has syntax errors.

**Diagnosis:**

Check DAG file:

.. code-block:: bash

   cat checkouts/EVENT/PROD/dag.dag

**Solution:**

This usually indicates a pipeline bug. Report the issue with:

1. Pipeline name and version
2. Full ledger entry for the production
3. Generated DAG file content

Data Access Issues
==================

Cannot Find Calibration Files
------------------------------

**Symptom:**

.. code-block:: text

   FileNotFoundError: Calibration file not found

**Cause:**

Calibration files not in expected location.

**Solutions:**

1. Check path in ledger is correct:

   .. code-block:: yaml
   
      data:
        calibration:
          H1: /path/to/H1.dat

2. Use absolute paths or paths relative to repository

3. Verify files exist:

   .. code-block:: bash
   
      ls checkouts/EVENT/C01_offline/calibration/

Frame Data Not Accessible
--------------------------

**Symptom:**

.. code-block:: text

   RuntimeError: Could not find frame files

**Cause:**

No access to frame data or incorrect channel names.

**Solutions:**

1. Verify LIGO.ORG credentials:

   .. code-block:: bash
   
      kinit username@LIGO.ORG

2. Check frame types and channels in ledger:

   .. code-block:: yaml
   
      data:
        channels:
          H1: H1:DCS-CALIB_STRAIN_C01
        frame-types:
          H1: H1_HOFT_C01

3. Test data access manually:

   .. code-block:: bash
   
      gw_data_find -o H -t H1_HOFT_C01 -s START -e END

PSD Files Missing
-----------------

**Symptom:**

Analysis fails due to missing PSD files.

**Cause:**

PSD generation analysis hasn't completed or paths incorrect.

**Solutions:**

1. Check PSD generation completed:

   .. code-block:: bash
   
      asimov report status --event EVENT | grep -i psd

2. Verify PSD paths in ledger:

   .. code-block:: yaml
   
      psds:
        H1: path/to/H1-psd.txt

3. Ensure dependent analysis finished:

   .. code-block:: yaml
   
      productions:
        - Prod0:  # PSD generation
            status: finished
        - Prod1:  # PE analysis
            needs: [Prod0]  # Dependency

Storage and Results Issues
===========================

Results Not Being Collected
----------------------------

**Symptom:**

Job finished but results not in store.

**Diagnosis:**

Check result collection in logs:

.. code-block:: bash

   grep -i "collect" logs/asimov.log

**Solutions:**

1. Verify storage configuration:

   .. code-block:: ini
   
      [storage]
      root = /data
      results_store = results/

2. Check write permissions:

   .. code-block:: bash
   
      test -w /data/results && echo "writable" || echo "not writable"

3. Manually trigger collection:

   .. code-block:: bash
   
      asimov monitor --once --event EVENT

Hash Verification Failed
-------------------------

**Symptom:**

.. code-block:: text

   ValueError: Hash mismatch for file

**Cause:**

File was modified after being stored or corruption during transfer.

**Solution:**

1. Re-collect results:

   .. code-block:: bash
   
      # Remove from store
      rm -r results/EVENT/PROD
      
      # Re-collect
      asimov monitor --once --event EVENT

2. If problem persists, re-run analysis

Store Read-Only Error
----------------------

**Symptom:**

.. code-block:: text

   PermissionError: Store is read-only

**Cause:**

Attempting to modify files in read-only store.

**Solution:**

This is expected behavior - stores are immutable. To update results:

1. Re-run the analysis
2. Results will be stored with a new timestamp
3. Old results remain unchanged

Performance Issues
==================

Asimov Commands Slow
---------------------

**Symptom:**

Commands take a long time to execute.

**Diagnosis:**

1. Check if querying large Condor pool:

   .. code-block:: bash
   
      time condor_q

2. Check ledger size:

   .. code-block:: bash
   
      wc -l .asimov/ledger.yml

**Solutions:**

1. Increase cache time:

   .. code-block:: ini
   
      [condor]
      cache_time = 1800  # 30 minutes

2. Use event-specific commands:

   .. code-block:: bash
   
      asimov report status --event EVENT

3. Consider database backend for large projects:

   .. code-block:: ini
   
      [ledger]
      engine = mongodb

Large Log Files
---------------

**Symptom:**

Log files consuming excessive disk space.

**Solution:**

1. Rotate logs:

   .. code-block:: bash
   
      cd logs
      for f in *.log; do
        mv "$f" "$f.$(date +%Y%m%d)"
        gzip "$f.$(date +%Y%m%d)"
      done

2. Configure log rotation in asimov configuration

3. Set higher logging level:

   .. code-block:: ini
   
      [logging]
      level = warning

Review and Collaboration Issues
================================

Cannot Update Review Status
----------------------------

**Symptom:**

.. code-block:: text

   PermissionError: Cannot update review

**Cause:**

Insufficient permissions for GitLab ledger or file permissions issue.

**Solution:**

1. Check GitLab permissions
2. Ensure you have write access to project
3. For file-based ledgers, check file permissions:

   .. code-block:: bash
   
      chmod 644 .asimov/ledger.yml

Review Comments Not Syncing
----------------------------

**Symptom:**

Reviews added via CLI don't appear in GitLab.

**Cause:**

GitLab integration not properly configured.

**Solution:**

Verify GitLab configuration:

.. code-block:: ini

   [ledger]
   engine = gitlab
   location = group/project

Migration and Compatibility Issues
===================================

Upgrading from v0.3 to v0.4+
-----------------------------

**Issue:**

"Production" terminology changed to "Analysis".

**Solution:**

Ledger format is backward compatible. The key ``productions:`` in YAML still works, but you can use the new terminology in documentation and discussions.

Upgrading from v0.6 to v0.7+
-----------------------------

**Issue:**

Some pipelines extracted to separate packages.

**Solution:**

Install pipeline-specific packages:

.. code-block:: bash

   pip install asimov-pycbc asimov-cogwheel

Ledger Version Mismatch
------------------------

**Symptom:**

.. code-block:: text

   Warning: Ledger format version mismatch

**Solution:**

1. Back up ledger:

   .. code-block:: bash
   
      cp .asimov/ledger.yml .asimov/ledger.yml.backup

2. Run migration (if available):

   .. code-block:: bash
   
      asimov migrate ledger

3. Or manually update according to changelog

Getting More Help
=================

Collecting Diagnostic Information
----------------------------------

When reporting issues, include:

1. **Asimov version:**

   .. code-block:: bash
   
      asimov --version

2. **Configuration:**

   .. code-block:: bash
   
      cat asimov.conf

3. **Ledger excerpt** (sanitize sensitive data):

   .. code-block:: bash
   
      head -n 50 .asimov/ledger.yml

4. **Recent logs:**

   .. code-block:: bash
   
      tail -n 100 logs/asimov.log

5. **Environment:**

   .. code-block:: bash
   
      pip list | grep -E "asimov|bilby|htcondor"

6. **Minimal reproducible example**

Enabling Debug Mode
-------------------

Get more detailed output:

.. code-block:: ini

   [logging]
   level = debug
   print level = debug

Or temporarily:

.. code-block:: bash

   asimov --verbose monitor --once

Common Error Messages Explained
================================

"Production X needs Production Y which is not finished"
-------------------------------------------------------

**Meaning:** Dependency not satisfied.

**Solution:** Wait for dependency to finish or remove dependency requirement.

"No matching scheduler found"
------------------------------

**Meaning:** Can't connect to HTCondor scheduler.

**Solution:** Check scheduler configuration and network access.

"PipelineException: Unknown pipeline 'X'"
------------------------------------------

**Meaning:** Pipeline not installed or not registered.

**Solution:** Install pipeline package or check entry point configuration.

"Failed to refresh SciToken"
-----------------------------

**Meaning:** Authentication token expired or renewal failed.

**Solution:** Get new token with ``htgettoken``.

See Also
========

- :ref:`faq`: Frequently asked questions
- :ref:`architecture`: System architecture
- :ref:`glossary`: Terminology definitions
- `GitHub Issues <https://github.com/etive-io/asimov/issues>`_: Report bugs and request features
