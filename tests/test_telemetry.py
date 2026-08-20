"""Tests for asimov.telemetry."""

import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, Mock, patch

from asimov.telemetry import (
    TelemetryEvent,
    TelemetrySink,
    LocalJSONLSink,
    PrometheusPushgatewaySink,
    TELEMETRY_SINK_REGISTRY,
    register_telemetry_sink,
    discover_telemetry_sinks,
    emit_event,
)


class TestTelemetryEvent(unittest.TestCase):
    """Tests for the TelemetryEvent dataclass."""

    def test_to_json_round_trips(self):
        event = TelemetryEvent(
            timestamp="2026-08-20T10:00:00+00:00",
            event_type="status_change",
            event_name="GW150914",
            analysis_name="Prod0",
            rundir="/tmp/rundir",
            data={"from": "running", "to": "finished"},
        )
        parsed = json.loads(event.to_json())
        self.assertEqual(parsed["event_type"], "status_change")
        self.assertEqual(parsed["data"], {"from": "running", "to": "finished"})


class TestLocalJSONLSink(unittest.TestCase):
    """Tests for the always-on built-in sink."""

    def setUp(self):
        self.rundir = tempfile.mkdtemp()
        self.sink = LocalJSONLSink()

    def tearDown(self):
        shutil.rmtree(self.rundir, ignore_errors=True)

    def test_appends_jsonl(self):
        event = TelemetryEvent(
            timestamp="t1", event_type="status_change", event_name="GW150914",
            analysis_name="Prod0", rundir=self.rundir, data={"from": "ready", "to": "running"},
        )
        self.sink.emit(event)
        self.sink.emit(event)

        path = os.path.join(self.rundir, "telemetry.jsonl")
        with open(path) as f:
            lines = f.readlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(json.loads(lines[0])["event_type"], "status_change")

    def test_missing_rundir_is_created(self):
        nested = os.path.join(self.rundir, "not", "yet", "created")
        event = TelemetryEvent(
            timestamp="t1", event_type="status_change", event_name="GW150914",
            analysis_name="Prod0", rundir=nested, data={},
        )
        self.sink.emit(event)
        self.assertTrue(os.path.isfile(os.path.join(nested, "telemetry.jsonl")))

    def test_no_rundir_is_a_noop(self):
        event = TelemetryEvent(
            timestamp="t1", event_type="status_change", event_name="GW150914",
            analysis_name="Prod0", rundir="", data={},
        )
        # Should not raise, and should not create anything.
        self.sink.emit(event)


class TestPrometheusPushgatewaySink(unittest.TestCase):
    """Tests for the reference external sink."""

    def test_default_url_from_env(self):
        with patch.dict(os.environ, {"ASIMOV_PROMETHEUS_PUSHGATEWAY_URL": "http://example:9091"}):
            sink = PrometheusPushgatewaySink()
            self.assertEqual(sink.pushgateway_url, "http://example:9091")

    def test_payload_format(self):
        sink = PrometheusPushgatewaySink(pushgateway_url="http://localhost:9091")
        event = TelemetryEvent(
            timestamp="t1", event_type="status_change", event_name="GW150914",
            analysis_name="Prod0", rundir="", data={"to": "finished", "runtime": 12.5},
        )
        payload = sink._format_payload(event)
        self.assertTrue(payload.startswith("asimov_analysis_event{"))
        self.assertIn('event="GW150914"', payload)
        self.assertIn('analysis="Prod0"', payload)
        self.assertIn('event_type="status_change"', payload)
        self.assertIn('data_to="finished"', payload)
        self.assertIn('data_runtime="12.5"', payload)
        self.assertTrue(payload.rstrip("\n").endswith("} 1"))

    def test_label_sanitisation_escapes_quotes(self):
        sink = PrometheusPushgatewaySink()
        self.assertEqual(sink._sanitise_label('has "quotes"'), 'has \\"quotes\\"')

    @patch("asimov.telemetry.urllib.request.urlopen")
    def test_emit_posts_to_pushgateway(self, mock_urlopen):
        mock_urlopen.return_value.__enter__ = Mock(return_value=Mock(read=Mock()))
        mock_urlopen.return_value.__exit__ = Mock(return_value=False)
        sink = PrometheusPushgatewaySink(pushgateway_url="http://localhost:9091", job="asimov")
        event = TelemetryEvent(
            timestamp="t1", event_type="status_change", event_name="GW150914",
            analysis_name="Prod0", rundir="", data={},
        )
        sink.emit(event)
        called_request = mock_urlopen.call_args[0][0]
        self.assertEqual(called_request.full_url, "http://localhost:9091/metrics/job/asimov")


class TestTelemetrySinkRegistry(unittest.TestCase):
    """Tests for sink registration and entry-point discovery."""

    def setUp(self):
        TELEMETRY_SINK_REGISTRY.clear()

    def tearDown(self):
        TELEMETRY_SINK_REGISTRY.clear()

    def test_register_requires_telemetry_sink_instance(self):
        with self.assertRaises(TypeError):
            register_telemetry_sink(object())

    def test_register_and_overwrite(self):
        class DummySink(TelemetrySink):
            @property
            def name(self):
                return "dummy"

            def emit(self, event):
                pass

        register_telemetry_sink(DummySink())
        self.assertIn("dummy", TELEMETRY_SINK_REGISTRY)
        register_telemetry_sink(DummySink())  # should just warn, not raise
        self.assertIn("dummy", TELEMETRY_SINK_REGISTRY)

    @patch("asimov.telemetry.entry_points")
    def test_discover_telemetry_sinks(self, mock_entry_points):
        class TestSink(TelemetrySink):
            @property
            def name(self):
                return "test_sink"

            def emit(self, event):
                pass

        mock_ep = MagicMock()
        mock_ep.name = "test_sink"
        mock_ep.value = "test.module:TestSink"
        mock_ep.load.return_value = TestSink
        mock_entry_points.return_value = [mock_ep]

        discover_telemetry_sinks()

        self.assertIn("test_sink", TELEMETRY_SINK_REGISTRY)
        mock_entry_points.assert_called_once_with(group="asimov.hooks.telemetry")

    @patch("asimov.telemetry.entry_points")
    def test_discover_telemetry_sinks_error_handling(self, mock_entry_points):
        mock_ep = MagicMock()
        mock_ep.name = "broken_sink"
        mock_ep.load.side_effect = ImportError("no such module")
        mock_entry_points.return_value = [mock_ep]

        discover_telemetry_sinks()  # must not raise

        self.assertEqual(TELEMETRY_SINK_REGISTRY, {})

    @patch("asimov.telemetry.entry_points")
    def test_discover_telemetry_sinks_entry_points_call_fails(self, mock_entry_points):
        mock_entry_points.side_effect = RuntimeError("boom")
        discover_telemetry_sinks()  # must not raise
        self.assertEqual(TELEMETRY_SINK_REGISTRY, {})


class TestEmitEvent(unittest.TestCase):
    """Tests for emit_event()'s local-always-on + opt-in-fan-out behaviour."""

    def setUp(self):
        TELEMETRY_SINK_REGISTRY.clear()
        self.rundir = tempfile.mkdtemp()
        self.analysis = Mock()
        self.analysis.name = "Prod0"
        self.analysis.rundir = self.rundir
        self.analysis.event = Mock()
        self.analysis.event.name = "GW150914"

    def tearDown(self):
        TELEMETRY_SINK_REGISTRY.clear()
        shutil.rmtree(self.rundir, ignore_errors=True)

    def _read_local_events(self):
        path = os.path.join(self.rundir, "telemetry.jsonl")
        if not os.path.isfile(path):
            return []
        with open(path) as f:
            return [json.loads(line) for line in f if line.strip()]

    def test_always_writes_local_sink(self):
        emit_event(self.analysis, "status_change", **{"from": "ready", "to": "running"})
        events = self._read_local_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_type"], "status_change")
        self.assertEqual(events[0]["data"], {"from": "ready", "to": "running"})

    def test_no_ledger_only_writes_local(self):
        sink = Mock(spec=TelemetrySink)
        sink.name = "external"
        TELEMETRY_SINK_REGISTRY["external"] = sink

        emit_event(self.analysis, "status_change", ledger=None)

        sink.emit.assert_not_called()
        self.assertEqual(len(self._read_local_events()), 1)

    def test_fans_out_to_enabled_external_sink(self):
        sink = Mock(spec=TelemetrySink)
        sink.name = "external"
        TELEMETRY_SINK_REGISTRY["external"] = sink

        ledger = Mock()
        ledger.data = {"hooks": {"telemetry": {"external": {}}}}

        emit_event(self.analysis, "status_change", ledger=ledger)

        sink.emit.assert_called_once()

    def test_disabled_external_sink_is_not_called(self):
        sink = Mock(spec=TelemetrySink)
        sink.name = "external"
        TELEMETRY_SINK_REGISTRY["external"] = sink

        ledger = Mock()
        ledger.data = {"hooks": {"telemetry": {}}}

        emit_event(self.analysis, "status_change", ledger=ledger)

        sink.emit.assert_not_called()

    def test_broken_external_sink_does_not_raise(self):
        sink = Mock(spec=TelemetrySink)
        sink.name = "external"
        sink.emit.side_effect = RuntimeError("network down")
        TELEMETRY_SINK_REGISTRY["external"] = sink

        ledger = Mock()
        ledger.data = {"hooks": {"telemetry": {"external": {}}}}

        # Must not raise, and the local sink must still have written.
        emit_event(self.analysis, "status_change", ledger=ledger)
        self.assertEqual(len(self._read_local_events()), 1)

    def test_analysis_without_rundir_does_not_raise(self):
        analysis = Mock(spec=["name"])
        analysis.name = "Prod0"
        # accessing .rundir raises AttributeError due to spec=["name"]
        event = emit_event(analysis, "status_change")
        self.assertEqual(event.rundir, "")


if __name__ == "__main__":
    unittest.main()
