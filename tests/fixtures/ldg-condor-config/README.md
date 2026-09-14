# LDG-parity HTCondor pool configuration

This directory holds a **submission-policy** snapshot of the HTCondor pool
configuration used on the LIGO Data Grid (LDG), for use by the
`setup-htcondor-ldg` composite action and the
`.github/workflows/htcondor-ldg-parity-tests.yml` workflow. The goal is to
catch jobs that asimov (or a pipeline plugin) builds and that pass our
existing, deliberately permissive `htcondor/mini` CI pool, but that a real
LDG submit node would reject outright at `condor_submit` time.

## Provenance

Captured 2026-09-14 via `ssh cit` (`ldas-grid.ligo.caltech.edu`, the
Caltech LDG cluster), running HTCondor 25.13.2 on Rocky Linux 8.10. All of
`config.d/` is either verbatim or a trimmed copy of files under
`/etc/condor/config.d/` there, which are themselves Puppet-managed from the
`igwn-htcondor-config` module
(`git.ligo.org/computing/distributed/igwn-htcondor-config`) shared across
LDG sites -- not something specific to CIT. Every file says at the top
whether it's verbatim or trimmed, and why.

To refresh: `ssh cit` and re-read `/etc/condor/config.d/`
(`condor_config_val -dump` for the resolved macro values), diff against
what's here, and update. No special access beyond a normal LDG account is
needed to read these files.

## What's deliberately excluded

This mirrors submission-time *policy* (security requirements, accounting
enforcement, required job attributes), not CIT's specific deployment
topology or runtime resource-usage enforcement:

- Host/network-specific settings from the real `00-ldas` (NFS, dedicated
  MPI scheduler, checkpoint server, `UID_DOMAIN`, LAN interface ranges,
  preemption tuning) -- not applicable to a disposable single-container CI
  pool and would need site-specific values that don't exist there anyway.
- The `DISK_EXCEEDED`/`SYSTEM_PERIODIC_HOLD` runtime policies that hold an
  *already-running* job for exceeding what it requested -- out of scope for
  a suite that's checking "does this job get accepted", not "does this job
  behave once running".
- The real `valid_tags`/`valid_users` accounting maps (~65k entries each,
  including real users' LIGO identifiers) -- replaced with a small,
  fixture-only map in `accounting/` containing just the tags/users this
  test suite actually needs. `test.test.test.test` in particular is **not**
  a real LVK accounting tag; it exists only so this fixture pool has
  something to allow asimov's own bundled testing pipelines (which don't
  carry a real production tag) to submit successfully.

## What this does and doesn't prove

Passing this suite means asimov's generated jobs satisfy the same
*submission-time* policy a real LDG schedd enforces (accounting group and
request_disk present and valid, no blanket `getenv = True`, security
handshake succeeds). It does **not** exercise real IGWN authentication
infrastructure (SciTokens issuers, X.509/VOMS, the real accounting maps) --
FS authentication is used instead, which is sufficient within one
container but isn't itself proof that real credential flows work. See
`docs/source/pipelines/e2e-testing-ldg-parity.md` for the fuller writeup.
