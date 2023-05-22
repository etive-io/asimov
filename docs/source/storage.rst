.. _storage:

=================
Storage Interface
=================

In order to ensure the veracity of results files asimov implements an interface for storing results files from pipelines.

Results are stored in directories called ``Stores`` and when checked in and out of the directory they are verified by comparing their MD5 hash to the hash which was recorded when the file was originally stored. Additional safety can be guaranteed by asserting that the file match an externally provided hash.

The storage interface for asimov was developed to replace the need for ``git`` to store large results files, while guaranteeing that the data contained within the files had not been edited or corrupted after production.
Files stored in a store are stored on the principle of write-once-read-only; when a file is stored it is intended to never be editted.
This follows the overall philosophy of the productions system of asimov, where an analysis should be created as a new production if changes must be made in order to ensure changes can be tracked efficiently.

Using Stores
------------

Stores can be accessed either through the python API in ``asimov.storage`` or via a command line interface, ``locutus``, which allows stores to be manipulated from a command line.

Python API
----------

The python API for asimov Stores can be found in the ``asimov.storage`` module.
This implements two classes, ``asimov.storage.Manifest`` and ``asimov.storage.Store``. The former handles the management of manifest files, which record the contents of the Stores, and the latter handles file system operations, and the process of storing files.


Creating a store
~~~~~~~~~~~~~~~~

A new Store can be created with the class method ``Store.create``. For example:

::

   from asimov.storage import Store

   new_store = Store.create("/tmp/test_store", "Test Store")

Stores must be assigned a root directory and a name when they are created.
This method then creates a new directory, ``.manifest`` in the store's root directory, which will handle the recording of files in the directory.

Storing a file
~~~~~~~~~~~~~~

A new file can be added to the store with the ``Store.add_file`` method.
This method assigns a uuid to the file, copies it into the store, using the uuid as its name, and makes the file read-only.
The hash of the file is then stored in the ``Store`` manifest.

Stores require that files be maintained in a hierarchy containing the event and production which the file relates to, however files intended to be shared between productions may be stored as a production named ``shared``. For example

::

   from asimov.storage import Store

   new_store = Store.create("/tmp/test_store", "Test Store")

   new_store.add_file("S000000xx", "Prod0", "test_results.xml")


The returned value of ``.add_file`` will be a dictionary which contains the uuid and the hash of the file, which can be stored elsewhere, for example in a production ledger.

Retrieving a file
~~~~~~~~~~~~~~~~~

Files should be retrieved from a store using the ``Store.fetch_file`` method, which looks up the file's uuid, and checks the hash of the returned file against the record in the manifest.
For example:

::

   from asimov.storage import Store
   old_store = Store("/tmp/test_store")

   old_store.fetch_file("S000000xx", "Prod0", "test_results.xml")

It is possible to pass a hash to this method, in which case the hash of the file is also checked against the provided hash. For example:

::

   from asimov.storage import Store
   old_store = Store("/tmp/test_store")

   old_store.fetch_file("S000000xx", "Prod0", "test_results.xml", hash="dfksdjfklsdjfklsdjdf")

If any of the hash checks for the file fail a ``asimov.storage.HashError`` exception will be raised rather than the file being returned.
   
Locutus
-------

Locutus is designed to provide a simple user interface to the storage API which can be used at the command line. When ``asimov`` is installed ``locutus`` will also be installed.

..
   .. click:: module:parser
      :prog: locutus
      :nested: full

Manifest files
--------------

Manifest files are used to track changes within the repository, and store details of all of the files which are stored in the store.

Manifest files are YAML 1.1 files which store details of files in a simple hierarchy:

::
   
   name: Store's name
   events:
      S000000xx:
         Prod0:
            test_file:
               hash: d41d8cd98f00b204e9800998ecf8427e
               uuid: f9f167bee8e3449aa0c68bf7f91e7b7a

A python object (``asimov.storage.Manifest``) is provided to make working with manifest files easier, although normally you shouldn't need to interact directly with the store's manifest.
