Building asimov's documentation
===============================

We have designed asimov's documentation to be built with the ``sphinx`` package using the ``sphinx-multiversion`` extension to allow multiple versions of documentation to be produced to provide backwards compatibility to older versions of the package.

Our CI system within the LIGO Scientific Collaboration will build documentation for the review and master branches as well as releases automatically, but if you're working on documentation on your own form you should follow the instructions below to preview the documentation.

Installing build requirements
-----------------------------

You can install the build requirements for the documentation using ``pip``::

  pip install -r docs-requirements.txt

Building docs for a single branch
---------------------------------

If you want to build the documentation just for your current working directory (i.e. a single branch of the repository) you can run::

  make html

In the ``docs`` directory of the repository to produce html formatted documentation.

Building the full documentation
-------------------------------

The full documentation for asimov includes documentation for older versions of the code, and can be built by running::

  make multi

In the ``docs`` directory of the repository.
Only html formatted documentation can be produced in this process.
