"""
Submission throttling.

Schedulers (HTCondor in particular) only cope with a limited number of
queued DAGs, so ``asimov manage submit`` must not blindly submit every ready
analysis in one pass. This module provides a small budget object which the
submit command consults before each submission.

The limits are *per project*. Three settings are read from the
``[scheduler]`` section of the configuration; each is optional and an unset
(or non-positive) value means "no limit", which preserves the historical
behaviour:

``max_queued``
    The maximum number of analyses from this project which may be active
    (see :data:`ACTIVE_STATES`) at once.
``max_submit_per_pass``
    The maximum number of submissions made by a single ``manage submit``
    invocation.
``submit_interval``
    Seconds to wait between consecutive submissions, to avoid hammering the
    scheduler.
"""

import time

from asimov import config, logger

ACTIVE_STATES = frozenset({"running", "processing"})
"""Analysis statuses which are treated as occupying a slot in the queue."""

_TRANSIENT_MARKERS = (
    "too many",
    "limit",
    "timed out",
    "timeout",
    "temporarily",
    "try again",
    "connection",
    "unable to connect",
    "schedd",
)


def _positive_int(value):
    """Parse ``value`` as a positive integer, returning None for "no limit"."""
    if value is None or value == "":
        return None
    try:
        value = int(value)
    except (TypeError, ValueError):
        logger.warning(f"Ignoring invalid submission limit {value!r}")
        return None
    return value if value > 0 else None


def _config_value(key, fallback=None):
    try:
        return config.get("scheduler", key, fallback=fallback)
    except Exception:  # missing section on a minimal/mocked config
        return fallback


def count_active(ledger):
    """
    Count the analyses in a project which are currently in the queue.

    This reads the ledger rather than the scheduler: it needs no scheduler
    access and is a conservative estimate (an analysis which has finished
    but hasn't been seen by ``asimov monitor`` yet still counts).

    Parameters
    ----------
    ledger : asimov.ledger.Ledger
        The project ledger.

    Returns
    -------
    int
        The number of active event analyses and project analyses.
    """
    active = 0
    for event in ledger.get_event(None):
        for production in event.productions:
            if str(production.status).lower() in ACTIVE_STATES:
                active += 1
    for analysis in ledger.project_analyses:
        if str(analysis.status).lower() in ACTIVE_STATES:
            active += 1
    return active


def is_transient_submit_error(error):
    """
    Decide whether a submission error looks like the scheduler being busy.

    Such errors mean "try again later" and must not mark an analysis as
    stuck. The exception and its causes are inspected, since pipelines
    typically wrap the scheduler's own error in a ``PipelineException``.
    """
    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        if isinstance(error, (TimeoutError, ConnectionError)):
            return True
        name = type(error).__name__
        if name in {"HTCondorIOError", "HTCondorInternalError"}:
            return True
        message = str(error).lower()
        if any(marker in message for marker in _TRANSIENT_MARKERS):
            return True
        error = error.__cause__ or error.__context__
    return False


class SubmissionThrottle:
    """
    A per-pass budget of submissions.

    Parameters
    ----------
    max_queued : int, optional
        Cap on active analyses in the project.
    max_per_pass : int, optional
        Cap on submissions made in this pass.
    interval : float, optional
        Seconds to sleep between submissions.
    active : int, optional
        The number of analyses already active when the pass starts.
    sleep, clock : callable, optional
        Replacements for :func:`time.sleep` and :func:`time.monotonic`
        (for testing).
    """

    def __init__(
        self,
        max_queued=None,
        max_per_pass=None,
        interval=0,
        active=0,
        sleep=time.sleep,
        clock=time.monotonic,
    ):
        self.max_queued = _positive_int(max_queued)
        self.max_per_pass = _positive_int(max_per_pass)
        self.interval = max(float(interval or 0), 0.0)
        self.active = active
        self.submitted = 0
        self.deferred = []
        self.halted = False
        self._sleep = sleep
        self._clock = clock
        self._last_submit = None

    @classmethod
    def from_config(cls, ledger=None, max_per_pass=None, **kwargs):
        """
        Build a throttle from the ``[scheduler]`` configuration.

        Parameters
        ----------
        ledger : asimov.ledger.Ledger, optional
            If given, and ``max_queued`` is set, the ledger is used to
            count the analyses which are already active.
        max_per_pass : int, optional
            Overrides ``max_submit_per_pass`` (e.g. from a CLI flag).
        """
        max_queued = _positive_int(_config_value("max_queued"))
        if max_per_pass is None:
            max_per_pass = _config_value("max_submit_per_pass")
        interval = _config_value("submit_interval", 0)
        try:
            interval = float(interval)
        except (TypeError, ValueError):
            interval = 0
        active = count_active(ledger) if (ledger is not None and max_queued) else 0
        return cls(
            max_queued=max_queued,
            max_per_pass=max_per_pass,
            interval=interval,
            active=active,
            **kwargs,
        )

    @property
    def limited(self):
        """True if any limit is in force."""
        return self.max_queued is not None or self.max_per_pass is not None

    @property
    def remaining(self):
        """The number of submissions still allowed, or None if unlimited."""
        budgets = []
        if self.max_queued is not None:
            budgets.append(self.max_queued - self.active - self.submitted)
        if self.max_per_pass is not None:
            budgets.append(self.max_per_pass - self.submitted)
        return max(min(budgets), 0) if budgets else None

    def can_submit(self):
        """Whether another submission fits in the budget."""
        if self.halted:
            return False
        remaining = self.remaining
        return remaining is None or remaining > 0

    def halt(self):
        """Stop further submissions this pass (the scheduler is busy)."""
        self.halted = True

    def defer(self, name):
        """Record that ``name`` was ready but left for a later pass."""
        self.deferred.append(name)

    def pace(self):
        """
        Wait until ``interval`` seconds have passed since the last submission.

        Call this immediately before submitting. Pacing is done here, not
        after a submission is recorded, so nothing sleeps between the
        scheduler accepting a DAG and the caller saving its job id.
        """
        if self.interval and self._last_submit is not None:
            wait = self.interval - (self._clock() - self._last_submit)
            if wait > 0:
                self._sleep(wait)

    def record_submission(self):
        """Count a successful submission."""
        self.submitted += 1
        self._last_submit = self._clock()

    def summary(self):
        """A one-line, human-readable summary of the pass."""
        text = f"Submitted {self.submitted}"
        if self.deferred:
            reason = "scheduler busy" if self.halted else "queue limit reached"
            text += f", deferred {len(self.deferred)} ({reason})"
        return text
