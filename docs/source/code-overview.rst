========================
Code overview for asimov
========================

User interface
--------------

Python modules
--------------

.. graphviz::

   digraph {
         "asimov" -> ".analysis";
	 "asimov" -> ".auth";
	 "asimov" -> ".blueprints";
	 "asimov" -> ".condor";
	 "asimov" -> ".custom_states";
	 "asimov" -> ".database";
	 "asimov" -> ".event";
	 "asimov" -> ".git";
	 "asimov" -> ".ini";
	 "asimov" -> ".ledger";
	 "asimov" -> ".locutus";
	 "asimov" -> ".logging";
	 "asimov" -> ".mattermost";
	 "asimov" -> ".monitor_api";
	 "asimov" -> ".monitor_context";
	 "asimov" -> ".monitor_helpers";
	 "asimov" -> ".monitor_states";
	 "asimov" -> ".olivaw";
	 "asimov" -> ".pipeline";
         "asimov" -> ".pipelines";
	 ".pipelines" -> ".pipelines.testing";
	 "asimov" -> ".priors";
	 "asimov" -> ".project";
	 "asimov" -> ".review";
	 "asimov" -> ".scheduler";
	 "asimov" -> ".scheduler_utils";
	 "asimov" -> ".storage";
	 "asimov" -> ".strategies";
 	 "asimov" -> ".testing";
         "asimov" -> ".utils";
            }

Real analysis pipelines (bilby, RIFT, LALInference, BayesWave, PESummary) are no longer submodules of
``.pipeline``/``.pipelines`` — they're separate plugin packages registered via the ``asimov.pipelines``
entry-point group; see :doc:`pipelines`. Only the internal testing pipelines
(``.pipelines.testing``) ship in this package.

Workflow
--------
