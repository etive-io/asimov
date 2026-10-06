# LDG-parity end-to-end testing

This describes a second tier of end-to-end testing, alongside the existing
`htcondor/mini`-based CI (`testing-pipelines.yml`, `htcondor-tests.yml`):
running the same kind of real-`asimov`-CLI, real-HTCondor test, but against
a pool configured to enforce the same *submission-time policy* as a real
LIGO Data Grid (LDG) node, rather than the permissive `htcondor/mini`
defaults those workflows use.

## Why this exists

The existing HTCondor CI proves asimov (and its pipeline plugins) can
build a DAG and drive it through a disposable HTCondor pool end to end. It
doesn't prove that DAG would be *accepted* by a real LDG submit node,
because the disposable pool doesn't enforce what a real one does.
Concretely, as of a live-pool check against `ldas-grid.ligo.caltech.edu`
(CIT) on 2026-09-14:

- **`SUBMIT_ALLOW_GETENV = False`** -- a job submitted with `getenv = True`
  is rejected outright. `asimov`'s own bundled testing pipelines
  (`SimpleTestPipeline`/`SubjectTestPipeline`/`ProjectTestPipeline`) and the
  `asimov monitor start` cron job both did exactly this; both are fixed as
  part of this work (see below).
- **Accounting group / search-tag validation.** Any non-DAGMan job must
  carry a valid `accounting_group` (mapped internally to a `LigoSearchTag`
  classad and checked against a site accounting map) and an
  `accounting_group_user` matching what that submitting user is allowed to
  claim, or the submission is rejected.
- **An explicit `request_disk`.** The pool's own default doesn't satisfy
  its own "did you actually set this" submit requirement -- you have to
  set a value different from that default.
- **`FS, IDTOKENS` authentication, required encryption/integrity** (via
  HTCondor's `security:recommended` profile), rather than a legacy
  host-based trust model.

None of this needs a full IGWN credential stack to test against -- FS
(same-filesystem) authentication satisfies it within a single disposable
container, so the parity pool can run in CI the same way the existing
pools do, just with stricter config layered in.

## What's covered

`.github/workflows/htcondor-ldg-parity-tests.yml`, via the
`setup-htcondor-ldg` composite action, runs the same
Simple/Subject/ProjectTestPipeline + `asimov monitor start` flow as
`testing-pipelines.yml`, against the stricter pool. See
`tests/fixtures/ldg-condor-config/README.md` in the repository root for
exactly what config was captured, how, and what was deliberately left out
(site-specific topology, runtime resource-usage enforcement, and the real
~65k-entry accounting maps, which are replaced with a small fixture-only
map).

It's deliberately scoped to pipelines that live in this repo. The full
bilby/BayesWave/LALInference/PESummary chain that `htcondor-tests.yml`
exercises pulls in several separately-maintained plugin packages
(`asimov-bayeswave`, `asimov-pesummary`,
`github.com/transientlunatic/asimov-lalinference`, ...); running that
chain against the LDG-parity pool too is a natural next step, and matches
the trajectory of eventually carving this style of testing out into its
own review repository shared across those plugins, rather than
duplicating the pool setup in each one.

## Bugs this approach already found

Building this surfaced two real bugs, fixed alongside the new workflow
rather than just documented as known gaps:

1. `SimpleTestPipeline`/`SubjectTestPipeline`/`ProjectTestPipeline` wrote
   `getenv = True` into their submit files unconditionally, even though
   the jobs are self-contained bash scripts that don't need any inherited
   environment. Removed, and replaced with an explicit
   `accounting_group`/`accounting_group_user`/`request_disk` (see
   `asimov/pipelines/testing/_util.py`), so these pipelines are themselves
   submittable to a real LDG pool, not just a permissive one.
2. `asimov monitor start`'s HTCondor submission
   (`asimov/cli/monitor.py::_start_htcondor_monitor`) built its
   `submit_description` dict with an *unguarded*
   `config.get("asimov start", "accounting")` call -- if that section/key
   wasn't configured, this raised uncaught, before the function's own
   `try`/`except` fallback (a few lines further down, meant to warn and
   continue without accounting info) ever ran, making that fallback dead
   code. It also set `getenv = "true"` unconditionally, which a real LDG
   pool rejects outright. Neither was caught before because
   `asimov monitor start` wasn't exercised by any existing test. Both are
   fixed, and the getenv value is now an explicit, configurable variable
   list (`condor`/`monitor_getenv`) instead of a blanket `true`.
