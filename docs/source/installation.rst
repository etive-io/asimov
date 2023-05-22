.. _installation-guide:

Installing Asimov
=================

There are lots of ways of installing ``asimov``, and the best way of getting access to it depends both on your local setup, and on whether you have access to IGWN computing resources.
``asimov`` was initially designed for use in analysing gravitational wave detector data, and so some of the information in this manual will be aimed directly at users from that background.

Installation using ``pip``
--------------------------

The simplest method for installing ``asimov`` is to use the latest released version from ``pypi``, the python package index.
We always recommend installing in a virtual environment.

To create a new virtual environment you can run

.. code-block:: console

		$ mkdir environment
		$ python -m venv environment

You can then "activate" the environment by running

.. code-block:: console

		$ source environment/bin/activate

You'll need to run this activation step each time you open a new terminal when you want to use ``asimov``.

You can then install asimov using ``pip``.

.. code-block:: console
   
		$ pip install asimov


Installation using ``conda``
----------------------------

It is also possible to install asimov in a conda environment from conda forge.
You can do this by ensuring that your conda environment is activated, and then running

.. code-block:: console

		$ conda install -c conda-forge ligo-asimov

Installation from source
------------------------

If you want to run unreleased code you can do this by installing directly from the asimov git repository.

The quickest way to do this is to run

.. code-block:: console

		$ pip install git+https://git.ligo.org/asimov/asimov.git

You should use the package with care if installing from source; while the master branch should represent stable code, it may contain new or undocumented features, or behave unexpectedly.


Installation for development
----------------------------

If you want to develop code in the ``asimov`` repository then it can be helpful to install in development mode.

First clone a copy of the ``asimov`` repository, for example by running

.. code-block:: console

		$ git clone https://git.ligo.org/asimov/asimov.git

Then you can install this repository into your current virtual environment by running

.. code-block:: console

		$ cd asimov
		$ pip install -e .


Using an IGWN Environment
-------------------------

If you have access to IGWN compute facilities, such as the LIGO Data Grid, then you can use an IGWN environment to run asimov.
Asimov is pre-installed in both testing and deployed environments, so you should be able to access it on the cluster simply by activating one of these environments.

For example,

.. code-block:: console

		$ conda activate igwn-py39

