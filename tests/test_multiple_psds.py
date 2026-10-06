"""
End-to-end coverage for issue #153: "Support for multiple PSDs per event".

The underlying mechanism (`GravitationalWaveTransient._collect_psds`, in
``asimov/analysis.py``) already supports this in principle: a production can
either specify its own ``psds:`` block directly, or inherit PSDs from
whichever of its ``needs:`` dependencies produced them
(``pipeline.collect_assets()["psds"]``). This had never been exercised
end-to-end, so it was unclear whether it actually worked for the scenario
described in the issue -- generating PSDs via multiple methods, then
comparing PE outputs across them within a single project.

These tests drive the real ledger/apply_page/dependency-resolution code
paths (matching the style of ``tests/test_dependencies.py``), but substitute
lightweight fixture pipelines for BayesWave/Bilby so the tests run in
milliseconds instead of waiting on real analyses.
"""
import logging
import os
import shutil
import unittest
from unittest.mock import patch

import asimov.pipelines
from asimov.pipelines.testing.simple import SimpleTestPipeline
from asimov.cli.application import apply_page
from asimov.cli.manage import check_psds_available
from asimov.cli.project import make_project
from asimov.event import DescriptionException
from asimov.ledger import YAMLLedger

IFOS = ["H1", "L1"]


class _FakePSDPipeline(SimpleTestPipeline):
    """Stands in for a real PSD-estimation pipeline (e.g. BayesWave).

    Produces a ``psds`` asset keyed by interferometer, with a file unique to
    this production (its rundir is ``<working directory>/<production name>``),
    so that two different PSD-estimation productions for the same event never
    collide or get confused with one another.
    """

    name = "FakePSDPipeline"

    def collect_assets(self):
        assets = super().collect_assets()
        if not self.production.rundir:
            return assets
        os.makedirs(self.production.rundir, exist_ok=True)
        psds = {}
        for ifo in IFOS:
            psd_file = os.path.join(self.production.rundir, f"{ifo}-psd.dat")
            if not os.path.exists(psd_file):
                with open(psd_file, "w") as psd_fh:
                    psd_fh.write(
                        f"# Fake PSD for {ifo}, produced by {self.production.name}\n"
                    )
            psds[ifo] = psd_file
        assets["psds"] = psds
        return assets


class _FakePEPipeline(SimpleTestPipeline):
    """Stands in for a real PE pipeline (e.g. Bilby); produces no PSDs of its own."""

    name = "FakePEPipeline"


class _FakeUnfinishedPSDPipeline(SimpleTestPipeline):
    """A PSD-estimation pipeline that is expected to provide PSDs (it
    declares ``psds`` in ``available_outputs``) but hasn't finished running
    yet, so ``collect_assets()`` doesn't have any to offer -- used to check
    the build-time PSD check catches this rather than silently building a
    PE job with no noise curve."""

    name = "FakeUnfinishedPSDPipeline"
    available_outputs = ["psds"]


class _FakeXMLPSDPipeline(SimpleTestPipeline):
    """A PSD-estimation pipeline which only provides ``xml psds``, used to
    check the ``xml psds`` code path independently of the ascii one."""

    name = "FakeXMLPSDPipeline"

    def collect_assets(self):
        assets = super().collect_assets()
        if not self.production.rundir:
            return assets
        assets["xml psds"] = {
            ifo: os.path.join(self.production.rundir, f"{ifo}-psd.xml.gz")
            for ifo in IFOS
        }
        return assets


class _FakeBayesWaveLikePipeline(_FakePSDPipeline):
    """Mimics asimov-bayeswave when ``convert_psd_ascii2xml`` isn't
    installed: ``collect_assets()`` always has an ``xml psds`` key, but it
    stays empty even once the job has finished and its ascii PSDs exist."""

    name = "FakeBayesWaveLikePipeline"

    def collect_assets(self):
        assets = super().collect_assets()
        assets["xml psds"] = {}
        return assets


EVENT_BLUEPRINT = """
kind: event
name: GW150914_095045
interferometers:
- H1
- L1
"""


def _psd_mapping_block(key, psds):
    """Render a detector-keyed PSD mapping (e.g. ``psds: {H1: ..., L1: ...}``)
    as a YAML block under the given top-level key."""
    return f"{key}:\n" + "\n".join(f"  {ifo}: {path}" for ifo, path in psds.items()) + "\n"


def _event_blueprint(psds=None, xml_psds=None, sample_rate=None, rate_keyed_psds=None):
    """Build an event blueprint, optionally carrying event-level PSDs.

    Parameters
    ----------
    psds : dict, optional
        A detector-keyed ``psds:`` mapping to set at the event level.
    xml_psds : dict, optional
        As `psds`, but for ``xml psds:``.
    sample_rate : int, optional
        A ``likelihood: sample rate:`` to set at the event level (needed to
        resolve `rate_keyed_psds`).
    rate_keyed_psds : dict, optional
        A legacy, sample-rate-keyed ``psds:`` mapping, e.g.
        ``{1024: {H1: ..., L1: ...}}`` (see
        ``tests/integration/GW190426190642.yaml``). Mutually exclusive with
        `psds`.
    """
    doc = EVENT_BLUEPRINT
    if sample_rate is not None:
        doc += f"likelihood:\n  sample rate: {sample_rate}\n"
    if psds:
        doc += _psd_mapping_block("psds", psds)
    if rate_keyed_psds:
        doc += "psds:\n"
        for rate, ifo_psds in rate_keyed_psds.items():
            doc += f"  {rate}:\n"
            for ifo, path in ifo_psds.items():
                doc += f"    {ifo}: {path}\n"
    if xml_psds:
        doc += _psd_mapping_block("xml psds", xml_psds)
    return doc


def _psd_blueprint(name, pipeline="fakepsdpipeline"):
    return f"""
kind: analysis
name: {name}
pipeline: {pipeline}
comment: PSD estimation job
event: GW150914_095045
status: ready
"""


def _unfinished_psd_blueprint(name):
    return f"""
kind: analysis
name: {name}
pipeline: fakeunfinishedpsdpipeline
comment: PSD estimation job that hasn't finished yet
event: GW150914_095045
status: running
"""


def _pe_blueprint(name, needs=None, psds=None, xml_psds=None):
    doc = f"""
kind: analysis
name: {name}
pipeline: fakepepipeline
comment: PE job
event: GW150914_095045
status: ready
"""
    if needs:
        doc += "needs:\n" + "\n".join(f"  - {n}" for n in needs) + "\n"
    if psds:
        doc += _psd_mapping_block("psds", psds)
    if xml_psds:
        doc += _psd_mapping_block("xml psds", xml_psds)
    return doc


class MultiplePSDsPerEventTests(unittest.TestCase):
    """Regression/coverage tests for issue #153."""

    @classmethod
    def setUpClass(cls):
        cls.cwd = os.getcwd()

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls.cwd)

    def setUp(self):
        known_pipelines_patch = patch.dict(
            asimov.pipelines.known_pipelines,
            {
                "fakepsdpipeline": _FakePSDPipeline,
                "fakepepipeline": _FakePEPipeline,
                "fakeunfinishedpsdpipeline": _FakeUnfinishedPSDPipeline,
                "fakexmlpsdpipeline": _FakeXMLPSDPipeline,
                "fakebayeswavelikepipeline": _FakeBayesWaveLikePipeline,
            },
        )
        known_pipelines_patch.start()
        self.addCleanup(known_pipelines_patch.stop)

        os.makedirs(f"{self.cwd}/tests/tmp/multiple_psds_project")
        os.chdir(f"{self.cwd}/tests/tmp/multiple_psds_project")
        make_project(
            name="Test project", root=f"{self.cwd}/tests/tmp/multiple_psds_project"
        )
        self.ledger = YAMLLedger(".asimov/ledger.yml")

    def tearDown(self):
        del self.ledger
        os.chdir(self.cwd)
        shutil.rmtree(f"{self.cwd}/tests/tmp/multiple_psds_project")

    def _apply(self, contents, name):
        path = f"tests/tmp/multiple_psds_project/{name}.yaml"
        with open(f"{self.cwd}/{path}", "w") as blueprint_file:
            blueprint_file.write(contents)
        apply_page(file=f"{self.cwd}/{path}", ledger=self.ledger)

    def test_pe_productions_inherit_distinct_psds_from_their_own_dependency(self):
        """Two PE productions, each depending on a *different* PSD job for
        the same event, should each pick up only their own dependency's PSDs
        -- the scenario described in #153 (comparing bilby outputs across
        PSDs generated by different methods, within one project)."""
        self._apply(EVENT_BLUEPRINT, "event")
        self._apply(_psd_blueprint("BayesWavePSD"), "psd_bw")
        self._apply(_psd_blueprint("AltMethodPSD"), "psd_alt")
        self._apply(_pe_blueprint("Bilby_BW", needs=["BayesWavePSD"]), "pe_bw")
        self._apply(_pe_blueprint("Bilby_Alt", needs=["AltMethodPSD"]), "pe_alt")

        event = self.ledger.get_event("GW150914_095045")[0]
        productions = {p.name: p for p in event.productions}

        bw_psds = productions["BayesWavePSD"].pipeline.collect_assets()["psds"]
        alt_psds = productions["AltMethodPSD"].pipeline.collect_assets()["psds"]

        # Sanity check: the two PSD-generation methods actually produced
        # different PSDs (different files), otherwise this test would pass
        # trivially.
        self.assertNotEqual(bw_psds, alt_psds)

        self.assertEqual(productions["Bilby_BW"].psds, bw_psds)
        self.assertEqual(productions["Bilby_Alt"].psds, alt_psds)
        self.assertNotEqual(productions["Bilby_BW"].psds, productions["Bilby_Alt"].psds)

    def test_pe_production_with_explicit_psds_overrides_dependency(self):
        """A production can also specify `psds:` directly; this should be
        used as-is, regardless of any `needs:` dependency."""
        self._apply(EVENT_BLUEPRINT, "event")
        self._apply(_psd_blueprint("BayesWavePSD"), "psd_bw")
        explicit_psds = {"H1": "/tmp/explicit-H1.dat", "L1": "/tmp/explicit-L1.dat"}
        self._apply(
            _pe_blueprint("Bilby_Explicit", needs=["BayesWavePSD"], psds=explicit_psds),
            "pe_explicit",
        )

        event = self.ledger.get_event("GW150914_095045")[0]
        productions = {p.name: p for p in event.productions}

        self.assertEqual(productions["Bilby_Explicit"].psds, explicit_psds)

    def test_pe_production_with_no_psd_dependency_has_no_psds(self):
        """A PE production that doesn't depend on any PSD-producing job
        should simply have no PSDs, rather than picking one up by accident.

        Deliberately applies an *unrelated* PSD-producing production to the
        same event first, so this actually exercises "there is a PSD source
        in this event, but I don't depend on it" rather than trivially
        passing because the event has no PSD source at all.
        """
        self._apply(EVENT_BLUEPRINT, "event")
        self._apply(_psd_blueprint("UnrelatedPSD"), "psd_unrelated")
        self._apply(_pe_blueprint("Bilby_NoPSD"), "pe_no_psd")

        event = self.ledger.get_event("GW150914_095045")[0]
        productions = {p.name: p for p in event.productions}

        self.assertEqual(productions["Bilby_NoPSD"].psds, {})

    # ------------------------------------------------------------------
    # Precedence: analysis-level psds > needs: dependency > event-level psds
    # (asimov#153, cases 1-3, 6).
    # ------------------------------------------------------------------

    def test_dependency_psds_win_over_event_level_psds(self):
        """An event-level `psds:` block is a shadow dependency, not an
        override: when a production also `needs:` a PSD-producing job, that
        dependency's PSDs must be used, not the event's."""
        event_psds = {"H1": "/tmp/event-H1.dat", "L1": "/tmp/event-L1.dat"}
        self._apply(_event_blueprint(psds=event_psds), "event")
        self._apply(_psd_blueprint("BayesWavePSD"), "psd_bw")
        self._apply(_pe_blueprint("Bilby_BW", needs=["BayesWavePSD"]), "pe_bw")

        event = self.ledger.get_event("GW150914_095045")[0]
        productions = {p.name: p for p in event.productions}

        dep_psds = productions["BayesWavePSD"].pipeline.collect_assets()["psds"]
        self.assertNotEqual(dep_psds, event_psds)
        self.assertEqual(productions["Bilby_BW"].psds, dep_psds)

    def test_event_level_psds_used_when_no_dependency_provides_them(self):
        """With no `needs:` PSD dependency, a production falls back to the
        event-level `psds:` block."""
        event_psds = {"H1": "/tmp/event-H1.dat", "L1": "/tmp/event-L1.dat"}
        self._apply(_event_blueprint(psds=event_psds), "event")
        self._apply(_pe_blueprint("Bilby_EventPSD"), "pe_event")

        event = self.ledger.get_event("GW150914_095045")[0]
        productions = {p.name: p for p in event.productions}

        self.assertEqual(productions["Bilby_EventPSD"].psds, event_psds)

    def test_analysis_level_psds_win_over_event_level_and_dependency(self):
        """Highest precedence: PSDs set directly on the analysis beat both
        the event-level block and any `needs:` dependency."""
        event_psds = {"H1": "/tmp/event-H1.dat", "L1": "/tmp/event-L1.dat"}
        self._apply(_event_blueprint(psds=event_psds), "event")
        self._apply(_psd_blueprint("BayesWavePSD"), "psd_bw")
        analysis_psds = {"H1": "/tmp/explicit-H1.dat", "L1": "/tmp/explicit-L1.dat"}
        self._apply(
            _pe_blueprint("Bilby_Explicit", needs=["BayesWavePSD"], psds=analysis_psds),
            "pe_explicit",
        )

        event = self.ledger.get_event("GW150914_095045")[0]
        productions = {p.name: p for p in event.productions}

        self.assertEqual(productions["Bilby_Explicit"].psds, analysis_psds)

    def test_analysis_level_partial_override_is_not_merged_with_event_psds(self):
        """A partial analysis-level `psds:` block (e.g. only H1) must
        *replace* the event-level block entirely, not be deep-merged with
        it -- `asimov.utils.update` merges recursively, which would
        otherwise mix an analysis-level H1 PSD with the event's L1 PSD."""
        event_psds = {"H1": "/tmp/event-H1.dat", "L1": "/tmp/event-L1.dat"}
        self._apply(_event_blueprint(psds=event_psds), "event")
        partial_psds = {"H1": "/tmp/explicit-H1.dat"}
        self._apply(_pe_blueprint("Bilby_Partial", psds=partial_psds), "pe_partial")

        event = self.ledger.get_event("GW150914_095045")[0]
        productions = {p.name: p for p in event.productions}

        self.assertEqual(productions["Bilby_Partial"].psds, partial_psds)
        self.assertNotIn("L1", productions["Bilby_Partial"].psds)

    # ------------------------------------------------------------------
    # Legacy sample-rate-keyed event psds (asimov#153, case 2).
    # ------------------------------------------------------------------

    def test_sample_rate_keyed_event_psds_are_normalised(self):
        """Some older event blueprints key `psds:` by sample rate first
        (e.g. `psds: {1024: {H1: ..., L1: ...}}}`, see
        `tests/integration/GW190426190642.yaml`), rather than directly by
        detector. The matching entry for the analysis's configured sample
        rate should be picked out."""
        rate_keyed_psds = {
            512: {"H1": "/tmp/512-H1.dat", "L1": "/tmp/512-L1.dat"},
            1024: {"H1": "/tmp/1024-H1.dat", "L1": "/tmp/1024-L1.dat"},
        }
        self._apply(
            _event_blueprint(sample_rate=1024, rate_keyed_psds=rate_keyed_psds),
            "event",
        )
        self._apply(_pe_blueprint("Bilby_RateKeyed"), "pe_rate_keyed")

        event = self.ledger.get_event("GW150914_095045")[0]
        productions = {p.name: p for p in event.productions}

        self.assertEqual(
            productions["Bilby_RateKeyed"].psds, rate_keyed_psds[1024]
        )

    def test_sample_rate_keyed_event_psds_with_no_match_are_ignored(self):
        """If none of the sample-rate-keyed entries match the analysis's
        configured sample rate, no PSDs should be used (and a warning
        logged), rather than passing on the wrong rate's PSDs."""
        rate_keyed_psds = {
            512: {"H1": "/tmp/512-H1.dat", "L1": "/tmp/512-L1.dat"},
        }
        self._apply(
            _event_blueprint(sample_rate=2048, rate_keyed_psds=rate_keyed_psds),
            "event",
        )
        self._apply(_pe_blueprint("Bilby_NoMatch"), "pe_no_match")

        event = self.ledger.get_event("GW150914_095045")[0]
        productions = {p.name: p for p in event.productions}

        self.assertEqual(productions["Bilby_NoMatch"].psds, {})

    # ------------------------------------------------------------------
    # Ambiguous dependencies (asimov#153, case 4) and the build-time check
    # (asimov#153, case 5).
    # ------------------------------------------------------------------

    def test_multiple_psd_dependencies_are_ambiguous(self):
        """If more than one `needs:` dependency provides PSDs, asimov must
        not silently pick one: the analysis should end up with no PSDs, the
        problem recorded on `_psd_errors`, and the build-time check must
        raise rather than let a run configuration be generated with the
        wrong (or arbitrarily-chosen) PSDs."""
        self._apply(EVENT_BLUEPRINT, "event")
        self._apply(_psd_blueprint("PSD_A"), "psd_a")
        self._apply(_psd_blueprint("PSD_B"), "psd_b")
        # A single property-based dependency (`pipeline: fakepsdpipeline`)
        # matches *both* PSD_A and PSD_B, rather than naming them
        # individually.
        self._apply(
            _pe_blueprint("Bilby_Ambiguous", needs=["pipeline: fakepsdpipeline"]),
            "pe_ambiguous",
        )

        event = self.ledger.get_event("GW150914_095045")[0]
        productions = {p.name: p for p in event.productions}
        analysis = productions["Bilby_Ambiguous"]

        self.assertEqual(sorted(analysis.dependencies), ["PSD_A", "PSD_B"])
        self.assertEqual(analysis.psds, {})
        self.assertTrue(analysis._psd_errors)

        with self.assertRaises(DescriptionException):
            check_psds_available(analysis, logging.getLogger("test"))

    def test_dependency_with_no_psds_yet_fails_build_time_check(self):
        """A production that `needs:` a PSD-estimation job which hasn't
        finished yet (so it provides no PSDs) should fail the build-time
        check, rather than silently being built with no noise curve."""
        self._apply(EVENT_BLUEPRINT, "event")
        self._apply(_unfinished_psd_blueprint("StillRunningPSD"), "psd_running")
        self._apply(
            _pe_blueprint("Bilby_Waiting", needs=["StillRunningPSD"]), "pe_waiting"
        )

        event = self.ledger.get_event("GW150914_095045")[0]
        productions = {p.name: p for p in event.productions}
        analysis = productions["Bilby_Waiting"]

        self.assertEqual(analysis.psds, {})

        with self.assertRaises(DescriptionException):
            check_psds_available(analysis, logging.getLogger("test"))

    def test_analysis_unrelated_to_psds_passes_build_time_check(self):
        """The build-time PSD check must be narrow: an analysis with no
        PSD-providing dependency (and no PSD errors of its own) should pass
        it cleanly, even though it also has no PSDs."""
        self._apply(EVENT_BLUEPRINT, "event")
        self._apply(_pe_blueprint("Bilby_Unrelated"), "pe_unrelated")

        event = self.ledger.get_event("GW150914_095045")[0]
        productions = {p.name: p for p in event.productions}
        analysis = productions["Bilby_Unrelated"]

        self.assertEqual(analysis.psds, {})
        # Should not raise.
        check_psds_available(analysis, logging.getLogger("test"))

    # ------------------------------------------------------------------
    # Deterministic dependency ordering (asimov#153, case 4).
    # ------------------------------------------------------------------

    def test_dependencies_order_is_deterministic(self):
        """`Analysis.dependencies` used to iterate a `set`, so its order
        varied between processes because of hash randomisation. It should
        now be sorted, and stable across repeated access."""
        self._apply(EVENT_BLUEPRINT, "event")
        self._apply(_psd_blueprint("PSD_Zeta"), "psd_zeta")
        self._apply(_psd_blueprint("PSD_Alpha"), "psd_alpha")
        self._apply(_psd_blueprint("PSD_Mu"), "psd_mu")
        self._apply(
            _pe_blueprint(
                "Bilby_Multi", needs=["PSD_Zeta", "PSD_Alpha", "PSD_Mu"]
            ),
            "pe_multi",
        )

        event = self.ledger.get_event("GW150914_095045")[0]
        analysis = {p.name: p for p in event.productions}["Bilby_Multi"]

        expected = ["PSD_Alpha", "PSD_Mu", "PSD_Zeta"]
        self.assertEqual(analysis.dependencies, expected)
        # Access it again to check it's stable, not just correct once.
        self.assertEqual(analysis.dependencies, expected)

    # ------------------------------------------------------------------
    # `xml psds` follows the same rules as `psds` (asimov#153, case 6).
    # ------------------------------------------------------------------

    def test_xml_psds_follow_the_same_precedence_as_ascii_psds(self):
        """`xml psds` should obey the same precedence rules as `psds`:
        analysis-level, then dependency, then event-level."""
        event_xml_psds = {"H1": "/tmp/event-H1.xml", "L1": "/tmp/event-L1.xml"}
        self._apply(_event_blueprint(xml_psds=event_xml_psds), "event")
        self._apply(_pe_blueprint("Bilby_EventXML"), "pe_event_xml")

        analysis_xml_psds = {"H1": "/tmp/explicit-H1.xml", "L1": "/tmp/explicit-L1.xml"}
        self._apply(
            _pe_blueprint("Bilby_ExplicitXML", xml_psds=analysis_xml_psds),
            "pe_explicit_xml",
        )

        event = self.ledger.get_event("GW150914_095045")[0]
        productions = {p.name: p for p in event.productions}

        self.assertEqual(productions["Bilby_EventXML"].xml_psds, event_xml_psds)
        self.assertEqual(productions["Bilby_ExplicitXML"].xml_psds, analysis_xml_psds)
        self.assertEqual(productions["Bilby_EventXML"].psds, {})

    def test_xml_psds_ambiguous_dependency_fails_build_time_check(self):
        """The ambiguous-dependency check applies to `xml psds` too."""
        self._apply(EVENT_BLUEPRINT, "event")
        self._apply(_psd_blueprint("XMLPSD_A", "fakexmlpsdpipeline"), "xmlpsd_a")
        self._apply(_psd_blueprint("XMLPSD_B", "fakexmlpsdpipeline"), "xmlpsd_b")
        self._apply(
            _pe_blueprint(
                "Bilby_AmbiguousXML", needs=["pipeline: fakexmlpsdpipeline"]
            ),
            "pe_ambiguous_xml",
        )

        event = self.ledger.get_event("GW150914_095045")[0]
        productions = {p.name: p for p in event.productions}
        analysis = productions["Bilby_AmbiguousXML"]

        self.assertEqual(analysis.xml_psds, {})
        self.assertIn("xml psds", analysis._psd_errors)
        # Neither dependency provides ascii PSDs, but both have produced
        # PSDs, so there's nothing to complain about for that format.
        self.assertNotIn("psds", analysis._psd_errors)
        with self.assertRaises(DescriptionException):
            check_psds_available(analysis, logging.getLogger("test"))

    def test_unfinished_dependency_does_not_fall_back_to_event_psds(self):
        """If the PSD dependency hasn't produced its PSDs yet, the analysis
        must not quietly use the event-level PSDs in the meantime: that
        would build the run with a different noise curve from the one its
        `needs:` asked for."""
        event_psds = {"H1": "/tmp/event-H1.dat", "L1": "/tmp/event-L1.dat"}
        self._apply(_event_blueprint(psds=event_psds), "event")
        self._apply(_unfinished_psd_blueprint("StillRunningPSD"), "psd_running")
        self._apply(
            _pe_blueprint("Bilby_Waiting", needs=["StillRunningPSD"]), "pe_waiting"
        )

        event = self.ledger.get_event("GW150914_095045")[0]
        analysis = {p.name: p for p in event.productions}["Bilby_Waiting"]

        self.assertEqual(analysis.psds, {})
        with self.assertRaises(DescriptionException):
            check_psds_available(analysis, logging.getLogger("test"))

    def test_dependency_without_xml_psds_passes_build_time_check(self):
        """A finished PSD dependency which provides ascii PSDs but an empty
        `xml psds` (asimov-bayeswave without `convert_psd_ascii2xml`) is a
        normal situation, and must not block the build. The event-level
        `xml psds` are not mixed in: the dependency is the analysis's PSD
        source."""
        event_xml_psds = {"H1": "/tmp/event-H1.xml", "L1": "/tmp/event-L1.xml"}
        self._apply(_event_blueprint(xml_psds=event_xml_psds), "event")
        self._apply(
            _psd_blueprint("BayesWavePSD", "fakebayeswavelikepipeline"), "psd_bw"
        )
        self._apply(_pe_blueprint("Bilby_BW", needs=["BayesWavePSD"]), "pe_bw")

        event = self.ledger.get_event("GW150914_095045")[0]
        productions = {p.name: p for p in event.productions}
        analysis = productions["Bilby_BW"]

        dep_psds = productions["BayesWavePSD"].pipeline.collect_assets()["psds"]
        self.assertEqual(analysis.psds, dep_psds)
        self.assertEqual(analysis.xml_psds, {})
        # Should not raise.
        check_psds_available(analysis, logging.getLogger("test"))
