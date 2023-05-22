0.4.0
=====

We performed the review of asimov developments in preparation for O4.
The reviewed and signed-off version is tagged ``v0.4.0``. All review
checks were performed using the (non-static) ``igwn-py39-testing``
environment on RL8 machines; environment files have been recorded in the
`review
repository <https://git.ligo.org/pe/O4/asimov-review/-/tree/main/v0.4.x>`__.
For completion, it is noted that the setup included the manual
installation of ``asimov0.4.0rc4`` via pip.

The review covered the workflow generation for bayeswave, bilby and
pesummary.

Since its previous reviewed version (``v0.3.1``), significant changes to
the asimov workflow were implemented. The main change pertinent to this
review concerned reducing the dependence on gitlab. See `this
MR <https://git.ligo.org/asimov/asimov/-/merge_requests/45>`__ for all
details. Issues arising from those changes were addressed on the
`infrastructure-updates
branch <https://git.ligo.org/asimov/asimov/-/commits/infrastructure-updates>`__
as part of this review before merged upstream.

We note that neither bayeswave nor bilby are yet reviewed for O4 but in
order for asimov to work with the O4 sampler review,
``bilby_pipe version 1.0.7`` and ``bilby version 1.4.1`` were used for
this review. Due to unresolved condor file transfer issues, file
transfer for bilby jobs is disabled by default in this version of asimov
but can be enabled manually if desired.

We used the ``pesummary version 0.13.10`` for this review, as the
O4-reviewed version is not yet available. The default settings for
bayeswave, bilby and pesummary were not changed relative to the reviewed
version for O3 (``v0.3.1``).

We performed end-to-end runs for GW150914 on CIT and LHO as well as for
two non-vanilla cases: GW191109, which has a different minimum frequency
in one of the IFOs, and GW190924, which required deglitched data frames.
The latter did not run to completion due to a recurring `gwpy
issue <https://github.com/gwpy/gwpy/issues/1582>`__ but the asimov
workflow and configuration were set up correctly. We reviewed the setup,
workflow and outputs.

We also reviewed the .YAML files generated from the GitLab ledgers used
in O3. This included line-by-line review of the `conversion
script <https://git.ligo.org/asimov/data/-/snippets/157>`__ and review
of the specific files for: GW150914 (vanilla), GW190814 (different lower
frequency in L1), GW190924 (deglitched frame for LLO), GW190929
(different Virgo channel name), GW191109 (vanilla), and GW200115 (NSBH).
Notes for the review are available
`here <https://git.ligo.org/pe/O4/asimov-review/-/wikis/Review-of-YAML-generation>`__.

Support for dryrun was added and reviewed. dryrun tests and unit tests
were also added and reviewed. The documentation was reviewed to improve
clarity and internal coherence, and now suffices as a mini tutorial for
users.

We note that this review did not include testing of the OSG or a shared
account for running asimov analyses. These will be deferred to a later
version.

The RIFT integration in this version is not reviewed. More development
is necessary due to changes in RIFT for usage in O4. This is postponed
to the next reviewed version.

Required inputs from gracedb, pe configurator, calibration, detchar are
handled as in ``v0.3.1``. Changes will be required to integrate with O4
updates to those inputs once they become available (TBD).

0.3.0
=====

(25.4.2021) We have performed line-by-line reviews of the core functions of asimov, the PE automation pipeline for O3a final. The review covered the generation of the workflow, DAGs and command lines for BayesWave, bilby (via bilby_pipe) and RIFT. The handling of LALInference was not reviewed here.
The reviewed code packages and files are listed in the table below. All requested fixes were implemented on the review branch and are signed off, ready to be merged upstream into master (!5). Several new logger messages were added. All requests and fixes are documented in the relevant issues and MRs. Significant changes affect the

BayesWave settings for PSD generation
PE summary generation for results generation
Passing of a bilby prior file directly via the ini file instead of the CL
Removal of the ROQ priors as default
Passing of the minimum template frequency for RIFT

A new set of integration tests was added but we note that these do not allow for a complete end-to-end test of the asimov pipeline as the interfacing with gitlab was removed (on purpose); hence the git issue generation and gitlab interactions are not covered in these tests. They serve the purpose of demonstrating the correct generation of ini files and DAGs/CLs.
A complete end-to-end test with all fixes implemented on the review branch was performed on a test-trigger event (copy of GW190426l) with the BayesWave dependencies removed: pe/O3/o3b-pe-coordination#122 with the generated ini files ProdF{6,7,8} available at https://git.ligo.org/daniel-williams/S190426l/-/tree/master/C01_offline
The correct end-to-end workflow was produced.
The MR !5 will be merged upstream, with the reviewed version of asimov corresponding to version v0.3.0. This version of asimov should be used for all O3 production analysis.
In addition, we have also reviewed and signed off on default inputs specific to the O3a final analysis. While many of these defaults are also applicable to the O3b analysis, e.g. default calibration C01_offline, channel names etc., we recommend a thorough re-check of these settings specific for O3b.
For the future, we recommend further improvement in logging messages, the writing of a documentation and a workflow-chart. We also note that the spin magnitude priors are currently hard-coded for RIFT. Hence, we recommend implementing the BBH magnitudes as the default option but allowing for these to be populated via the prior metadata. Extensions to consistently handling BNS and NSBH as well as allowing for other schedulers will likely be required in the future.
