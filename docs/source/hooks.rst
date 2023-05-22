================
Extending Asimov
================

Asimov is designed to be easy to extend with your own code which can "hook" into the various operations it carries out.

Adding data
-----------

New data and settings can be applied to an asimov project using the `apply` interface.
The standard way of interacting with ``asimov apply`` is to apply a blueprint file written in YAML format.
However, other packages can also provide information directly to asimov.

The do this by using the ``applicator`` hook, which allows them to become discoverable by asimov.
The data can then be applied to the project from the application interface.

For example, by running

.. code-block:: console

		asimov apply -p cbcflow -e S191219a

Where the ``-p`` argument tells which pipeline asimov should query for the data.

``asimov.hooks.applicator``
~~~~~~~~~~~~~~~~~~~~~~~~~~~

To use the applicator end point you must advertise the class which implements it using the ``asimov.hooks.applicator`` endpoint.
The class implementing the applicator interface must have an ``__init__`` method which accepts an ``asimov.ledger.Ledger`` object as its only argument, and a ``run`` method which implements the logic of the hook.

The Monitor Loop
----------------

The monitor loop in asimov does all of the heavy lifting of checking that analyses are still running, and if they've finished, checking and storing the results.
You can hook in to this loop in order to modify its behaviour, and add functionality with your own code.

``asimov.hooks.postmonitor``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The post-monitor hook is run at the end of the monitor loop, and is an ideal place to put code which needs to collate or report on the status of an entire asimov project.

To use this hook you'll need to advertise your hook using the `asimov.hooks.postmonitor` endpoint, and add the name of your hook to the `hooks/postmonitor` list in the ledger file.
It is easiest to do this when you're setting-up your project by applying a file containing e.g.

.. code-block:: yaml

		kind: config
		hooks:
		  postmonitor:
		    - MyMonitorHook

		      
