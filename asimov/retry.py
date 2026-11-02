"""
What happens when an analysis fails: whether it is tried again, and what the
analyses which need it do if it never succeeds (#240).

Nothing here changes behaviour until a policy is set. A policy is a ``retry``
block on an analysis (so it can also be set for a whole pipeline, in the
``pipelines:`` defaults of the project) or the ``[retry]`` section of the
project's configuration, in that order of precedence::

    kind: analysis
    name: fit
    command: [gwaith_fit, --output, "{outputs.result}"]
    outputs:
      result: result.hdf
    retry:
      attempts: 4                  # in all, the first included
      deterministic attempts: 2    # for a command which ran and failed
      delay: 60                    # seconds before the next attempt ...
      backoff: 2                   # ... times this for each one after
    on failure: skip               # or halt (the default)

A failure is *transient* if it is plausibly not the analysis's fault (a held
job, a pre-empted or lost one) and *deterministic* if it ran and failed, which
trying again is unlikely to fix: it is tried again fewer times.

Each failure is recorded in the analysis's ``attempts`` (when, which kind, why)
and, after the last attempt, a ``retries_exhausted`` telemetry event is emitted.
What then happens to the analysis, and to what needs it, is ``on failure``:

``halt``
    The analysis is ``stuck`` and what needs it waits, as it always has.
``skip``
    The analysis is ``skipped``, which lets what needs it go ahead without its
    outputs. They are told, and it is recorded on them (``skipped inputs``).
"""
import datetime
import logging
from typing import Any, Dict, Iterable, List, Optional

from asimov import config

logger = logging.getLogger("asimov.retry")

TRANSIENT = "transient"
DETERMINISTIC = "deterministic"

#: What ``on_failure`` decides.
RETRY, STUCK, SKIPPED = "retry", "stuck", "skipped"

#: The status of an analysis which failed for good and was given up on.
SKIPPED_STATUS = "skipped"

#: The keys of the ``retry`` block, and what they are when it does not say.
DEFAULTS = {
    "attempts": 1,
    "deterministic attempts": 2,
    "delay": 0.0,
    "backoff": 1.0,
}

ON_FAILURE = ("halt", "skip")

#: In an analysis's metadata.
ATTEMPTS_KEY = "attempts"
RETRY_AFTER_KEY = "retry after"
SKIPPED_INPUTS_KEY = "skipped inputs"


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _stamp(moment: datetime.datetime) -> str:
    return moment.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(value: Any) -> Optional[datetime.datetime]:
    try:
        return datetime.datetime.strptime(str(value), "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=datetime.timezone.utc
        )
    except ValueError:
        return None


def _configured(key: str) -> Optional[str]:
    try:
        return config.get("retry", key.replace(" ", "_"))
    except Exception:
        try:
            return config.get("retry", key)
        except Exception:
            return None


def _number(value: Any, default, minimum, kind):
    try:
        number = kind(value)
    except (TypeError, ValueError):
        logger.warning(f"Retry setting {value!r} is not a number; using {default}")
        return default
    return number if number >= minimum else default


def policy(analysis) -> Dict[str, Any]:
    """
    The retry policy which applies to an analysis.

    Returns
    -------
    dict
        ``attempts``, ``deterministic attempts``, ``delay``, ``backoff`` and
        ``on failure``, and ``configured``, whether anything was set (if not,
        failures are handled and reported as they always have been).
    """
    block = (getattr(analysis, "meta", None) or {}).get("retry")
    if isinstance(block, bool):
        block = None
    if isinstance(block, int):
        block = {"attempts": block}
    if not isinstance(block, dict):
        block = {}

    def pick(key):
        if key in block:
            return block[key], True
        value = _configured(key)
        return (value, True) if value is not None else (DEFAULTS.get(key), False)

    result: Dict[str, Any] = {}
    configured = False
    for key, kind, minimum in (
        ("attempts", int, 1),
        ("deterministic attempts", int, 1),
        ("delay", float, 0.0),
        ("backoff", float, 1.0),
    ):
        value, given = pick(key)
        configured = configured or given
        result[key] = _number(value, DEFAULTS[key], minimum, kind)

    value = (getattr(analysis, "meta", None) or {}).get("on failure")
    value = value if value is not None else _configured("on failure")
    given = value is not None
    value = str(value).lower() if given else "halt"
    if value not in ON_FAILURE:
        logger.warning(f"'on failure: {value}' is not one of {', '.join(ON_FAILURE)}; using halt")
        value = "halt"
    result["on failure"] = value
    result["configured"] = configured or given
    return result


def classify(error: Optional[BaseException] = None, held: bool = False) -> str:
    """
    Whether a failure is plausibly transient.

    A held job is. An error which has ``transient = True`` is (a pipeline sets
    it on the exceptions which it knows are about the scheduler, not the
    analysis); anything else is taken to be deterministic.
    """
    if held or getattr(error, "transient", False):
        return TRANSIENT
    return DETERMINISTIC


def attempts_made(analysis) -> List[Dict[str, Any]]:
    """The failures which have been recorded for an analysis."""
    found = (getattr(analysis, "meta", None) or {}).get(ATTEMPTS_KEY)
    return found if isinstance(found, list) else []


def on_failure(analysis, kind: str, reason: str, now: Optional[datetime.datetime] = None) -> str:
    """
    Decide what happens to an analysis which has just failed, and make it so.

    The analysis's status and metadata are changed; saving it is up to the
    caller.

    Returns
    -------
    str
        ``"retry"`` (it is ``ready`` again, to start after its delay),
        ``"skipped"`` (it is ``skipped``) or ``"stuck"`` (it is ``stuck``).
    """
    now = now or _now()
    rules = policy(analysis)
    meta = analysis.meta

    if rules["configured"]:
        history = list(attempts_made(analysis))
        history.append(
            {"attempt": len(history) + 1, "failed": _stamp(now), "kind": kind, "reason": str(reason)}
        )
        meta[ATTEMPTS_KEY] = history
        failures = len(history)
    else:
        failures = 1

    limit = rules["attempts"]
    if kind == DETERMINISTIC:
        limit = min(limit, rules["deterministic attempts"])

    if failures < limit:
        delay = rules["delay"] * (rules["backoff"] ** (failures - 1))
        analysis.status = "ready"
        meta.pop(RETRY_AFTER_KEY, None)
        if delay > 0:
            meta[RETRY_AFTER_KEY] = _stamp(now + datetime.timedelta(seconds=delay))
        return RETRY

    meta.pop(RETRY_AFTER_KEY, None)
    if rules["on failure"] == "skip":
        analysis.status = SKIPPED_STATUS
        return SKIPPED
    analysis.status = "stuck"
    return STUCK


def describe(analysis, outcome: str) -> str:
    """One line saying what was decided, for the monitor to print."""
    rules = policy(analysis)
    failures = len(attempts_made(analysis))
    if outcome == RETRY:
        wait = analysis.meta.get(RETRY_AFTER_KEY)
        later = f", after {wait}" if wait else ""
        return f"will be tried again (attempt {failures + 1} of {rules['attempts']}{later})"
    if outcome == SKIPPED:
        return f"failed {failures} time(s) and is skipped; what needs it will go ahead without it"
    return "is stuck" + (f" after {failures} attempt(s)" if rules["configured"] else "")


def exhausted(analysis, ledger=None, reason: str = "") -> None:
    """Emit the telemetry event which says an analysis has used up its attempts."""
    try:
        from asimov.telemetry import emit_event

        emit_event(
            analysis,
            "retries_exhausted",
            ledger=ledger,
            attempts=len(attempts_made(analysis)),
            reason=str(reason),
            outcome=analysis.status,
        )
    except Exception as error:  # a hook which fails must never stop the monitor
        logger.warning(f"Could not emit the retries_exhausted event: {error}")


def deferred(analysis, now: Optional[datetime.datetime] = None) -> bool:
    """Whether an analysis is waiting out the delay before another attempt."""
    when = _parse((getattr(analysis, "meta", None) or {}).get(RETRY_AFTER_KEY))
    return when is not None and when > (now or _now())


def pending(analyses: Iterable, now: Optional[datetime.datetime] = None) -> int:
    """How many of the analyses are waiting to be tried again."""
    return sum(
        1
        for a in analyses
        if str(getattr(a, "status", "")).lower() == "ready" and deferred(a, now)
    )


def clear(analysis) -> None:
    """Forget the failures and any delay, as when an analysis is run again by hand."""
    for key in (ATTEMPTS_KEY, RETRY_AFTER_KEY, SKIPPED_INPUTS_KEY):
        analysis.meta.pop(key, None)


def is_skipped(analysis) -> bool:
    return str(getattr(analysis, "status", "")).lower() == SKIPPED_STATUS


def skipped_dependencies(analysis) -> List[str]:
    """The analyses this one needs which were skipped (qualified as ``needs`` is)."""
    try:
        return [
            analysis._qualified_name(dependency)
            for dependency in analysis.dependency_objects
            if is_skipped(dependency)
        ]
    except Exception:
        return []


def note_skipped_inputs(analysis) -> List[str]:
    """
    Record, in an analysis's metadata, which of the analyses it needs were
    skipped, so that what it used (and did not have) can be seen later.
    """
    skipped = skipped_dependencies(analysis)
    if skipped:
        analysis.meta[SKIPPED_INPUTS_KEY] = skipped
    else:
        analysis.meta.pop(SKIPPED_INPUTS_KEY, None)
    return skipped
