"""
Tests for the audit trail (#143).
"""

import datetime
import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from click.testing import CliRunner

from asimov import telemetry
from asimov.audit import (
    PROJECT,
    AuditRecord,
    append_audit,
    filter_records,
    new_record,
    prov_document,
    timestamp_for,
)
from asimov.cli import audit as audit_cli
from asimov.cli.application import apply_page
from asimov.cli.project import make_project
from asimov.context import ProjectContext
from asimov.ledger import DatabaseLedger
from asimov.principal import Principal, acting_as

DATA = os.path.join(os.path.dirname(__file__), "test_data")
BLUEPRINTS = os.path.join(os.path.dirname(__file__), "test_blueprints")
ENGINES = ("yamlfile", "sqlite")


def record(target="S1/a", kind="analysis", who=None, **kwargs):
    with acting_as(who or Principal.person("alice")):
        return new_record("apply", kind, target, content={"name": "a"}, **kwargs)


class TestRecord(unittest.TestCase):
    def test_a_record_snapshots_the_principal(self):
        agent = Principal.agent("sess", acting_for=Principal.person("dw"), group="cbc", role="analyst")
        with acting_as(agent):
            made = new_record("apply", "analysis", "S1/a")
        self.assertEqual(made.principal, agent.to_dict())
        self.assertEqual(made.principal_obj, agent)

    def test_the_snapshot_is_a_copy_which_later_changes_do_not_reach(self):
        made = record()
        self.assertEqual(made.principal["identifier"], "alice")
        self.assertIsInstance(made.principal, dict)

    def test_secret_looking_values_are_not_kept(self):
        made = new_record(
            "apply",
            "configuration",
            PROJECT,
            content={
                "hooks": {"telemetry": {"pushgateway": {"url": "u", "api_key": "k"}}},
                "password": "p",
                "Token": "t",
                "tokens": ["a", "b"],
                "creds": {"secret": "s", "keep": 1},
                "credentials": {"user": "u", "other": "o"},
                "ordinary": "fine",
            },
        )
        text = json.dumps(made.content)
        for secret in ('"k"', '"p"', '"t"', '"s"'):
            self.assertNotIn(secret, text)
        self.assertEqual(made.content["ordinary"], "fine")
        self.assertEqual(made.content["creds"]["keep"], 1)
        self.assertEqual(made.content["password"], "***")
        self.assertEqual(made.content["tokens"], "***")
        self.assertEqual(made.content["credentials"], "***")

    def test_the_hash_does_not_depend_on_the_secrets(self):
        first = new_record("apply", "configuration", PROJECT, content={"a": 1, "password": "one"})
        second = new_record("apply", "configuration", PROJECT, content={"a": 1, "password": "two"})
        self.assertEqual(first.content_hash, second.content_hash)

    def test_the_hash_depends_on_the_content_not_its_order(self):
        a = new_record("apply", "x", "t", content={"a": 1, "b": 2})
        b = new_record("apply", "x", "t", content={"b": 2, "a": 1})
        c = new_record("apply", "x", "t", content={"a": 1, "b": 3})
        self.assertEqual(a.content_hash, b.content_hash)
        self.assertNotEqual(a.content_hash, c.content_hash)
        self.assertEqual(len(a.content_hash), 64)

    def test_the_content_is_plain_data(self):
        made = new_record("apply", "event", "S1", content={"when": datetime.date(2020, 1, 2), "t": (1, 2)})
        self.assertEqual(made.content, {"when": "2020-01-02", "t": [1, 2]})
        json.dumps(made.content)

    def test_the_content_is_copied(self):
        original = {"a": {"b": 1}}
        made = new_record("apply", "x", "t", content=original)
        original["a"]["b"] = 2
        self.assertEqual(made.content["a"]["b"], 1)

    def test_a_record_without_content_has_no_hash(self):
        made = new_record("apply", "x", "t")
        self.assertIsNone(made.content)
        self.assertEqual(made.content_hash, "")

    def test_timestamps_have_a_fixed_width_and_sort_as_text(self):
        early = datetime.datetime(2026, 1, 2, 3, 4, 5, tzinfo=datetime.timezone.utc)
        late = early + datetime.timedelta(microseconds=1)
        self.assertEqual(timestamp_for(early), "2026-01-02T03:04:05.000000Z")
        self.assertEqual(len(timestamp_for(early)), len(timestamp_for(late)))
        self.assertLess(timestamp_for(early), timestamp_for(late))

    def test_timestamps_are_in_utc(self):
        plus_one = datetime.timezone(datetime.timedelta(hours=1))
        moment = datetime.datetime(2026, 1, 2, 4, 0, 0, tzinfo=plus_one)
        self.assertEqual(timestamp_for(moment), "2026-01-02T03:00:00.000000Z")
        self.assertEqual(timestamp_for(datetime.datetime(2026, 1, 2, 4)), "2026-01-02T04:00:00.000000Z")

    def test_round_trip_and_unknown_keys(self):
        made = record()
        self.assertEqual(AuditRecord.from_dict(made.to_dict()), made)
        self.assertEqual(AuditRecord.from_dict({**made.to_dict(), "future": 1}), made)

    def test_a_record_is_immutable(self):
        with self.assertRaises(Exception):
            record().target = "elsewhere"

    def test_prov_describes_the_change_and_who_made_it(self):
        agent = Principal.agent("sess", acting_for=Principal.person("dw"))
        stored = AuditRecord.from_dict({**record(who=agent).to_dict(), "id": 7})
        activity, agent_node, person_node = stored.to_prov()
        self.assertEqual(activity["@id"], "urn:asimov:activity:audit:7")
        self.assertEqual(activity["@type"], ["prov:Activity", "CreateAction"])
        self.assertEqual(activity["agent"], {"@id": agent.prov_id})
        self.assertEqual(activity["prov:wasAssociatedWith"], {"@id": agent.prov_id})
        self.assertEqual(activity["prov:startedAtTime"], stored.timestamp)
        self.assertEqual(activity["asimov:target"], "S1/a")
        self.assertEqual(agent_node["prov:actedOnBehalfOf"], {"@id": person_node["@id"]})

    def test_a_prov_document_describes_each_agent_once(self):
        records = [record(who=Principal.person("alice")) for _ in range(3)]
        records = [AuditRecord.from_dict({**r.to_dict(), "id": i}) for i, r in enumerate(records, 1)]
        document = prov_document(records)
        ids = [node["@id"] for node in document["@graph"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(sum(1 for node in document["@graph"] if node["@type"] == "prov:Person"), 1)
        self.assertEqual(sum(1 for node in document["@graph"] if "CreateAction" in node["@type"]), 3)
        self.assertIn("prov", document["@context"][1])


class TestFilter(unittest.TestCase):
    def setUp(self):
        self.records = [
            AuditRecord.from_dict({**record("S1", "event").to_dict(), "id": 1}),
            AuditRecord.from_dict({**record("S1/a", "analysis").to_dict(), "id": 2}),
            AuditRecord.from_dict({**record("S10/a", "analysis").to_dict(), "id": 3}),
            AuditRecord.from_dict(
                {
                    **record(
                        "S2/b",
                        "analysis",
                        who=Principal.agent("sess", acting_for=Principal.person("dw")),
                    ).to_dict(),
                    "id": 4,
                }
            ),
            AuditRecord.from_dict({**record(PROJECT, "configuration").to_dict(), "id": 5}),
        ]

    def ids(self, **filters):
        return [r.id for r in filter_records(self.records, **filters)]

    def test_no_filter_gives_everything_in_order(self):
        self.assertEqual(self.ids(), [1, 2, 3, 4, 5])

    def test_a_target_includes_what_is_under_it_but_not_lookalikes(self):
        self.assertEqual(self.ids(target="S1"), [1, 2])
        self.assertEqual(self.ids(target="S1/a"), [2])
        self.assertEqual(self.ids(target=PROJECT), [5])

    def test_a_principal_includes_agents_acting_for_them(self):
        self.assertEqual(self.ids(principal="alice"), [1, 2, 3, 5])
        self.assertEqual(self.ids(principal="dw"), [4])
        self.assertEqual(self.ids(principal="sess"), [4])
        self.assertEqual(self.ids(principal="nobody"), [])

    def test_kind_and_action(self):
        self.assertEqual(self.ids(kind="event"), [1])
        self.assertEqual(self.ids(kind="analysis", target="S1"), [2])
        self.assertEqual(self.ids(action="apply"), [1, 2, 3, 4, 5])
        self.assertEqual(self.ids(action="build"), [])

    def test_since_is_inclusive_and_until_is_not(self):
        stamps = [
            timestamp_for(datetime.datetime(2026, 1, day)) for day in (1, 2, 3, 4, 5)
        ]
        dated = [
            AuditRecord.from_dict({**r.to_dict(), "timestamp": stamp, "id": r.id})
            for r, stamp in zip(self.records, stamps)
        ]
        got = lambda **f: [r.id for r in filter_records(dated, **f)]  # noqa: E731
        self.assertEqual(got(since=datetime.datetime(2026, 1, 3)), [3, 4, 5])
        self.assertEqual(got(until=datetime.datetime(2026, 1, 3)), [1, 2])
        self.assertEqual(
            got(since=datetime.datetime(2026, 1, 2), until=datetime.datetime(2026, 1, 4)), [2, 3]
        )


class LedgerTestCase(unittest.TestCase):
    def setUp(self):
        self.origin = os.getcwd()
        self.dirs = []
        self.addCleanup(os.chdir, self.origin)

    def tearDown(self):
        os.chdir(self.origin)
        for path in self.dirs:
            shutil.rmtree(path, ignore_errors=True)

    def context(self, engine):
        root = tempfile.mkdtemp()
        self.dirs.append(root)
        make_project(name="T", root=root, engine=engine)
        os.chdir(self.origin)
        ctx = ProjectContext.from_directory(root)
        self.addCleanup(lambda: getattr(ctx.ledger, "close", lambda: None)())
        return ctx


class TestLedgerAuditLog(LedgerTestCase):
    def test_appending_gives_ids_in_order(self):
        for engine in ENGINES:
            with self.subTest(engine=engine):
                ledger = self.context(engine).ledger
                first = ledger.append_audit(record("S1"))
                second = ledger.append_audit(record("S2"))
                self.assertEqual((first.id, second.id), (1, 2))
                self.assertEqual([r.id for r in ledger.audit_log()], [1, 2])

    def test_a_stored_record_reads_back_as_it_was_written(self):
        for engine in ENGINES:
            with self.subTest(engine=engine):
                ledger = self.context(engine).ledger
                written = ledger.append_audit(record("S1/a", who=Principal.agent("s", acting_for=Principal.person("dw"))))
                (read,) = ledger.audit_log()
                self.assertEqual(read, written)
                self.assertEqual(read.principal_obj.on_behalf_of, Principal.person("dw"))

    def test_the_log_survives_reopening_the_project(self):
        for engine in ENGINES:
            with self.subTest(engine=engine):
                ctx = self.context(engine)
                ctx.ledger.append_audit(record("S1"))
                again = ProjectContext.from_directory(ctx.root)
                try:
                    self.assertEqual([r.target for r in again.ledger.audit_log()], ["S1"])
                finally:
                    getattr(again.ledger, "close", lambda: None)()

    def test_filters_mean_the_same_on_every_ledger(self):
        for engine in ENGINES:
            with self.subTest(engine=engine):
                ledger = self.context(engine).ledger
                ledger.append_audit(record("S1", "event"))
                ledger.append_audit(record("S1/a", "analysis"))
                ledger.append_audit(record("S10/a", "analysis"))
                ledger.append_audit(
                    record("S2/b", "analysis", who=Principal.agent("sess", acting_for=Principal.person("dw")))
                )
                ledger.append_audit(record(PROJECT, "configuration"))
                targets = lambda **f: [r.target for r in ledger.audit_log(**f)]  # noqa: E731
                self.assertEqual(targets(target="S1"), ["S1", "S1/a"])
                self.assertEqual(targets(target="S1/a"), ["S1/a"])
                self.assertEqual(targets(principal="dw"), ["S2/b"])
                self.assertEqual(targets(principal="alice"), ["S1", "S1/a", "S10/a", PROJECT])
                self.assertEqual(targets(kind="event"), ["S1"])
                self.assertEqual(targets(limit=2), ["S2/b", PROJECT])
                self.assertEqual(targets(limit=2, principal="alice"), ["S10/a", PROJECT])
                self.assertEqual(targets(since=datetime.datetime(2999, 1, 1)), [])
                self.assertEqual(len(targets(until=datetime.datetime(2999, 1, 1))), 5)
                self.assertEqual(len(targets(since=datetime.datetime(2000, 1, 1))), 5)

    def test_a_target_with_wildcard_characters_matches_only_itself(self):
        for engine in ENGINES:
            with self.subTest(engine=engine):
                ledger = self.context(engine).ledger
                ledger.append_audit(record("GW_1/a"))
                ledger.append_audit(record("GWX1/a"))
                ledger.append_audit(record("GW%/a"))
                self.assertEqual([r.target for r in ledger.audit_log(target="GW_1")], ["GW_1/a"])
                self.assertEqual([r.target for r in ledger.audit_log(target="GW%")], ["GW%/a"])

    def test_a_project_made_before_the_log_gains_its_table(self):
        ctx = self.context("sqlite")
        from sqlalchemy import text

        with ctx.ledger.db.engine.begin() as connection:
            connection.execute(text("DROP TABLE audit_log"))
        ctx.ledger.close()

        reopened = ProjectContext.from_directory(ctx.root)
        try:
            reopened.ledger.append_audit(record("S1"))
            self.assertEqual([r.target for r in reopened.ledger.audit_log()], ["S1"])
        finally:
            reopened.ledger.close()

    def test_there_is_no_way_to_change_or_remove_a_record(self):
        for engine in ENGINES:
            with self.subTest(engine=engine):
                ledger = self.context(engine).ledger
                for name in dir(ledger):
                    if "audit" in name:
                        self.assertNotRegex(name, r"update|delete|remove|clear|edit|rewrite")

    def test_the_yaml_log_is_a_file_beside_the_ledger(self):
        ctx = self.context("yamlfile")
        ctx.ledger.append_audit(record("S1"))
        path = os.path.join(ctx.root, ".asimov", "audit.jsonl")
        with open(path) as f:
            lines = f.read().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])["target"], "S1")

    def test_an_unreadable_line_in_the_yaml_log_is_skipped(self):
        ctx = self.context("yamlfile")
        ctx.ledger.append_audit(record("S1"))
        with open(os.path.join(ctx.root, ".asimov", "audit.jsonl"), "a") as f:
            f.write("this is not json\n")
        ctx.ledger.append_audit(record("S2"))
        self.assertEqual([r.target for r in ctx.ledger.audit_log()], ["S1", "S2"])

    def test_a_tinydb_ledger_keeps_a_log_too(self):
        directory = tempfile.mkdtemp()
        self.dirs.append(directory)
        ledger = DatabaseLedger(engine="tinydb", location=os.path.join(directory, "ledger.json"))
        ledger.append_audit(record("S1"))
        ledger.append_audit(record("S2/a", who=Principal.person("bob")))
        self.assertEqual([r.target for r in ledger.audit_log()], ["S1", "S2/a"])
        self.assertEqual([r.target for r in ledger.audit_log(principal="bob")], ["S2/a"])
        self.assertEqual([r.target for r in ledger.audit_log(target="S2", limit=1)], ["S2/a"])


class TestTransactions(LedgerTestCase):
    """A change which doesn't happen leaves no record, and vice versa."""

    def test_records_in_a_failed_block_are_not_kept(self):
        for engine in ENGINES:
            with self.subTest(engine=engine):
                ledger = self.context(engine).ledger
                with self.assertRaises(ValueError):
                    with ledger.transaction():
                        ledger.append_audit(record("S1"))
                        raise ValueError
                self.assertEqual(ledger.audit_log(), [])

    def test_records_in_a_successful_block_are_kept(self):
        for engine in ENGINES:
            with self.subTest(engine=engine):
                ledger = self.context(engine).ledger
                with ledger.transaction():
                    ledger.append_audit(record("S1"))
                    ledger.append_audit(record("S2"))
                self.assertEqual([r.target for r in ledger.audit_log()], ["S1", "S2"])

    def test_a_block_sees_its_own_records(self):
        for engine in ENGINES:
            with self.subTest(engine=engine):
                ledger = self.context(engine).ledger
                with ledger.transaction():
                    ledger.append_audit(record("S1"))
                    self.assertEqual([r.target for r in ledger.audit_log()], ["S1"])

    def test_nested_blocks_join_the_outer_one(self):
        for engine in ENGINES:
            with self.subTest(engine=engine):
                ledger = self.context(engine).ledger
                with self.assertRaises(ValueError):
                    with ledger.transaction():
                        with ledger.transaction():
                            ledger.append_audit(record("inner"))
                        ledger.append_audit(record("outer"))
                        raise ValueError
                self.assertEqual(ledger.audit_log(), [])
                with ledger.transaction():
                    with ledger.transaction():
                        ledger.append_audit(record("inner"))
                    ledger.append_audit(record("outer"))
                self.assertEqual([r.target for r in ledger.audit_log()], ["inner", "outer"])

    def test_a_failed_block_does_not_lose_earlier_records(self):
        for engine in ENGINES:
            with self.subTest(engine=engine):
                ledger = self.context(engine).ledger
                ledger.append_audit(record("kept"))
                with self.assertRaises(ValueError):
                    with ledger.transaction():
                        ledger.append_audit(record("lost"))
                        raise ValueError
                self.assertEqual([r.target for r in ledger.audit_log()], ["kept"])

    def test_a_project_block_which_fails_leaves_no_record(self):
        from asimov.project import Project

        for engine in ENGINES:
            with self.subTest(engine=engine):
                root = tempfile.mkdtemp()
                self.dirs.append(root)
                Project("T", location=root, engine=engine)
                project = Project.load(root)
                with self.assertRaises(ValueError):
                    with project:
                        project.ledger.append_audit(record("S1"))
                        raise ValueError
                with project:
                    self.assertEqual(project.ledger.audit_log(), [])
                    project.ledger.append_audit(record("S2"))
                with project:
                    self.assertEqual([r.target for r in project.ledger.audit_log()], ["S2"])


class TestApplyRecords(LedgerTestCase):
    """``asimov apply`` records what it applies (#143)."""

    def setUp(self):
        super().setUp()
        self.addCleanup(self._clear_registry)

    @staticmethod
    def _clear_registry():
        telemetry.TELEMETRY_SINK_REGISTRY.pop("fake", None)

    def project(self, engine):
        ctx = self.context(engine)
        with ctx.activate():
            apply_page(os.path.join(DATA, "testing_pe.yaml"), ledger=ctx.ledger)
            apply_page(os.path.join(DATA, "test_event.yaml"), ledger=ctx.ledger)
        return ctx

    def apply_text(self, ctx, text, **kwargs):
        path = os.path.join(tempfile.mkdtemp(), "blueprint.yaml")
        self.dirs.append(os.path.dirname(path))
        with open(path, "w") as f:
            f.write(text)
        with ctx.activate():
            apply_page(path, ledger=ctx.ledger, **kwargs)

    def summary(self, ctx, **filters):
        return [(r.kind, r.target, r.outcome) for r in ctx.ledger.audit_log(**filters)]

    def test_configuration_and_event_are_recorded(self):
        for engine in ENGINES:
            with self.subTest(engine=engine):
                with acting_as(Principal.person("alice")):
                    ctx = self.project(engine)
                self.assertEqual(
                    self.summary(ctx),
                    [("configuration", PROJECT, "added"), ("event", "S000000", "added")],
                )
                first = ctx.ledger.audit_log()[0]
                self.assertEqual(first.principal_obj, Principal.person("alice"))
                self.assertTrue(first.content_hash)
                self.assertEqual(first.action, "apply")

    def test_an_applied_analysis_is_recorded_with_who_applied_it(self):
        for engine in ENGINES:
            with self.subTest(engine=engine):
                ctx = self.project(engine)
                agent = Principal.agent("sess-1", acting_for=Principal.person("dw"))
                with acting_as(agent):
                    with ctx.activate():
                        apply_page(
                            os.path.join(BLUEPRINTS, "simple_test_pipeline.yaml"),
                            event="S000000",
                            ledger=ctx.ledger,
                        )
                (made,) = ctx.ledger.audit_log(kind="analysis")
                self.assertEqual(made.target, "S000000/test-simple-pipeline")
                self.assertEqual(made.principal_obj, agent)
                self.assertEqual(made.content["name"], "test-simple-pipeline")
                self.assertEqual(
                    [r.target for r in ctx.ledger.audit_log(principal="dw")],
                    ["S000000/test-simple-pipeline"],
                )

    def test_an_analysis_which_is_refused_leaves_no_record(self):
        for engine in ENGINES:
            with self.subTest(engine=engine):
                ctx = self.project(engine)
                path = os.path.join(BLUEPRINTS, "simple_test_pipeline.yaml")
                with ctx.activate():
                    apply_page(path, event="S000000", ledger=ctx.ledger)
                    before = len(ctx.ledger.audit_log())
                    apply_page(path, event="S000000", ledger=ctx.ledger)
                self.assertEqual(len(ctx.ledger.audit_log()), before)

    def test_an_event_which_already_exists_leaves_no_record(self):
        for engine in ENGINES:
            with self.subTest(engine=engine):
                ctx = self.project(engine)
                before = len(ctx.ledger.audit_log())
                with ctx.activate():
                    apply_page(os.path.join(DATA, "test_event.yaml"), ledger=ctx.ledger)
                self.assertEqual(len(ctx.ledger.audit_log()), before)

    def test_updating_an_event_is_recorded_as_an_update(self):
        for engine in ENGINES:
            with self.subTest(engine=engine):
                ctx = self.project(engine)
                with ctx.activate():
                    apply_page(
                        os.path.join(DATA, "test_event.yaml"), ledger=ctx.ledger, update_page=True
                    )
                self.assertEqual(self.summary(ctx, kind="event")[-1], ("event", "S000000", "updated"))

    def test_a_project_analysis_is_recorded(self):
        for engine in ENGINES:
            with self.subTest(engine=engine):
                ctx = self.project(engine)
                self.apply_text(
                    ctx,
                    "kind: projectanalysis\nname: pa1\npipeline: simpletestpipeline\n"
                    "subjects: [S000000]\nanalyses:\n- - 'pipeline: simpletestpipeline'\nstatus: ready\n",
                )
                self.assertEqual(
                    self.summary(ctx, kind="projectanalysis"),
                    [("projectanalysis", f"{PROJECT}/pa1", "added")],
                )

    def test_analyses_in_a_bundle_are_recorded_one_by_one(self):
        for engine in ENGINES:
            with self.subTest(engine=engine):
                ctx = self.project(engine)
                self.apply_text(
                    ctx,
                    "kind: analysisbundle\nname: b\nanalyses:\n"
                    "- name: one\n  pipeline: simpletestpipeline\n  status: ready\n"
                    "- name: two\n  pipeline: simpletestpipeline\n  status: ready\n",
                    event="S000000",
                )
                self.assertEqual(
                    [t for _, t, _ in self.summary(ctx, kind="analysis")],
                    ["S000000/one", "S000000/two"],
                )

    def test_postprocessing_is_recorded_against_the_project(self):
        ctx = self.project("yamlfile")
        self.apply_text(ctx, "kind: postprocessing\nname: stage-one\npipeline: simpletestpipeline\n")
        self.assertEqual(self.summary(ctx, kind="postprocessing"), [("postprocessing", PROJECT, "added")])

    def test_secrets_in_a_blueprint_are_not_kept_in_the_log(self):
        for engine in ENGINES:
            with self.subTest(engine=engine):
                ctx = self.project(engine)
                self.apply_text(ctx, "kind: configuration\nservice:\n  url: https://x\n  api_key: hunter2\n")
                logged = json.dumps([r.to_dict() for r in ctx.ledger.audit_log()])
                self.assertNotIn("hunter2", logged)
                self.assertIn("https://x", logged)

    def test_a_change_and_its_record_are_stored_together(self):
        """If the record can't be written, the change is not kept either."""
        ctx = self.project("sqlite")
        path = os.path.join(BLUEPRINTS, "simple_test_pipeline.yaml")

        def broken(ledger, made):
            raise RuntimeError("the log is unavailable")

        with patch("asimov.cli.application.append_audit", broken):
            with ctx.activate():
                with self.assertRaises(RuntimeError):
                    apply_page(path, event="S000000", ledger=ctx.ledger)

        with ctx.activate():
            names = [p.name for p in ctx.ledger.get_event("S000000")[0].productions]
        self.assertNotIn("test-simple-pipeline", names)
        self.assertEqual(self.summary(ctx, kind="analysis"), [])

    def test_the_record_is_copied_to_enabled_telemetry_sinks(self):
        received = []

        class Sink(telemetry.TelemetrySink):
            @property
            def name(self):
                return "fake"

            def emit(self, event):
                received.append(event)

        telemetry.register_telemetry_sink(Sink())
        for engine in ENGINES:
            with self.subTest(engine=engine):
                received.clear()
                ctx = self.context(engine)
                ctx.ledger.data.setdefault("hooks", {})["telemetry"] = {"fake": {}}
                stored = append_audit(ctx.ledger, record("S1"))
                (event,) = received
                self.assertEqual(event.event_type, "audit")
                self.assertEqual(event.data["target"], "S1")
                self.assertEqual(event.data["id"], stored.id)

    def test_a_telemetry_sink_which_fails_does_not_matter(self):
        class Broken(telemetry.TelemetrySink):
            @property
            def name(self):
                return "fake"

            def emit(self, event):
                raise RuntimeError("unreachable")

        telemetry.register_telemetry_sink(Broken())
        ctx = self.context("sqlite")
        ctx.ledger.data.setdefault("hooks", {})["telemetry"] = {"fake": {}}
        append_audit(ctx.ledger, record("S1"))
        self.assertEqual([r.target for r in ctx.ledger.audit_log()], ["S1"])

    def test_sinks_which_are_not_enabled_get_nothing(self):
        received = []

        class Sink(telemetry.TelemetrySink):
            @property
            def name(self):
                return "fake"

            def emit(self, event):
                received.append(event)

        telemetry.register_telemetry_sink(Sink())
        ctx = self.context("sqlite")
        append_audit(ctx.ledger, record("S1"))
        self.assertEqual(received, [])


class TestCommand(LedgerTestCase):
    def setUp(self):
        super().setUp()
        self.ctx = self.context("sqlite")
        with self.ctx.activate():
            with acting_as(Principal.person("alice")):
                apply_page(os.path.join(DATA, "testing_pe.yaml"), ledger=self.ctx.ledger)
                apply_page(os.path.join(DATA, "test_event.yaml"), ledger=self.ctx.ledger)
            with acting_as(Principal.agent("sess", acting_for=Principal.person("dw"))):
                apply_page(
                    os.path.join(BLUEPRINTS, "simple_test_pipeline.yaml"),
                    event="S000000",
                    ledger=self.ctx.ledger,
                )

    def run_command(self, *args):
        with self.ctx.activate():
            result = CliRunner().invoke(audit_cli.audit, ["show", *args])
        self.assertEqual(result.exit_code, 0, result.output)
        return result.output

    def test_the_table_lists_the_log_oldest_first(self):
        lines = self.run_command().strip().splitlines()
        self.assertEqual(len(lines), 3)
        self.assertIn("configuration", lines[0])
        self.assertIn("alice", lines[0])
        self.assertIn("sess (for dw)", lines[2])
        self.assertIn("S000000/test-simple-pipeline", lines[2])

    def test_filters(self):
        self.assertEqual(len(self.run_command("--principal", "dw").strip().splitlines()), 1)
        self.assertEqual(len(self.run_command("--target", "S000000").strip().splitlines()), 2)
        self.assertEqual(len(self.run_command("--kind", "event").strip().splitlines()), 1)
        self.assertEqual(len(self.run_command("--limit", "1").strip().splitlines()), 1)
        self.assertEqual(len(self.run_command("--since", "2999-01-01").strip().splitlines()), 1)
        self.assertEqual(self.run_command("--since", "2999-01-01").strip(), "There are no matching records.")
        self.assertEqual(len(self.run_command("--until", "2999-01-01").strip().splitlines()), 3)

    def test_json_includes_what_was_applied(self):
        data = json.loads(self.run_command("--format", "json"))
        self.assertEqual(len(data), 3)
        self.assertEqual(data[2]["content"]["name"], "test-simple-pipeline")
        self.assertEqual(data[2]["principal"]["acting for"]["identifier"], "dw")

    def test_prov_is_json_ld(self):
        document = json.loads(self.run_command("--format", "prov"))
        self.assertIn("@graph", document)
        activities = [n for n in document["@graph"] if "CreateAction" in n["@type"]]
        self.assertEqual(len(activities), 3)

    def test_a_bad_date_is_refused(self):
        with self.ctx.activate():
            result = CliRunner().invoke(audit_cli.audit, ["show", "--since", "yesterday"])
        self.assertNotEqual(result.exit_code, 0)


if __name__ == "__main__":
    unittest.main()
