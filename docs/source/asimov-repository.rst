The asimov repository and review process
========================================

Each subject (event) that asimov manages is associated with a git repository (the ``repository``
value in its ledger entry) where analysis configuration files, priors, and other analysis products
are committed. Asimov itself only records where this repository lives and clones/pulls it as needed;
it does not manage the repository's contents beyond that.

Review status
-------------

Individual analyses can be signed off through asimov's review system (``asimov.review``), independent
of the pipeline that produced them. A review status is one of:

+ ``REJECTED``
+ ``APPROVED``
+ ``PREFERRED``
+ ``DEPRECATED``

Each analysis accumulates a list of timestamped review messages (``ReviewMessage``); the analysis's
current review status is whichever of these messages was added most recently with a status set. This
history, not just the current status, is what's recorded and shown.

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

Review status can be used to filter which analyses a :doc:`subject analysis <analyses>` depends on, so
that (for example) a PESummary job only combines analyses that have been approved:

.. code-block:: yaml

   kind: analysis
   name: ApprovedPESummary
   pipeline: pesummary
   analyses:
     - - review: approved
       - pipeline: bilby
   refreshable: true
