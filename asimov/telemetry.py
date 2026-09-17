"""
Telemetry event system for asimov analyses.

This module provides structured, timestamped event emission during analysis
monitoring: status transitions, resource snapshots, and pipeline-defined
milestones. Every event is always recorded locally (no configuration
required, no third-party dependency) via a JSONL file alongside an
analysis's other run-directory files - see :mod:`asimov.pipeline`'s
``collect_logs`` for the sibling feature this mirrors.

Larger deployments can additionally forward the same events to an external
observability stack (Prometheus, Grafana, Loki, ...) by installing a plugin
package that registers a :class:`TelemetrySink` under the
``asimov.hooks.telemetry`` entry-point group and enabling it via ledger
configuration:

.. code-block:: yaml

    kind: config
    hooks:
      telemetry:
        prometheus:
          pushgateway_url: http://localhost:9091

No external plugin needs to be installed, and asimov core never depends on
one, for the local sink to work.
"""

import dataclasses
import datetime
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from typing import Dict

from asimov import logger, LOGGER_LEVEL

if sys.version_info < (3, 10):
    from importlib_metadata import entry_points
else:
    from importlib.metadata import entry_points

logger = logger.getChild("telemetry")
logger.setLevel(LOGGER_LEVEL)


@dataclasses.dataclass
class TelemetryEvent:
    """A single structured, timestamped telemetry event for an analysis."""

    timestamp: str
    event_type: str
    event_name: str
    analysis_name: str
    rundir: str
    data: dict

    def to_json(self):
        return json.dumps(dataclasses.asdict(self))


class TelemetrySink(ABC):
    """
    Abstract base class for telemetry sinks.

    A sink receives every :class:`TelemetryEvent` emitted via
    :func:`emit_event` and does something with it. :func:`emit_event`
    isolates each sink call in its own try/except so a broken or
    unreachable sink can never interrupt the monitor loop, but a
    well-behaved implementation shouldn't rely on that as its only error
    handling.

    Examples
    --------
    >>> class MySink(TelemetrySink):
    ...     @property
    ...     def name(self):
    ...         return "my_sink"
    ...     def emit(self, event):
    ...         print(event.to_json())
    """

    @property
    @abstractmethod
    def name(self):
        """Return the unique name of this sink (used for ledger opt-in)."""

    @abstractmethod
    def emit(self, event: TelemetryEvent):
        """Handle one telemetry event."""


class LocalJSONLSink(TelemetrySink):
    """
    The always-on, built-in sink.

    Appends one JSON line per event to ``telemetry.jsonl`` in the
    analysis's run directory. No configuration, no ledger writes, no
    third-party dependency: this is what makes telemetry work out of the
    box for a small, single-user project.
    """

    @property
    def name(self):
        return "local"

    def emit(self, event: TelemetryEvent):
        if not event.rundir:
            logger.debug(
                "No run directory for %s/%s; skipping local telemetry write",
                event.event_name, event.analysis_name,
            )
            return
        os.makedirs(event.rundir, exist_ok=True)
        path = os.path.join(event.rundir, "telemetry.jsonl")
        with open(path, "a") as f:
            f.write(event.to_json() + "\n")


class PrometheusPushgatewaySink(TelemetrySink):
    """
    Reference implementation of an external telemetry sink.

    Pushes each event to a `Prometheus Pushgateway
    <https://github.com/prometheus/pushgateway>`_ as a single gauge, using
    only the standard library (no ``prometheus_client`` dependency). This is
    deliberately thin - enough to prove the ``asimov.hooks.telemetry``
    contract works end-to-end against a real target, and to give anyone
    writing a fuller ``asimov-prometheus``/``asimov-grafana`` package
    something concrete to start from. Grafana then reads from Prometheus as
    a data source; asimov never needs to build its own dashboarding.

    Parameters
    ----------
    pushgateway_url : str, optional
        Base URL of the Pushgateway. Defaults to the
        ``ASIMOV_PROMETHEUS_PUSHGATEWAY_URL`` environment variable, or
        ``http://localhost:9091`` if that isn't set either.
    job : str, optional
        The Pushgateway "job" label events are grouped under.
    timeout : float, optional
        HTTP request timeout in seconds.
    """

    @property
    def name(self):
        return "prometheus"

    def __init__(self, pushgateway_url=None, job="asimov", timeout=5):
        self.pushgateway_url = pushgateway_url or os.environ.get(
            "ASIMOV_PROMETHEUS_PUSHGATEWAY_URL", "http://localhost:9091"
        )
        self.job = job
        self.timeout = timeout

    @staticmethod
    def _sanitise_label(value):
        return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")

    def _format_payload(self, event: TelemetryEvent):
        labels = {
            "event": event.event_name,
            "analysis": event.analysis_name,
            "event_type": event.event_type,
        }
        for key, value in event.data.items():
            if isinstance(value, (str, int, float, bool)):
                labels[f"data_{key}"] = value

        label_str = ",".join(
            f'{key}="{self._sanitise_label(value)}"' for key, value in labels.items()
        )
        return f"asimov_analysis_event{{{label_str}}} 1\n"

    def emit(self, event: TelemetryEvent):
        payload = self._format_payload(event).encode("utf-8")
        job_label = urllib.parse.quote(self.job, safe="")
        url = f"{self.pushgateway_url.rstrip('/')}/metrics/job/{job_label}"
        request = urllib.request.Request(url, data=payload, method="POST")
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            response.read()


# Registry of all discovered/registered external telemetry sinks. The
# always-on local sink is deliberately kept out of this registry - it is
# never opt-in, so it has no reason to be looked up by name.
TELEMETRY_SINK_REGISTRY: Dict[str, TelemetrySink] = {}

_local_sink = LocalJSONLSink()
_sinks_discovered = False


def register_telemetry_sink(sink):
    """
    Register an external telemetry sink instance.

    Parameters
    ----------
    sink : TelemetrySink
        The sink to register.
    """
    if not isinstance(sink, TelemetrySink):
        raise TypeError(
            f"Telemetry sink must be an instance of TelemetrySink, "
            f"got {type(sink).__name__}"
        )

    if sink.name in TELEMETRY_SINK_REGISTRY:
        logger.warning("Overwriting existing telemetry sink '%s'", sink.name)

    TELEMETRY_SINK_REGISTRY[sink.name] = sink
    logger.debug("Registered telemetry sink '%s'", sink.name)


def discover_telemetry_sinks():
    """
    Discover and register external telemetry sinks via entry points.

    Looks for entry points in the ``asimov.hooks.telemetry`` group. A
    broken or missing entry point never prevents the others from loading:
    discovery itself is guarded, and each entry point's ``.load()``/
    instantiation is guarded individually.
    """
    try:
        discovered = entry_points(group="asimov.hooks.telemetry")
        for entry in discovered:
            try:
                sink_obj = entry.load()
                sink = sink_obj() if isinstance(sink_obj, type) else sink_obj
                register_telemetry_sink(sink)
                logger.info(
                    "Discovered and registered telemetry sink '%s' from %s",
                    entry.name, entry.value,
                )
            except Exception as e:
                logger.warning("Failed to load telemetry sink '%s': %s", entry.name, e)
    except Exception as e:
        logger.debug("No telemetry sinks discovered: %s", e)


def initialize_telemetry_sinks():
    """
    Lazily discover external telemetry sinks, once per process.

    Discovery is deliberately not run at import time - an eager
    ``entry_points()`` call in a module's top-level code can fail the
    import itself if a broken plugin is installed. Call this once from the
    monitor loop entry point instead.
    """
    global _sinks_discovered
    if not _sinks_discovered:
        discover_telemetry_sinks()
        _sinks_discovered = True


def _enabled_sink_names(ledger):
    """Return the set of external sink names enabled via ledger config."""
    if ledger is None or not hasattr(ledger, "data"):
        return set()
    hooks = ledger.data.get("hooks", {})
    if not isinstance(hooks, dict):
        return set()
    telemetry_hooks = hooks.get("telemetry", {})
    if not isinstance(telemetry_hooks, dict):
        return set()
    return set(telemetry_hooks.keys())


def emit_event(analysis, event_type, ledger=None, **data):
    """
    Emit a telemetry event for *analysis*.

    Always writes the event via the built-in local JSONL sink. Additionally
    fans it out to every discovered external sink whose name is enabled in
    *ledger*'s ``hooks.telemetry`` configuration - each fan-out call is
    isolated in its own try/except so a broken or unreachable external sink
    can never interrupt the monitor loop.

    Parameters
    ----------
    analysis : Analysis
        The analysis this event concerns.
    event_type : str
        A short event category, e.g. ``"status_change"``,
        ``"resource_snapshot"``, or a pipeline-defined milestone name.
    ledger : Ledger, optional
        The project ledger, used to look up which external sinks are
        enabled. If omitted, only the local sink runs.
    **data
        Free-form event payload, e.g. ``from="running", to="finished"``.

    Returns
    -------
    TelemetryEvent
        The event that was emitted.
    """
    event_name = getattr(getattr(analysis, "event", None), "name", "") or ""
    try:
        rundir = analysis.rundir or ""
    except Exception:
        rundir = ""

    event = TelemetryEvent(
        timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        event_type=event_type,
        event_name=event_name,
        analysis_name=getattr(analysis, "name", ""),
        rundir=rundir,
        data=data,
    )

    try:
        _local_sink.emit(event)
    except Exception as e:
        logger.warning(
            "Local telemetry sink failed for %s/%s: %s",
            event.event_name, event.analysis_name, e,
        )

    for sink_name in _enabled_sink_names(ledger):
        sink = TELEMETRY_SINK_REGISTRY.get(sink_name)
        if sink is None:
            continue
        try:
            sink.emit(event)
        except Exception as e:
            logger.warning(
                "Telemetry sink '%s' failed for %s/%s: %s",
                sink_name, event.event_name, event.analysis_name, e,
            )

    return event
