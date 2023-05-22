.. _project-guide:

===============
Asimov Projects
===============

Asimov manages sets of analyses by collecting them into projects.
Projects collect setup and configuration information about analyses, results from analyses, and all of the auxilliary files and information required to run and monitor those analyses.

Creating a new project
----------------------

When you create a new project, asimov will generate some new directories and files to allow it to organise and manage your work.

The easiest way to do this is by running

.. code-block:: console

		$ asimov init "Test project"

Which will convert the current directory into an asimov project directory, including producing the ledger file, and creating directories for results storage.

It is also possible to customise the project in a number of ways, including specifying alternative locations for the various subdirectories (though you should do this with care).

.. todo:: Add further information about customising project creation

Adding default analysis settings
--------------------------------

.. todo:: Add documentation about default analysis settings.
	  
The structure of a project
--------------------------

When you run ``asimov init`` in a directory it will create a few files and directories which allow it to track information about the project and all of the analyses which you'll add to it.

``ledger.yml``
    This file is the *ledger*, which is a database of all of the analyses in the project.

``asimov.conf``
    This file is the configuration file for asimov, and contains information about the project itself and the computing environment.

Asimov will create a number of new directories when it's creating a project.

``results``
    This directory will contain an Asimov results store, and will be the location that results files are automatically copied to once Asimov has determined that the job has finished.
    Files stored here will be hashed and stored as read-only, to help prevent results files from becoming corrupted or over-written accidentally.

``working``
    This directory will be used to store run directories for each analysis job (directories where the analysis is run) and can contain temporary files and logs related to the analysis.

``checkouts``
    Asimov stores the files used to configure pipelines in git repositories, and these are stored in the ``checkouts`` directory.
    By default these repositories are local to your own machine, and the current asimov project.

``pages``
    This directory is used to store html-format output from both asimov and the pipelines.

Customising a project
---------------------

Sometimes it can be useful to change the default settings for a project.
For example, you may want to move the ``pages`` directory to be located somewhere that is served by a web-server.
The configuration of the project is handled by the ``asimov.conf`` file, and by editing the configuration values in this file you can change asimov's default behaviour.

You can also set the locations of these directories when creating the project using ``asimov init``.

``results``
    The results directory can be specified when creating the project using the ``--results`` option on the ``asimov init`` command, for example

    .. code-block:: console

		    $ asimov init --results /home/albert.einstein/results

    if your results directory shoould be located in ``/home/albert.einstein/results``, for example.
    It can also be changed in the configuration file, ``asimov.conf`` in the root directory of the project by editing the value of ``[storage]/results_store``

    .. code-block:: ini

		    [storage]
		    results_store = /home/albert.einstein/results

    .. warning:: Results stores

		 In order to prevent results becoming corrupted or overwritten, asimov enforces a specific layout on the results store directory, and it will expect this to be present. If you change the location of the results store after creating the project be sure to either copy the results directory from the current project to the new location first, or ensure that the new location is set up as a results store.
		 For more information about doing this, see the :ref:`storage` guide.

    
Cloning projects
----------------

If you need to extend another analysis it might make sense to be able to get access to the settings which were used for its various events and analyses.

To do this asimov allows you to *clone* an existing project by running

.. code-block:: console

		$ asimov clone path/to/project

This will give you a local copy of most of that project, including results, but not the working directories and temporary files from the analyses.
