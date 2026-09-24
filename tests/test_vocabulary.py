"""
Tests for the ledger vocabulary (asimov.vocabulary).
"""

import glob
import os
import tempfile
import unittest
from unittest import mock

import yaml
from click.testing import CliRunner

from asimov import blueprints
from asimov import vocabulary as vocabulary_module
from asimov.cli.vocabulary import vocabulary as vocabulary_cli
from asimov.vocabulary import TERM_TYPES, Vocabulary, get_vocabulary

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))


class CoreVocabularyTests(unittest.TestCase):
    def setUp(self):
        self.vocabulary = Vocabulary.core()

    def test_every_term_is_described(self):
        for term in self.vocabulary.terms():
            self.assertTrue(term.description, term.dotted)
            self.assertIn(term.type, TERM_TYPES, term.dotted)

    def test_deprecations_point_at_real_terms(self):
        for term in self.vocabulary.terms():
            if term.replaced_by:
                self.assertIsNotNone(
                    self.vocabulary.lookup(term.replaced_by),
                    f"{term.dotted} is replaced by an unknown term",
                )

    def test_lookup(self):
        term = self.vocabulary.lookup("likelihood.minimum frequency")
        self.assertEqual(term.units, "Hz")
        self.assertTrue(term.per_ifo)
        self.assertIsNone(self.vocabulary.lookup("likelihood.not a term"))

    def test_lookup_follows_aliases(self):
        term = self.vocabulary.lookup("likelihood.marginalisation.distance")
        self.assertEqual(term.dotted, "likelihood.marginalization.distance")

    def test_lookup_through_pipelines_overlay(self):
        term = self.vocabulary.lookup("pipelines.bilby.scheduler.request cpus")
        self.assertEqual(term.dotted, "scheduler.request cpus")

    def test_blueprint_models_are_in_the_vocabulary(self):
        """The pydantic blueprint models must not drift from the vocabulary."""
        models = {
            "waveform": blueprints.Waveform,
            "likelihood": blueprints.Likelihood,
            "likelihood.marginalization": blueprints.Marginalisation,
            "likelihood.roq": blueprints.ROQ,
            "likelihood.relative binning": blueprints.RelativeBinning,
            "likelihood.calibration": blueprints.Calibration,
            "": blueprints.Subject,
        }
        for section, model in models.items():
            for name, field in model.model_fields.items():
                key = field.alias or name
                path = f"{section}.{key}" if section else key
                self.assertIsNotNone(
                    self.vocabulary.lookup(path), f"{path} ({model.__name__})"
                )

    def test_reference_blueprints_only_use_known_terms(self):
        files = glob.glob(
            os.path.join(TESTS_DIR, "test_data", "**", "*.yaml"), recursive=True
        ) + glob.glob(os.path.join(TESTS_DIR, "test_blueprints", "*.yaml"))
        checked = 0
        for path in files:
            try:
                findings = self.vocabulary.check_file(path)
            except yaml.YAMLError:
                continue
            checked += 1
            problems = [
                str(f) for f in findings if f.kind in {"unknown", "duplicate", "type"}
            ]
            self.assertEqual(problems, [], path)
        self.assertGreater(checked, 10)


class CheckTests(unittest.TestCase):
    def setUp(self):
        self.vocabulary = Vocabulary.core()

    def kinds(self, document, **kwargs):
        return {
            f.dotted: (f.kind, f.suggestion)
            for f in self.vocabulary.check(document, **kwargs)
        }

    def test_clean_document(self):
        document = {
            "kind": "analysis",
            "name": "Prod0",
            "pipeline": "bilby",
            "interferometers": ["H1", "L1"],
            "waveform": {"approximant": "IMRPhenomXPHM", "reference frequency": 20},
            "likelihood": {"minimum frequency": {"H1": 20}, "sample rate": 2048},
            "scheduler": {"accounting group": "x", "request cpus": 4},
            "sampler": {"sampler": "dynesty", "sampler kwargs": {"nlive": 1000}},
            "priors": {"chirp mass": {"minimum": 1, "maximum": 2}},
        }
        self.assertEqual(self.vocabulary.check(document), [])

    def test_unknown_key_in_section_suggests_sibling(self):
        found = self.kinds({"scheduler": {"cpus": 4, "gpus": 1}})
        self.assertEqual(found["scheduler.cpus"], ("unknown", "scheduler.request cpus"))
        self.assertEqual(found["scheduler.gpus"], ("unknown", "scheduler.request gpus"))

    def test_unknown_key_suggests_from_synonym(self):
        found = self.kinds({"waveform": {"f_ref": 20}})
        self.assertEqual(
            found["waveform.f_ref"], ("unknown", "waveform.reference frequency")
        )

    def test_unknown_key_suggests_close_spelling(self):
        found = self.kinds({"likelihood": {"sample rte": 2048}})
        self.assertEqual(
            found["likelihood.sample rte"], ("unknown", "likelihood.sample rate")
        )

    def test_pipeline_namespace_duplicates(self):
        document = {
            "pipeline": "jim",
            "jim": {
                "data": {"psd_files": {"H1": "h1.txt"}, "psd_is_asd": {}},
                "prior": {"chirp mass": {}},
                "sampling": {"n_chains": 10},
            },
        }
        found = self.kinds(document)
        self.assertEqual(found["jim.data.psd_files"], ("duplicate", "psds"))
        self.assertEqual(found["jim.prior"], ("duplicate", "priors"))
        self.assertNotIn("jim.sampling", found)
        self.assertNotIn("jim.data.psd_is_asd", found)

    def test_pipeline_namespace_is_case_insensitive(self):
        found = self.kinds({"pipeline": "Jim", "jim": {"f_ref": 20}})
        self.assertEqual(
            found["jim.f_ref"], ("duplicate", "waveform.reference frequency")
        )

    def test_duplicates_prefer_current_terms(self):
        found = self.kinds({"pipeline": "x", "x": {"sample_rate": 4096}})
        self.assertEqual(
            found["x.sample_rate"], ("duplicate", "likelihood.sample rate")
        )

    def test_other_pipelines_namespace_is_unknown(self):
        found = self.kinds({"pipeline": "bilby", "jim": {}})
        self.assertEqual(found["jim"][0], "unknown")

    def test_alias(self):
        found = self.kinds({"likelihood": {"window-length": 4}})
        self.assertEqual(
            found["likelihood.window-length"], ("alias", "likelihood.window length")
        )

    def test_deprecated(self):
        found = self.kinds({"quality": {"minimum frequency": {"H1": 20}}})
        self.assertEqual(
            found["quality.minimum frequency"],
            ("deprecated", "likelihood.minimum frequency"),
        )

    def test_foreign(self):
        found = self.kinds({"likelihood": {"iterations": 10}}, pipeline="bilby")
        self.assertEqual(found["likelihood.iterations"][0], "foreign")
        self.assertEqual(
            self.kinds({"likelihood": {"iterations": 10}}, pipeline="bayeswave"), {}
        )

    def test_section_given_scalar(self):
        found = self.kinds({"likelihood": 4})
        self.assertEqual(found["likelihood"][0], "type")

    def test_leaf_types_are_checked(self):
        found = self.kinds(
            {
                "scheduler": {"request cpus": "four"},
                "waveform": {"approximant": 1},
                "likelihood": {"minimum frequency": 20},
                "interferometers": "H1,L1",
            }
        )
        self.assertEqual(found["scheduler.request cpus"][0], "type")
        self.assertEqual(found["waveform.approximant"][0], "type")
        self.assertEqual(found["likelihood.minimum frequency"][0], "type")
        self.assertEqual(found["interferometers"][0], "type")

    def test_valid_leaf_types_pass(self):
        document = {
            "scheduler": {"request cpus": 4, "request memory": 1024},
            "likelihood": {"minimum frequency": {"H1": 20, "L1": 20.5}},
            "data": {"segment length": 4.0},
            "sampler": {"sampler kwargs": "{nlive: 100}"},
        }
        self.assertEqual(self.vocabulary.check(document), [])

    def test_ledger_documents_are_checked(self):
        ledger = {
            "asimov": {"version": "0.8"},
            "project": {"name": "test"},
            "project analyses": [],
            "events": [
                {
                    "name": "GW150914",
                    "interferometers": ["H1", "L1"],
                    "productions": [
                        {"Prod0": None},
                        {
                            "name": "Prod1",
                            "pipeline": "bilby",
                            "scheduler": {"cpus": 4},
                        },
                    ],
                }
            ],
        }
        ledger["events"][0]["productions"].append(
            {"Prod2": {"pipeline": "bilby", "waveform": {"f_ref": 20}}}
        )
        found = self.kinds(ledger)
        self.assertEqual(
            found["events.0.productions.2.Prod2.waveform.f_ref"],
            ("unknown", "waveform.reference frequency"),
        )
        del found["events.0.productions.2.Prod2.waveform.f_ref"]
        self.assertEqual(
            found["events.0.productions.1.scheduler.cpus"],
            ("unknown", "scheduler.request cpus"),
        )
        self.assertEqual(len(found), 1)

    def test_legacy_hyphenated_quality_keys(self):
        findings = self.vocabulary.check(
            {"quality": {"sample-rate": 2048, "high-frequency": 896}}
        )
        found = {(f.dotted, f.kind, f.suggestion) for f in findings}
        self.assertIn(("quality.sample-rate", "alias", "quality.sample rate"), found)
        self.assertIn(
            ("quality.sample-rate", "deprecated", "likelihood.sample rate"), found
        )
        self.assertIn(
            ("quality.high-frequency", "deprecated", "likelihood.maximum frequency"),
            found,
        )
        self.assertFalse([f for f in findings if f.kind == "unknown"])

    def test_accounting_group_user(self):
        self.assertEqual(self.kinds({"scheduler": {"accounting group user": "x"}}), {})

    def test_pipelines_overlay_is_checked(self):
        found = self.kinds(
            {"pipelines": {"bilby": {"scheduler": {"cpus": 4}}}}
        )
        self.assertEqual(
            found["pipelines.bilby.scheduler.cpus"],
            ("unknown", "scheduler.request cpus"),
        )

    def test_open_sections_are_not_checked(self):
        document = {
            "sampler": {"sampler kwargs": {"anything": 1}},
            "priors": {"made up parameter": {"minimum": 0}},
            "strategy": {"waveform.approximant": ["A", "B"]},
        }
        self.assertEqual(self.vocabulary.check(document), [])


class PluginVocabularyTests(unittest.TestCase):
    plugin = {
        "terms": {
            "mypipeline": {
                "description": "Settings only mypipeline understands.",
                "children": {
                    "chains": {"type": "integer", "description": "Chain count."},
                },
            },
            "sampler": {
                "children": {
                    "temperature ladder": {
                        "type": "list",
                        "description": "Parallel-tempering ladder.",
                    }
                }
            },
        },
        "assets": {"trace": {"description": "The sampler trace."}},
    }

    def test_merge_adds_owned_terms(self):
        vocabulary = Vocabulary.core()
        vocabulary.merge(self.plugin, owner="mypipeline")
        vocabulary.plugins.append("mypipeline")
        term = vocabulary.lookup("sampler.temperature ladder")
        self.assertEqual(term.owner, "mypipeline")
        self.assertEqual(vocabulary.lookup("mypipeline.chains").owner, "mypipeline")
        self.assertIn("trace", vocabulary.assets)
        self.assertEqual(vocabulary.conflicts, [])
        self.assertEqual(
            vocabulary.check(
                {"pipeline": "mypipeline", "mypipeline": {"chains": 4}}
            ),
            [],
        )
        found = {
            f.dotted: f.kind
            for f in vocabulary.check(
                {"pipeline": "other", "sampler": {"temperature ladder": [1]}}
            )
        }
        self.assertEqual(found["sampler.temperature ladder"], "foreign")

    def test_redefinition_is_a_conflict(self):
        vocabulary = Vocabulary.core()
        vocabulary.merge(
            {"terms": {"psds": {"description": "Mine now."}}}, owner="greedy"
        )
        self.assertIn(("psds", "greedy"), vocabulary.conflicts)
        self.assertIsNone(vocabulary.lookup("psds").owner)

    def test_children_cannot_extend_scalar_terms(self):
        vocabulary = Vocabulary.core()
        vocabulary.merge(
            {"terms": {"psds": {"children": {"foo": {"description": "x"}}}}},
            owner="greedy",
        )
        self.assertIn(("psds", "greedy"), vocabulary.conflicts)
        self.assertEqual(vocabulary.lookup("psds").children, {})

    def test_plugin_term_duplicating_core(self):
        vocabulary = Vocabulary.core()
        vocabulary.merge(
            {
                "terms": {
                    "greedy": {
                        "description": "x",
                        "children": {"psd_files": {"description": "PSDs."}},
                    }
                }
            },
            owner="greedy",
        )
        vocabulary.plugins.append("greedy")
        found = vocabulary.duplicates()
        self.assertEqual([f.suggestion for f in found], ["psds"])

    def test_entry_point_loading(self):
        entry_point = mock.Mock()
        entry_point.name = "mypipeline"
        entry_point.load.return_value = lambda: self.plugin
        with mock.patch.object(
            vocabulary_module, "entry_points", return_value=[entry_point]
        ):
            vocabulary = get_vocabulary(refresh=True)
        self.assertEqual(vocabulary.plugins, ["mypipeline"])
        self.assertEqual(vocabulary.lookup("mypipeline.chains").owner, "mypipeline")
        get_vocabulary(refresh=True)

    def test_entry_point_yaml_path(self):
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as handle:
            yaml.safe_dump(self.plugin, handle)
        try:
            data = vocabulary_module._resolve_plugin_vocabulary(handle.name)
        finally:
            os.unlink(handle.name)
        self.assertIn("mypipeline", data["terms"])


class VocabularyCLITests(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()
        self.directory = tempfile.mkdtemp()

    def write(self, name, document):
        path = os.path.join(self.directory, name)
        with open(path, "w") as handle:
            yaml.safe_dump(document, handle)
        return path

    def test_check_passes(self):
        path = self.write("ok.yaml", {"kind": "analysis", "waveform": {"approximant": "X"}})
        result = self.runner.invoke(vocabulary_cli, ["check", path])
        self.assertEqual(result.exit_code, 0, result.output)

    def test_check_fails_on_unknown(self):
        path = self.write("bad.yaml", {"scheduler": {"cpus": 4}})
        result = self.runner.invoke(vocabulary_cli, ["check", path])
        self.assertEqual(result.exit_code, 1)
        self.assertIn("request cpus", result.output)

    def test_check_strict_fails_on_deprecated(self):
        path = self.write("old.yaml", {"approximant": "X"})
        self.assertEqual(
            self.runner.invoke(vocabulary_cli, ["check", path]).exit_code, 0
        )
        self.assertEqual(
            self.runner.invoke(vocabulary_cli, ["check", "--strict", path]).exit_code,
            1,
        )

    def test_check_json(self):
        path = self.write("bad.yaml", {"scheduler": {"cpus": 4}})
        result = self.runner.invoke(vocabulary_cli, ["check", "--json", path])
        data = yaml.safe_load(result.output)
        self.assertEqual(data[path][0]["suggestion"], "scheduler.request cpus")

    def test_show_and_export(self):
        result = self.runner.invoke(vocabulary_cli, ["show", "psds"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("_collect_psds", result.output)
        result = self.runner.invoke(vocabulary_cli, ["show", "scheduler.cpus"])
        self.assertEqual(result.exit_code, 1)
        result = self.runner.invoke(vocabulary_cli, ["export", "--format", "json"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn('"assets"', result.output)


if __name__ == "__main__":
    unittest.main()
