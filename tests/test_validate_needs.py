"""
Tests for the validate_needs() method on the Analysis class.
"""
import os
import shutil
import unittest
import warnings

from asimov.ledger import YAMLLedger
from asimov.cli.project import make_project
from asimov.cli.application import apply_page


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
        make_project(name="Test project", root=f"{self.cwd}/tests/tmp/validate_needs_project")
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
pipeline: bayeswave
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
pipeline: bayeswave
status: uploaded
---
kind: analysis
name: Prod1
pipeline: bilby
needs:
  - Prod0
"""
        with open("test_unsatisfied.yaml", "w") as f:
            f.write(blueprint)

        apply_page(file="test_unsatisfied.yaml", event="GW150914_095045", ledger=self.ledger)
        event = self.ledger.get_event("GW150914_095045")[0]

        prod1 = [p for p in event.productions if p.name == "Prod1"][0]

        # Temporarily patch the pipeline to declare a required input
        original_required = prod1.pipeline.required_inputs
        prod1.pipeline.required_inputs = ["psd"]
        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                prod1.validate_needs()
            user_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
            self.assertEqual(len(user_warnings), 1)
            self.assertIn("psd", str(user_warnings[0].message))
            self.assertIn("no dependency provides it", str(user_warnings[0].message))
        finally:
            prod1.pipeline.required_inputs = original_required

    def test_no_warning_when_requirement_satisfied(self):
        """validate_needs() raises no warning when a dependency provides the required input."""
        blueprint = """
kind: analysis
name: Prod0
pipeline: bayeswave
status: uploaded
---
kind: analysis
name: Prod1
pipeline: bilby
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
        original_required = prod1.pipeline.required_inputs
        original_available = prod0.pipeline.available_outputs
        prod1.pipeline.required_inputs = ["psd"]
        prod0.pipeline.available_outputs = ["psd"]
        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                prod1.validate_needs()
            user_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
            self.assertEqual(len(user_warnings), 0)
        finally:
            prod1.pipeline.required_inputs = original_required
            prod0.pipeline.available_outputs = original_available

    def test_get_actual_inputs_returns_required_inputs(self):
        """Pipeline.get_actual_inputs() returns the required_inputs class attribute by default."""
        blueprint = """
kind: analysis
name: Prod0
pipeline: bilby
status: ready
"""
        with open("test_actual_inputs.yaml", "w") as f:
            f.write(blueprint)

        apply_page(file="test_actual_inputs.yaml", event="GW150914_095045", ledger=self.ledger)
        event = self.ledger.get_event("GW150914_095045")[0]
        prod0 = [p for p in event.productions if p.name == "Prod0"][0]

        original_required = prod0.pipeline.required_inputs
        prod0.pipeline.required_inputs = ["frame_files", "psd"]
        try:
            result = prod0.pipeline.get_actual_inputs(prod0)
            self.assertEqual(result, ["frame_files", "psd"])
        finally:
            prod0.pipeline.required_inputs = original_required

    def test_get_actual_outputs_returns_available_outputs(self):
        """Pipeline.get_actual_outputs() returns the available_outputs class attribute by default."""
        blueprint = """
kind: analysis
name: Prod0
pipeline: bayeswave
status: uploaded
"""
        with open("test_actual_outputs.yaml", "w") as f:
            f.write(blueprint)

        apply_page(file="test_actual_outputs.yaml", event="GW150914_095045", ledger=self.ledger)
        event = self.ledger.get_event("GW150914_095045")[0]
        prod0 = [p for p in event.productions if p.name == "Prod0"][0]

        original_available = prod0.pipeline.available_outputs
        prod0.pipeline.available_outputs = ["psd", "calibration"]
        try:
            result = prod0.pipeline.get_actual_outputs(prod0)
            self.assertEqual(result, ["psd", "calibration"])
        finally:
            prod0.pipeline.available_outputs = original_available

    def test_multiple_requirements_partial_satisfaction(self):
        """validate_needs() warns only for unsatisfied requirements."""
        blueprint = """
kind: analysis
name: PSD
pipeline: bayeswave
status: uploaded
---
kind: analysis
name: PE
pipeline: bilby
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
        original_required = pe_prod.pipeline.required_inputs
        original_available = psd_prod.pipeline.available_outputs
        pe_prod.pipeline.required_inputs = ["psd", "calibration"]
        psd_prod.pipeline.available_outputs = ["psd"]
        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                pe_prod.validate_needs()
            user_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
            # Only calibration is unsatisfied
            self.assertEqual(len(user_warnings), 1)
            self.assertIn("calibration", str(user_warnings[0].message))
        finally:
            pe_prod.pipeline.required_inputs = original_required
            psd_prod.pipeline.available_outputs = original_available

    def test_no_warning_when_no_dependencies(self):
        """validate_needs() raises no warning when pipeline has no required inputs and no deps."""
        blueprint = """
kind: analysis
name: Standalone
pipeline: bilby
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
