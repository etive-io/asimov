"""
Shared helpers for asimov's bundled testing pipelines
(:class:`~asimov.pipelines.testing.SimpleTestPipeline`,
:class:`~asimov.pipelines.testing.SubjectTestPipeline`,
:class:`~asimov.pipelines.testing.ProjectTestPipeline`).
"""

import configparser

from asimov import config as asimov_config

#: Fallback accounting tag used when neither the production's own
#: ``scheduler.accounting group`` metadata nor the project-wide
#: ``[condor] accounting`` setting supplies one. This is not a real LVK
#: accounting tag: on a real LIGO Data Grid pool it only submits
#: successfully because CI provisions a matching entry in that pool's
#: accounting/valid_tags map (see the ``setup-htcondor-ldg`` action).
FALLBACK_ACCOUNTING_GROUP = "test.test.test.test"


def accounting_submit_lines(production):
    """
    Build the extra HTCondor submit-file lines the bundled testing
    pipelines need in order to be accepted by a production-like LIGO Data
    Grid pool, rather than only the permissive disposable pool used by
    most CI.

    Real LDG pools reject any non-DAGMan job that doesn't carry a valid
    ``accounting_group`` (mapped to the ``LigoSearchTag`` classad and
    checked against a site accounting map) and an explicit
    ``request_disk`` (the pool's own default doesn't satisfy its "did you
    actually set this" submit requirement). ``getenv = True`` is also
    rejected outright once a pool sets ``SUBMIT_ALLOW_GETENV = False``,
    which is why callers should stop writing that line rather than adding
    these alongside it.

    Parameters
    ----------
    production : :class:`asimov.analysis.Analysis`
        The production whose ``meta`` may supply ``scheduler.accounting
        group``, ``scheduler.accounting group user``, ``scheduler.request
        disk`` and ``scheduler.request memory`` overrides.

    Returns
    -------
    list of str
        Submit-file lines (each already newline-terminated), ready to be
        written directly into a ``.sub`` file.
    """
    scheduler_meta = production.meta.get("scheduler", {})

    accounting_group = scheduler_meta.get("accounting group")
    if not accounting_group:
        try:
            accounting_group = asimov_config.get("condor", "accounting")
        except (configparser.NoOptionError, configparser.NoSectionError):
            accounting_group = FALLBACK_ACCOUNTING_GROUP

    accounting_group_user = scheduler_meta.get("accounting group user")
    if not accounting_group_user:
        try:
            accounting_group_user = asimov_config.get("condor", "user")
        except (configparser.NoOptionError, configparser.NoSectionError):
            accounting_group_user = None

    lines = [
        f"accounting_group = {accounting_group}\n",
        f"request_disk = {scheduler_meta.get('request disk', '100MB')}\n",
        f"request_memory = {scheduler_meta.get('request memory', '512MB')}\n",
    ]
    if accounting_group_user:
        lines.append(f"accounting_group_user = {accounting_group_user}\n")
    return lines
