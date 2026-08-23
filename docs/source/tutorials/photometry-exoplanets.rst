Scoping a stellar photometry / exoplanet workflow
===================================================

.. note::
   This document scopes a new science workflow for Asimov: automated
   analysis of stellar photometry (for example *Kepler*, *K2*, or *TESS*
   light curves) in search of transiting exoplanets. It is a design
   proposal, not yet an implementation — it exists to record the plan and
   the decisions made before code is written.

Why this is a good fit for Asimov
----------------------------------

Asimov's value comes from three things: a pipeline-agnostic interface, a
version-controlled ledger of what has and hasn't been run, and automated
job submission/monitoring/recovery on HTC clusters. A single transit
search on one light curve takes seconds and doesn't need any of that. The
payoff appears at *catalog scale*: re-running a detrending + transit
search pipeline over thousands of Kepler Objects of Interest (KOIs), or
running an injection-recovery completeness study across a whole field, is
exactly the "hundreds of coordinated jobs, tracked and reproducible"
problem Asimov already solves for gravitational-wave parameter
estimation. The design below is deliberately built around that scale-out
case, while still working for a single named target.

Mapping onto Asimov's existing model
-------------------------------------

Asimov's core abstractions are already domain-neutral (see
:doc:`../blueprints`), so nothing needs to change in ``asimov`` core to
support this — a new *pipeline plugin* is enough.

.. list-table::
   :header-rows: 1

   * - Asimov concept
     - Photometry/exoplanet meaning
   * - ``subject`` (blueprint ``kind: subject``)
     - A target star, keyed by its catalog identifier (KIC/EPIC/TIC number).
   * - ``SimpleAnalysis``
     - One pipeline run on one target: download light curve → detrend →
       transit search → vet.
   * - ``ProjectAnalysis``
     - A catalog-scale campaign: the same analysis applied across a list
       of targets (a KOI/TOI catalog, an injection-recovery study, a
       full-field re-analysis), with Asimov handling submission,
       monitoring, and result collation across all of them.
   * - ``Pipeline`` plugin
     - A new companion package, registered via the ``asimov.pipelines``
       entry point, exactly as ``bilby``/``RIFT``/``pyRing`` are today.

Package layout
---------------

Following the pattern used by every real analysis pipeline in the Asimov
ecosystem (``bilby``, ``RIFT``, ``pyRing``, ``asimov-gracedb``), this
should ship as its own installable package — provisionally named
``asimov-photometry`` — rather than living inside ``asimov`` core. Core
stays pipeline-agnostic; the science-specific code (light curve I/O,
detrending, box least squares) lives with the domain, gets its own
release cycle, and can depend on ``lightkurve``/``astropy`` without
imposing that on every Asimov user.

::

   asimov-photometry/
     pyproject.toml            # entry points: asimov.pipelines, asimov.hooks.filesource
     asimov_photometry/
       __init__.py
       pipeline.py              # BLSTransitSearch(Pipeline)
       filesource.py            # MAST/Kepler filesource hook
       config_template.toml     # liquid-templated pipeline config
       report.py                # per-target + per-catalog reporting

The ``asimov/pipelines/testing`` module in this repo (``SimpleTestPipeline``,
``ProjectTestPipeline``) is the right template to copy from — it already
documents the minimum set of methods a new pipeline needs to implement,
and end-to-end tests can run against it without a real backend.

Data ingestion: a ``filesource`` hook
---------------------------------------

Asimov already has a precedent for "fetch data from an external archive
and hand asimov a local path": the ``asimov.hooks.filesource`` entry
point used by ``asimov-gracedb`` (see ``Event.get_gracedb`` in
``asimov/event.py``). A ``mast``/``kepler`` filesource hook would follow
the same contract — a class taking the global ``config`` in its
constructor and exposing a ``fetch(target_id, product)`` method that
returns the requested file's bytes (in this case, a light curve FITS file
pulled via ``lightkurve``/``astroquery.mast``). This keeps "how do I get
the data" decoupled from "what do I do with the data", the same
separation GW analyses already use for GWOSC frames.

Pipeline stages (MVP)
-----------------------

The agreed MVP scope is a single-target pipeline using **Box Least
Squares** (``astropy.timeseries.BoxLeastSquares``) — no extra heavy
dependency, and a solid, well-understood baseline before anything more
sensitive (e.g. ``transitleastsquares``) is considered.

1. **Ingest** — fetch the light curve for the subject's catalog ID via
   the filesource hook; cache the FITS file under the analysis run
   directory.
2. **Detrend** — remove stellar variability and instrumental trends
   (``lightkurve``'s ``flatten()``/spline detrending) to leave a
   transit-searchable residual flux series.
3. **Transit search** — run BLS over a period grid, record the best
   period, epoch, duration, depth, and signal detection efficiency (SDE)
   or equivalent significance statistic.
4. **Vet** — cheap, deterministic checks on the top candidate(s): odd/even
   transit depth consistency, a secondary-eclipse search at phase 0.5,
   and (where available) a per-quarter/sector consistency check. This is
   intentionally *not* a full false-positive vetting suite (e.g.
   centroid/pixel-level diagnostics, which need target pixel files) —
   that's future work, not MVP.
5. **Report** — a small machine-readable results file (period, depth,
   duration, SDE, vetting flags) plus a folded-light-curve plot, in the
   same spirit as ``collect_assets`` for GW pipelines.

Pipeline interface sketch
----------------------------

.. code-block:: python

   from asimov.pipeline import Pipeline

   class BLSTransitSearch(Pipeline):
       name = "photometry-bls"

       def build_dag(self, dryrun=False):
           # Write a small executable script (or, for catalog campaigns,
           # one row of an HTCondor/Slurm DAG per subject) that runs the
           # ingest -> detrend -> BLS -> vet -> report steps and writes
           # results.json into self.production.rundir.
           ...

       def submit_dag(self, dryrun=False):
           # Hand the built job(s) to the configured scheduler
           # (asimov.scheduler.Slurm or HTCondor), exactly as other
           # pipelines do.
           ...

       def detect_completion(self):
           return os.path.exists(
               os.path.join(self.production.rundir, "results.json")
           )

       def collect_assets(self):
           return {
               "results": os.path.join(self.production.rundir, "results.json"),
               "folded_lightcurve": os.path.join(
                   self.production.rundir, "folded_lightcurve.png"
               ),
           }

Each stage is deliberately fast and deterministic, so for a *single*
target the whole thing can reasonably run in one job rather than as a
multi-node DAG — the DAG/scheduler machinery only starts mattering once
``ProjectAnalysis`` fans this out over a catalog.

Blueprint sketch
-------------------

Single target (MVP):

.. code-block:: yaml

   kind: subject
   name: KIC-11446443
   photometry:
     mission: Kepler
     catalog id: 11446443
   ---
   kind: analysis
   name: transit-search
   pipeline: photometry-bls
   comment: BLS transit search on Kepler-10

Catalog-scale campaign (Phase 3), as a ``ProjectAnalysis``:

.. code-block:: yaml

   kind: project_analysis
   name: koi-catalog-rerun
   pipeline: photometry-bls
   subjects: koi-active-list.txt
   comment: Re-run BLS across all active KOIs with an updated detrending window

Config templating
--------------------

Following the ``liquid``-templated config pattern used by every other
pipeline (see :doc:`adding-a-pipeline`), a minimal
``config_template.toml`` would look like:

.. code-block:: toml

   [target]
   catalog_id = {{ production.subject.meta['photometry']['catalog id'] }}
   mission = "{{ production.subject.meta['photometry']['mission'] }}"

   [detrend]
   window_length = {{ production.meta['detrend']['window length'] | default: 0.5 }}

   [bls]
   period_min = {{ production.meta['bls']['period min'] | default: 0.5 }}
   period_max = {{ production.meta['bls']['period max'] | default: 20.0 }}
   duration_grid = {{ production.meta['bls']['duration grid'] | default: "[0.05, 0.10, 0.20]" }}

Phased roadmap
------------------

- **Phase 0 — Scaffold.** Create the ``asimov-photometry`` package,
  register the ``asimov.pipelines`` and ``asimov.hooks.filesource`` entry
  points, and wire up a dummy pipeline (copying the
  ``asimov/pipelines/testing`` pattern) so the plumbing can be tested
  end-to-end before any real astronomy code exists.
- **Phase 1 — Single-target MVP.** Real MAST/``lightkurve`` ingestion,
  detrending, BLS transit search, ``collect_assets``/``detect_completion``,
  a worked blueprint, and unit tests against synthetic injected-transit
  light curves (no network access required in CI).
- **Phase 2 — Vetting & reporting.** Odd/even and secondary-eclipse
  checks, folded-light-curve plots, a human-readable per-target report.
- **Phase 3 — Catalog-scale campaigns.** ``ProjectAnalysis`` support for
  running the pipeline across a catalog of targets, HTCondor/Slurm DAG
  generation for batch submission, and an aggregate report/dashboard
  across the whole campaign (candidate table, completeness plots for
  injection-recovery runs).
- **Phase 4 — Stretch goals.** Pluggable transit-search backend (e.g.
  ``transitleastsquares`` as an alternative to BLS), multi-mission
  support (TESS, K2), pixel-level vetting using target pixel files.

Open questions / risks
--------------------------

- **Network access from cluster nodes.** Whether HTCondor/Slurm worker
  nodes used for a campaign can reach MAST directly, or whether light
  curves need pre-staging (download on a submit node, then distribute) —
  the same problem GW pipelines solve for GWOSC frame files.
- **Storage of downloaded light curves.** FITS light curve files are
  small individually but add up across a large catalog; these should not
  go into the git-backed ledger repository the way small config files do,
  and will need the same "assets, not ledger content" treatment GW
  results already get.
- **Depth of vetting required.** The MVP's odd/even + secondary-eclipse
  checks are not a substitute for full centroid/pixel-level vetting;
  scope for that should be agreed before Phase 2 rather than assumed.

Testing strategy
--------------------

Mirror the approach in ``asimov/pipelines/testing``: unit tests build a
pipeline instance against synthetic light curves with a known injected
transit (fixed period/depth/duration), assert BLS recovers it within
tolerance, and exercise ``build_dag``/``detect_completion``/
``collect_assets`` without needing network access or a real scheduler.
End-to-end tests can then use a small, fixed real target (e.g. Kepler-10,
which has well-characterised known transits) to validate against ground
truth.

Next steps
--------------

1. Confirm this scope (package name, MVP boundaries, and the open
   questions above) before writing implementation code.
2. Scaffold the ``asimov-photometry`` package (Phase 0).
3. Implement the Phase 1 MVP against a small set of known Kepler targets.
