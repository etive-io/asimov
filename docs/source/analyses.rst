Analyses
========

Analyses are the fundamental operations which asimov conducts on data.

Asimov defintes three types of analysis, depending on the inputs of the analysis.

Simple analyses
  These analyses operate only on a single event, and will generally use a 
  very specific set of configuration settings.
  An example of a simple analysis is a bilby or RIFT parameter estimation analysis,
  as these only require access to the data for a single event.
  Before version 0.4 these were called `Productions`.

Event analyses
  These analyses can access the results of all of the simple analyses which have been 
  performed on a single event, or a subset of them.
  An example of an event analysis is the production of mixed posterior samples from multiple
  PE analyses.
  
Project analyses
  These are the most general type of analysis, and have access to the results of all analyses
  on all events, including event and simple analyses.
  This type of analysis is useful for defining a population analysis, for example.


An analysis is defined as a series of configuration variables in an asimov project's ledger, which are then used to configure analysis pipelines.


.. _states:
Analysis state
--------------

In order to track each of the jobs asimov monitors it employs a simple state machine on each production.
This state is tracked within :ref:`the production ledger<ledger>` for each production with the value of ``status``.

Under normal running conditions the sequence of these states is

::
   
   ready --> running --> finished --> processing --> uploaded 

A number of additional states are also possible which interupt the normal flow of the job through ``asimov``'s workflow.

+ ``ready`` : This job should be started automatically. This state must be applied manually. The job will then be started once its dependencies are met.
+ ``stopped`` : This run has been manually stopped; stop tracking it. Must be applied manually. 
+ ``stuck`` : A problem has been discovered with this run, and needs manual intervention.
+ ``uploaded`` : This event has been uploaded to the event repository.
+ ``restart`` : This job should be restarted by Olivaw. Must be applied manually.
+ ``finished`` : This job has finished running and the results are ready to be processed on the next bot check.
+ ``processing`` : The results of this job are currently being processed by ``PESummary``.
+ ``uploaded`` : This job has been uploaded to the data store.



