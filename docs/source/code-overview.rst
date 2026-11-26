========================
Code overview for asimov
========================

User interface
--------------

The ``asimov`` command is a :mod:`click` application defined in :mod:`asimov.olivaw`. Its subcommands
live in the :mod:`asimov.cli` package, with one module per command group (``project``, ``event``,
``application``, ``manage``, ``monitor``, ``report``, ``review``, ``ledger``, ``registry`` and so on).
The same operations are available over HTTP from :mod:`asimov.api`, and to AI assistants through
the MCP server in :mod:`asimov.mcp_server`; see :doc:`rest-api` and :doc:`mcp`.

Python modules
--------------

.. graphviz::

   digraph {
         "asimov" -> ".access";
         "asimov" -> ".accounting";
         "asimov" -> ".actions";
         "asimov" -> ".analysis";
         "asimov" -> ".analysis_types";
         "asimov" -> ".audit";
         "asimov" -> ".auth";
         "asimov" -> ".blueprints";
         "asimov" -> ".condor";
         "asimov" -> ".context";
         "asimov" -> ".custom_states";
         "asimov" -> ".database";
         "asimov" -> ".environment";
         "asimov" -> ".event";
         "asimov" -> ".example_labellers";
         "asimov" -> ".features";
         "asimov" -> ".git";
         "asimov" -> ".groups";
         "asimov" -> ".identity";
         "asimov" -> ".ini";
         "asimov" -> ".jobs";
         "asimov" -> ".labellers";
         "asimov" -> ".ledger";
         "asimov" -> ".ledger_migration";
         "asimov" -> ".locutus";
         "asimov" -> ".logging";
         "asimov" -> ".mattermost";
         "asimov" -> ".mcp_server";
         "asimov" -> ".membership";
         "asimov" -> ".models";
         "asimov" -> ".monitor_api";
         "asimov" -> ".monitor_context";
         "asimov" -> ".monitor_helpers";
         "asimov" -> ".monitor_states";
         "asimov" -> ".needs_check";
         "asimov" -> ".olivaw";
         "asimov" -> ".pipeline";
         "asimov" -> ".preview";
         "asimov" -> ".principal";
         "asimov" -> ".priors";
         "asimov" -> ".project";
         "asimov" -> ".provenance";
         "asimov" -> ".reading";
         "asimov" -> ".registry";
         "asimov" -> ".report_groups";
         "asimov" -> ".retention";
         "asimov" -> ".retry";
         "asimov" -> ".review";
         "asimov" -> ".rocrate";
         "asimov" -> ".scheduler";
         "asimov" -> ".scheduler_utils";
         "asimov" -> ".storage";
         "asimov" -> ".strategies";
         "asimov" -> ".strategies_builtin";
         "asimov" -> ".subject_types";
         "asimov" -> ".telemetry";
         "asimov" -> ".testing";
         "asimov" -> ".throttle";
         "asimov" -> ".utils";
         "asimov" -> ".vocabulary";
         "asimov" -> ".api";
         "asimov" -> ".cli";
         "asimov" -> ".pipelines";
         ".pipelines" -> ".pipelines.testing";
         ".pipelines" -> ".pipelines.command";
   }

Real analysis pipelines (bilby, RIFT, LALInference, BayesWave, PESummary) are no longer submodules of
``.pipeline``/``.pipelines`` — they're separate plugin packages registered via the ``asimov.pipelines``
entry-point group; see :doc:`pipelines`. Only the internal testing pipelines
(``.pipelines.testing``) ship in this package.

Workflow
--------
