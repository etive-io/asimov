.. _provenance:

======================
Provenance & RO-Crate
======================

Asimov can assemble a standard, interoperable provenance record for any analysis, and package it as an `RO-Crate <https://www.researchobject.org/ro-crate/>`_ for archival, sharing, or citation.

Overview
--------

An analysis's ledger entry already records what it was configured with, and its :doc:`results store <storage>` manifest already records what it produced (with a hash and UUID for every output file). Since :doc:`environment capture <environment-reproducibility>` was added, asimov also records what software environment it ran in.

The provenance module brings these together into a single `W3C PROV-O <https://www.w3.org/TR/prov-o/>`_ graph, expressed as JSON-LD, describing:

- the analysis's **configuration**, as a ``prov:Entity``
- the **software environment** it ran in, if captured, as a ``prov:Entity``
- the analysis **run itself**, as a ``prov:Activity``
- the **software agents** involved (asimov, and the pipeline, including a best-effort pipeline version parsed from the captured ``pip freeze``), as ``prov:SoftwareAgent``
- every **output file**, as a ``prov:Entity`` carrying the hash/UUID already recorded in the results store

This is deliberately **export-only** for now. Re-importing a crate to recreate an analysis in a new project is tracked as a separate follow-up, since it touches the blueprint/apply path more invasively than a read-only export does.

Using the CLI
-------------

To see the provenance graph for an analysis:

.. code-block:: console

   $ asimov provenance GW150914_095045 prod0

This prints the PROV-O document as JSON. Use ``--output`` to write it to a file instead:

.. code-block:: console

   $ asimov provenance GW150914_095045 prod0 --output prod0-provenance.json

To export a full RO-Crate:

.. code-block:: console

   $ asimov package GW150914_095045 prod0
   RO-Crate written to GW150914_095045-prod0.crate

Use ``--output`` to choose the destination directory; it must not already exist.

What's in the crate
--------------------

.. code-block:: text

   GW150914_095045-prod0.crate/
   ├── ro-crate-metadata.json   # RO-Crate metadata, embedding the PROV-O graph
   ├── provenance.json          # the same PROV-O graph, standalone
   ├── config.json              # the analysis's configuration
   └── environment/
       ├── environment.json
       ├── environment-pip.txt
       └── environment-conda.txt   # if captured

**Output files (posterior samples, etc.) are not copied into the crate.** They're referenced by the hash and UUID already recorded in the results store's manifest, so crate size doesn't scale with the size of the analysis's outputs. A consumer with access to the same results store can resolve them from those references; the crate's metadata notes each one as externally stored rather than claiming a fetchable URL it can't actually serve.

Python API
----------

.. code-block:: python

   from asimov import current_ledger as ledger
   from asimov.provenance import build_provenance
   from asimov.rocrate import package_analysis

   # Just the provenance graph
   document = build_provenance(ledger, "GW150914_095045", "prod0")

   # A full RO-Crate export
   package_analysis(ledger, "GW150914_095045", "prod0", "prod0.crate")

.. autofunction:: asimov.provenance.build_provenance

.. autofunction:: asimov.rocrate.package_analysis

Design notes
------------

Ledger-backend generic
~~~~~~~~~~~~~~~~~~~~~~~

Asimov currently ships more than one :ref:`ledger <ledger>` backend (the YAML ledger, and the database ledger backed by SQLite/TinyDB/etc.), and the two disagree on some internal details. ``asimov.provenance`` and ``asimov.rocrate`` are built exclusively against the generic ``Ledger`` interface (``get_subject``/``get_event``, an analysis's ``.meta``/``.to_dict()``) and the ``Store``'s public methods, never against ``asimov.database``/``asimov.models`` or the YAML file directly. This means any current or future ``Ledger`` subclass works with no changes here.

No new dependencies
~~~~~~~~~~~~~~~~~~~~

PROV-O and RO-Crate are both JSON-LD with defined vocabularies, so asimov builds the JSON-LD directly rather than depending on a ``prov`` or ``rocrate`` package.

Limitations
-----------

- **Import isn't implemented yet.** A crate can be produced, but not (yet) fed back into ``asimov apply`` to recreate the analysis it describes.
- **No record of who applied a blueprint.** Asimov doesn't yet track *who* (or what) changed an analysis's configuration in the ledger, so the provenance graph can't attribute the configuration to a specific person or agent - only to the analysis itself. Once that's tracked, it can be added here as an additional agent/activity without changing the shape of anything already emitted.
- **Pipeline version is best-effort.** It's parsed by looking for the pipeline's own package name in the captured ``pip freeze`` output, which won't resolve it for every pipeline (e.g. one installed under a different package name, or run outside a Python environment asimov can inspect).

See Also
--------

- :doc:`Storage API <storage>`
- :doc:`Environment Reproducibility <environment-reproducibility>`
- :doc:`Analyses <analyses>`
- :doc:`The Ledger <ledger>`
