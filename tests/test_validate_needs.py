"""
Tests for the validate_needs() method on the Analysis class.
"""
import os
import shutil
import unittest
import warnings
from importlib import reload
from unittest.mock import patch

from click.testing import CliRunner

import asimov
from asimov.ledger import YAMLLedger
from asimov.cli.project import make_project
from asimov.cli.application import apply_page
from asimov.cli import manage


class ValidateNeedsTests(unittest.TestCase):
    """Tests for Analysis.validate_needs()."""

    @classmethod
    def setUpClass(cls):
        cls.cwd = os.getcwd()

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls.cwd)

    def setUp(self):
        os.makedirs(f"{self.cwd}/tests/tmp/validate_needs_project", exist_ok=True)
        os.chdir(f"{self.cwd}/tests/tmp/validate_needs_project")
        make_project(
            name="Test project",
            root=f"{self.cwd}/tests/tmp/validate_needs_project",
            engine="yamlfile",
        )
        self.ledger = YAMLLedger(".asimov/ledger.yml")
        apply_page(file=f"{self.cwd}/tests/test_data/testing_pe.yaml", event=None, ledger=self.ledger)
        apply_page(file=f"{self.cwd}/tests/test_data/events_blueprint.yaml", ledger=self.ledger)

    def tearDown(self):
        del self.ledger
        shutil.rmtree(f"{self.cwd}/tests/tmp/validate_needs_project")

    def test_no_warning_when_no_required_inputs(self):
        """validate_needs() raises no warning when pipeline has no required inputs."""
        blueprint = """
kind: analysis
name: Prod0
pipeline: simpletestpipeline
status: uploaded
"""
        with open("test_no_required.yaml", "w") as f:
            f.write(blueprint)

        apply_page(file="test_no_required.yaml", event="GW150914_095045", ledger=self.ledger)
        event = self.ledger.get_event("GW150914_095045")[0]

        prod0 = [p for p in event.productions if p.name == "Prod0"][0]

        # Pipeline has no required_inputs by default, so no warnings should be raised
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            prod0.validate_needs()
        self.assertEqual(len(caught), 0)

    def test_warning_when_requirement_not_satisfied(self):
        """validate_needs() warns when a required input has no dependency providing it."""
        blueprint = """
kind: analysis
name: Prod0
pipeline: simpletestpipeline
status: uploaded
---
kind: analysis
name: Prod1
pipeline: simpletestpipeline
needs:
  - Prod0
"""
        with open("test_unsatisfied.yaml", "w") as f:
            f.write(blueprint)

        apply_page(file="test_unsatisfied.yaml", event="GW150914_095045", ledger=self.ledger)
        event = self.ledger.get_event("GW150914_095045")[0]

        prod1 = [p for p in event.productions if p.name == "Prod1"][0]

        # Temporarily patch the pipeline to declare a required input
        with patch.object(prod1.pipeline, "required_inputs", ["psd"]):
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                prod1.validate_needs()
            user_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
            self.assertEqual(len(user_warnings), 1)
            self.assertIn("psd", str(user_warnings[0].message))
            self.assertIn("no dependency provides it", str(user_warnings[0].message))

    def test_no_warning_when_requirement_satisfied(self):
        """validate_needs() raises no warning when a dependency provides the required input."""
        blueprint = """
kind: analysis
name: Prod0
pipeline: simpletestpipeline
status: uploaded
---
kind: analysis
name: Prod1
pipeline: simpletestpipeline
needs:
  - Prod0
"""
        with open("test_satisfied.yaml", "w") as f:
            f.write(blueprint)

        apply_page(file="test_satisfied.yaml", event="GW150914_095045", ledger=self.ledger)
        event = self.ledger.get_event("GW150914_095045")[0]

        prod0 = [p for p in event.productions if p.name == "Prod0"][0]
        prod1 = [p for p in event.productions if p.name == "Prod1"][0]

        # Prod1 requires "psd"; Prod0 declares it produces "psd"
        with patch.object(prod1.pipeline, "required_inputs", ["psd"]), \
             patch.object(prod0.pipeline, "available_outputs", ["psd"]):
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                prod1.validate_needs()
            user_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
            self.assertEqual(len(user_warnings), 0)

    def test_get_actual_inputs_returns_required_inputs(self):
        """Pipeline.get_actual_inputs() returns the required_inputs class attribute by default."""
        blueprint = """
kind: analysis
name: Prod0
pipeline: simpletestpipeline
status: ready
"""
        with open("test_actual_inputs.yaml", "w") as f:
            f.write(blueprint)

        apply_page(file="test_actual_inputs.yaml", event="GW150914_095045", ledger=self.ledger)
        event = self.ledger.get_event("GW150914_095045")[0]
        prod0 = [p for p in event.productions if p.name == "Prod0"][0]

        # Both of these are dependency-graph-satisfiable products (unlike, say,
        # externally-sourced frame files - see the "Declaring pipeline inputs
        # and outputs" section of pipelines-dev.rst for why that distinction
        # matters for what belongs in required_inputs).
        with patch.object(prod0.pipeline, "required_inputs", ["psd", "calibration"]):
            result = prod0.pipeline.get_actual_inputs(prod0)
            self.assertEqual(result, ["psd", "calibration"])

    def test_get_actual_outputs_returns_available_outputs(self):
        """Pipeline.get_actual_outputs() returns the available_outputs class attribute by default."""
        blueprint = """
kind: analysis
name: Prod0
pipeline: simpletestpipeline
status: uploaded
"""
        with open("test_actual_outputs.yaml", "w") as f:
            f.write(blueprint)

        apply_page(file="test_actual_outputs.yaml", event="GW150914_095045", ledger=self.ledger)
        event = self.ledger.get_event("GW150914_095045")[0]
        prod0 = [p for p in event.productions if p.name == "Prod0"][0]

        with patch.object(prod0.pipeline, "available_outputs", ["psd", "calibration"]):
            result = prod0.pipeline.get_actual_outputs(prod0)
            self.assertEqual(result, ["psd", "calibration"])

    def test_multiple_requirements_partial_satisfaction(self):
        """validate_needs() warns only for unsatisfied requirements."""
        blueprint = """
kind: analysis
name: PSD
pipeline: simpletestpipeline
status: uploaded
---
kind: analysis
name: PE
pipeline: simpletestpipeline
needs:
  - PSD
"""
        with open("test_partial.yaml", "w") as f:
            f.write(blueprint)

        apply_page(file="test_partial.yaml", event="GW150914_095045", ledger=self.ledger)
        event = self.ledger.get_event("GW150914_095045")[0]

        psd_prod = [p for p in event.productions if p.name == "PSD"][0]
        pe_prod = [p for p in event.productions if p.name == "PE"][0]

        # PE requires psd and calibration; PSD only provides psd
        with patch.object(pe_prod.pipeline, "required_inputs", ["psd", "calibration"]), \
             patch.object(psd_prod.pipeline, "available_outputs", ["psd"]):
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                pe_prod.validate_needs()
            user_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
            # Only calibration is unsatisfied
            self.assertEqual(len(user_warnings), 1)
            self.assertIn("calibration", str(user_warnings[0].message))

    def test_project_analysis_validate_needs_does_not_crash(self):
        """
        validate_needs() must not crash for ProjectAnalysis, which has no
        singular `event` attribute (it operates across multiple subjects via
        `events`/`subjects` instead). This exercises both the name-based
        `needs` dependency graph and the class's own outputs.
        """
        from asimov.pipelines.testing.simple import SimpleTestPipeline
        from asimov.pipelines.testing.project import ProjectTestPipeline

        blueprint = """
kind: analysis
name: Prod0
pipeline: simpletestpipeline
status: uploaded
"""
        with open("test_project_prod0.yaml", "w") as f:
            f.write(blueprint)
        apply_page(file="test_project_prod0.yaml", event="GW150914_095045", ledger=self.ledger)

        pa_blueprint = """
kind: ProjectAnalysis
name: pop-study
pipeline: projecttestpipeline
status: ready
subjects:
  - GW150914_095045
needs:
  - Prod0
"""
        with open("test_project_pa.yaml", "w") as f:
            f.write(pa_blueprint)
        apply_page(file="test_project_pa.yaml", ledger=self.ledger)

        # `pop_study.pipeline` (a ProjectTestPipeline instance) is only
        # constructed after `ledger.project_analyses` is (re-)read below, and
        # `validate_needs()` also queries dependency pipelines it resolves
        # itself - so, unlike the single-event tests above, there is no
        # single already-constructed instance to patch.object() on. The class
        # attributes have to be patched instead, since every instance
        # constructed while the patch is active shares them.
        with patch.object(ProjectTestPipeline, "required_inputs", ["psd"]):
            # Unsatisfied: Prod0 (via SimpleTestPipeline) advertises no outputs.
            with patch.object(SimpleTestPipeline, "available_outputs", []):
                ledger = YAMLLedger(".asimov/ledger.yml")
                pop_study = [a for a in ledger.project_analyses if a.name == "pop-study"][0]
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter("always")
                    pop_study.validate_needs()
                user_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
                self.assertEqual(len(user_warnings), 1)
                self.assertIn("psd", str(user_warnings[0].message))

            # Satisfied: Prod0 now advertises the "psd" output.
            with patch.object(SimpleTestPipeline, "available_outputs", ["psd"]):
                ledger = YAMLLedger(".asimov/ledger.yml")
                pop_study = [a for a in ledger.project_analyses if a.name == "pop-study"][0]
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter("always")
                    pop_study.validate_needs()
                user_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
                self.assertEqual(len(user_warnings), 0)

    def test_project_analysis_validate_needs_repeatable_on_same_instance(self):
        """
        Calling validate_needs() more than once on the same ProjectAnalysis
        instance must not crash. ProjectAnalysis.dependencies re-queries the
        ledger for its subjects on every access, and a second, independent
        reconstruction of an event that already has productions can raise
        AttributeError deep inside Event's own initialisation - so
        _dependency_analyses() must cache its result per instance rather
        than re-reading `dependencies` on every call.
        """
        from asimov.pipelines.testing.simple import SimpleTestPipeline
        from asimov.pipelines.testing.project import ProjectTestPipeline

        blueprint = """
kind: analysis
name: Prod0
pipeline: simpletestpipeline
status: uploaded
"""
        with open("test_repeat_prod0.yaml", "w") as f:
            f.write(blueprint)
        apply_page(file="test_repeat_prod0.yaml", event="GW150914_095045", ledger=self.ledger)

        pa_blueprint = """
kind: ProjectAnalysis
name: pop-study-repeat
pipeline: projecttestpipeline
status: ready
subjects:
  - GW150914_095045
needs:
  - Prod0
"""
        with open("test_repeat_pa.yaml", "w") as f:
            f.write(pa_blueprint)
        apply_page(file="test_repeat_pa.yaml", ledger=self.ledger)

        with patch.object(ProjectTestPipeline, "required_inputs", ["psd"]), \
             patch.object(SimpleTestPipeline, "available_outputs", []):
            ledger = YAMLLedger(".asimov/ledger.yml")
            pop_study = [a for a in ledger.project_analyses if a.name == "pop-study-repeat"][0]

            for _ in range(3):
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter("always")
                    pop_study.validate_needs()
                user_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
                self.assertEqual(len(user_warnings), 1)
                self.assertIn("psd", str(user_warnings[0].message))

    def test_project_analysis_validate_needs_safe_after_prior_dependencies_read(self):
        """
        validate_needs() must not crash when something else has already read
        `.dependencies` on the same ProjectAnalysis instance first.

        `_dependency_analyses()` caching its own result only protects repeat
        calls to that method - it does nothing for a caller (to_dict(), for
        instance, which serialises `self.dependencies` into `needs`) that
        reads the `dependencies` property directly before validate_needs()
        is ever called. That property has to be safe to call more than once
        in its own right; this exercises exactly that sequence.
        """
        from asimov.pipelines.testing.project import ProjectTestPipeline

        blueprint = """
kind: analysis
name: Prod0
pipeline: simpletestpipeline
status: uploaded
"""
        with open("test_prior_read_prod0.yaml", "w") as f:
            f.write(blueprint)
        apply_page(file="test_prior_read_prod0.yaml", event="GW150914_095045", ledger=self.ledger)

        pa_blueprint = """
kind: ProjectAnalysis
name: pop-study-prior-read
pipeline: projecttestpipeline
status: ready
subjects:
  - GW150914_095045
needs:
  - Prod0
"""
        with open("test_prior_read_pa.yaml", "w") as f:
            f.write(pa_blueprint)
        apply_page(file="test_prior_read_pa.yaml", ledger=self.ledger)

        with patch.object(ProjectTestPipeline, "required_inputs", ["psd"]):
            ledger = YAMLLedger(".asimov/ledger.yml")
            pop_study = [a for a in ledger.project_analyses if a.name == "pop-study-prior-read"][0]

            # A prior, unrelated read of `dependencies` (as to_dict() does,
            # e.g. when the ledger is saved) before validate_needs() is ever
            # called on this instance.
            self.assertEqual(pop_study.to_dict()["needs"], ["Prod0"])

            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                pop_study.validate_needs()
            user_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
            self.assertEqual(len(user_warnings), 1)
            self.assertIn("psd", str(user_warnings[0].message))

    def test_subject_analysis_validate_needs_uses_resolved_analyses(self):
        """
        SubjectAnalysis always has an empty `needs`/`dependencies` (it does not
        participate in that graph), and instead resolves its dependencies via
        the smart `analyses` spec into `self.analyses`. validate_needs() must
        consult that list rather than reporting every requirement as
        unsatisfied.
        """
        blueprint = """
kind: analysis
name: Prod0
pipeline: simpletestpipeline
status: uploaded
"""
        with open("test_subject_prod0.yaml", "w") as f:
            f.write(blueprint)
        apply_page(file="test_subject_prod0.yaml", event="GW150914_095045", ledger=self.ledger)

        subject_blueprint = """
kind: analysis
name: Combined
pipeline: subjecttestpipeline
status: ready
analyses:
  - Prod0
"""
        with open("test_subject_combined.yaml", "w") as f:
            f.write(subject_blueprint)
        apply_page(file="test_subject_combined.yaml", event="GW150914_095045", ledger=self.ledger)

        event = self.ledger.get_event("GW150914_095045")[0]
        prod0 = [p for p in event.productions if p.name == "Prod0"][0]
        combined = [p for p in event.productions if p.name == "Combined"][0]
        self.assertIn(prod0, combined.analyses)

        with patch.object(combined.pipeline, "required_inputs", ["psd"]):
            # Unsatisfied: Prod0 does not (yet) advertise "psd".
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                combined.validate_needs()
            user_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
            self.assertEqual(len(user_warnings), 1)
            self.assertIn("psd", str(user_warnings[0].message))

            # Satisfied: Prod0 advertises "psd", which Combined resolves via
            # its smart `analyses` spec rather than the `needs` graph.
            with patch.object(prod0.pipeline, "available_outputs", ["psd"]):
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter("always")
                    combined.validate_needs()
                user_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
                self.assertEqual(len(user_warnings), 0)

    def test_build_cli_surfaces_unsatisfied_dependency(self):
        """
        `asimov manage build` should run validate_needs() ahead of building
        each production's configuration and surface any unsatisfied
        requirement to the user, without aborting the build.
        """
        blueprint = """
kind: analysis
name: Prod0
pipeline: simpletestpipeline
status: uploaded
---
kind: analysis
name: Prod1
pipeline: simpletestpipeline
needs:
  - Prod0
"""
        with open("test_build_cli.yaml", "w") as f:
            f.write(blueprint)
        apply_page(file="test_build_cli.yaml", event="GW150914_095045", ledger=self.ledger)

        # `build` loads its own fresh ledger/pipeline instances, so the
        # requirement has to be declared on the pipeline class itself for the
        # CLI invocation below to see it (Prod0 will also trivially warn,
        # since it declares the same required input and has no dependency at
        # all; that doesn't affect what's being checked here).
        from asimov.pipelines.testing.simple import SimpleTestPipeline

        with patch.object(SimpleTestPipeline, "required_inputs", ["psd"]):
            with patch("asimov.current_ledger", new=YAMLLedger(".asimov/ledger.yml")):
                reload(asimov)
                reload(manage)
                runner = CliRunner()
                result = runner.invoke(manage.manage, ["build", "--event", "GW150914_095045"])
            self.assertIn("requires 'psd' but no dependency provides it", result.output)
            self.assertIn("Prod1", result.output)
            # The build should still proceed rather than aborting.
            self.assertTrue(
                os.path.exists(
                    os.path.join(
                        "checkouts", "GW150914_095045", "analyses", "Prod1.ini"
                    )
                )
            )

    def test_no_warning_when_no_dependencies(self):
        """validate_needs() raises no warning when pipeline has no required inputs and no deps."""
        blueprint = """
kind: analysis
name: Standalone
pipeline: simpletestpipeline
status: ready
"""
        with open("test_standalone.yaml", "w") as f:
            f.write(blueprint)

        apply_page(file="test_standalone.yaml", event="GW150914_095045", ledger=self.ledger)
        event = self.ledger.get_event("GW150914_095045")[0]
        standalone = [p for p in event.productions if p.name == "Standalone"][0]

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            standalone.validate_needs()
        user_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
        self.assertEqual(len(user_warnings), 0)


if __name__ == "__main__":
    unittest.main()
