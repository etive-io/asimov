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

Telemetry
---------

Every analysis automatically gets a structured, timestamped event log - status changes and
resource-usage snapshots are recorded for you, with no configuration required, in a
``telemetry.jsonl`` file in the analysis's run directory. This local record is also available
through the REST API at ``GET /api/v1/analyses/<event>/<analysis>/telemetry``.

For larger deployments you can additionally forward the same events to an external
observability stack (Prometheus, Grafana, Loki, ...) without asimov itself depending on one.

``asimov.hooks.telemetry``
~~~~~~~~~~~~~~~~~~~~~~~~~~~

To advertise an external telemetry sink, implement ``asimov.telemetry.TelemetrySink`` - a
``name`` property and an ``emit(event)`` method that receives an
``asimov.telemetry.TelemetryEvent`` - and register it under the ``asimov.hooks.telemetry``
entry point:

.. code-block:: toml

		[project.entry-points."asimov.hooks.telemetry"]
		my_sink = "my_package.telemetry:MySink"

As with ``postmonitor``, a discovered sink only runs once its name is added to your project's
``hooks/telemetry`` configuration:

.. code-block:: yaml

		kind: config
		hooks:
		  telemetry:
		    my_sink:
		      some_config_key: some_value

asimov ships a reference implementation, ``asimov.telemetry.PrometheusPushgatewaySink``
(entry-point name ``prometheus``), which pushes events to a `Prometheus Pushgateway
<https://github.com/prometheus/pushgateway>`_ - Grafana can then read from Prometheus as a
data source without asimov needing any dashboard code of its own. A pipeline can also emit its
own custom milestones by calling ``asimov.telemetry.emit_event(analysis, "my_milestone",
**data)`` directly, for example from a ``before_submit``/``after_completion`` hook.
