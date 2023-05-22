Reviewing results
=================


Accessing results
-----------------

Asimov collects and stores results from analyses securely.
These can be accessed through the ``asimov production`` command line interface.

If we have an event called ``GW150914`` which has a production called ``Prod1`` we can see a list of all its stored results by running

.. code-block:: console

		$ asimov production results GW150914 Prod0

and then we can get a file path for a specific results file, e.g. ``results.dat`` by running

.. code-block:: console

		$ asimov production results GW150914 Prod0 --file results.dat

PE Summary and post-processing
------------------------------




Adding review information
-------------------------

Asimov allows review information to be added to productions within the ledger, which can then be interpretted by scripts.
This could be used, for example, to ensure that only signed-off results are used for downstream analyses, or in data releases.

The review tools in asimov are managed by the ``asimov review`` family of commands, and the corresponding data is stored in the ``review`` portion of the ledger for each production.


