# Telemetry → Prometheus → Grafana demo

Demonstrates asimov's [analysis telemetry](../../docs/source/hooks.rst) end to end: a couple of
real (if tiny) analyses run through the monitor loop with `asimov.telemetry.PrometheusPushgatewaySink`
enabled, pushing structured events to a Prometheus Pushgateway that Prometheus scrapes and Grafana
visualises.

Every event is *also* always written locally to `telemetry.jsonl` in each analysis's run
directory, with no configuration at all - that's the tier-1, "just works" story. This demo is
about the tier-2 story: forwarding the same events to a larger observability stack, which is
entirely opt-in and requires nothing from asimov core beyond installing/enabling a
`TelemetrySink` plugin.

## Prerequisites

- Docker (with `docker compose`)
- asimov installed (`pip install -e ../..` from a checkout, or just `pip install asimov` for a
  released version that includes this feature)

## Running it

```bash
# 1. Start Prometheus, the Pushgateway, and Grafana
docker compose up -d

# 2. Run a couple of real analyses with telemetry enabled
python run_demo.py
```

`run_demo.py` creates a throwaway asimov project (`demo-project/`, safe to delete and re-run),
configures the lightweight `LocalProcessScheduler` (so this needs nothing beyond Docker - no real
HTCondor or Slurm cluster), enables the `prometheus` telemetry sink via the same
`hooks.telemetry` ledger config documented in `docs/source/hooks.rst`, and drives two
`simpletestpipeline` analyses through `asimov apply` / `asimov manage build submit` /
`asimov monitor` - the real CLI, the same commands you'd type by hand.

## What to look at

- **Grafana**: http://localhost:3000/d/asimov-telemetry - a pre-provisioned dashboard (no login
  needed, anonymous access is enabled for this demo only) showing event counts and a raw event
  table.
- **Prometheus**: http://localhost:9090/graph?g0.expr=asimov_analysis_event - the raw metric,
  queryable directly.
- **Pushgateway**: http://localhost:9091 - what asimov actually pushed, before Prometheus scraped it.
- **Local telemetry**: `demo-project/working/GW150914_095045/*/telemetry.jsonl` - the always-on
  local record every analysis gets regardless of whether any external sink is configured.

## Known limitation: `resource_snapshot` events won't appear here

You'll see real `status_change` events land in Grafana, but not `resource_snapshot` (CPU/GPU/
runtime) ones, even though `LocalProcessScheduler.collect_history()` works correctly. This is a
limitation of `LocalProcessScheduler` itself, not of telemetry: its job tracking is an in-memory
dict on the scheduler instance, and `asimov manage build submit` / `asimov monitor` are separate
process invocations - each one gets a fresh, empty scheduler instance with no memory of jobs
another process submitted. `collect_history()` correctly reports "no history found" in that
situation.

This doesn't affect HTCondor or Slurm, which both have real persistent, cross-process-queryable
accounting systems (`condor_history`, `sacct`) - `resource_snapshot` telemetry works as expected
there. It's specific to the local scheduler, which this demo only uses because it needs no
external cluster to run.

## Cleaning up

```bash
docker compose down -v
rm -rf demo-project
```
