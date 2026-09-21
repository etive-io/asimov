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

Adding review information
-------------------------

Asimov allows review information to be added to productions within the ledger, which can then be interpretted by scripts.
This could be used, for example, to ensure that only signed-off results are used for downstream analyses, or in data releases.

The review tools in asimov are managed by the ``asimov review`` family of commands (``asimov.review``), and the corresponding
data is stored in the ``review`` portion of the ledger for each production.

A review status is one of:

+ ``REJECTED``
+ ``APPROVED``
+ ``PREFERRED``
+ ``DEPRECATED``

Each analysis accumulates a list of timestamped review messages; the analysis's current review status is whichever of
these messages was added most recently with a status set. This history, not just the current status, is what's recorded
and shown.

Recording a review
~~~~~~~~~~~~~~~~~~~

.. code-block:: console

   $ asimov review add <event> <production> <status> --message "Looks good, matches previous run"

where ``<status>`` is one of ``rejected``, ``approved``, ``preferred``, or ``deprecated`` (case-insensitive).
The ``status`` argument and ``--message`` are both optional — you can attach a free-form message to an
analysis without changing its review status.

Checking review status
~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: console

   $ asimov review status <event> <production>
   $ asimov review audit <event>

``review status`` reports the current review status (and history) for a single analysis; ``review audit``
summarises review status across all analyses for an event.

Using review status as a dependency
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Review status can be used to filter which analyses a :doc:`subject analysis <../analyses>` depends on, so
that (for example) a PESummary job only combines analyses that have been approved:

.. code-block:: yaml

   kind: analysis
   name: ApprovedPESummary
   pipeline: pesummary
   analyses:
     - - review: approved
       - pipeline: bilby
   refreshable: true

