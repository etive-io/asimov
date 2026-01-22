"""
These tests are designed to ensure that all classes of data in the
yaml 'blueprints' are correctly applied to the asimov ledger, and are
then correctly used to make config files.
"""

import os
import unittest
import shutil
import git
import asimov.event
from asimov.cli.project import make_project
from asimov.cli.application import apply_page
from asimov.ledger import YAMLLedger
from asimov.testing import AsimovTestCase


class EventTests(AsimovTestCase):
    """
    Tests to ensure that event-related blueprints are handled correctly.
    """
    def test_event_update(self):
        apply_page(
            f"{self.cwd}/tests/test_data/test_event.yaml",
            event="S000000",
            ledger=self.ledger,
        )
        apply_page(
            f"{self.cwd}/tests/test_data/test_analysis_S000000.yaml",
            event="S000000",
            ledger=self.ledger
            )
        Nanalyses_before = len(self.ledger.events['S000000']['productions'])

        apply_page(
            f"{self.cwd}/tests/test_data/test_event_update.yaml",
            event="S000000",
            ledger=self.ledger,
            update_page=True
        )
        Nanalyses_after = len(self.ledger.events['S000000']['productions'])
        self.assertEqual(Nanalyses_before, Nanalyses_after)
        event = self.ledger.events["S000000"]
        self.assertEqual(event['productions'][0]['bilby-IMRPhenomXPHM-QuickTest']['event time'], 900)
        self.assertEqual(event['event time'], 909)
        self.assertEqual(event['priors']['luminosity distance']['maximum'], 1010)
        self.assertEqual(event['priors']['mass ratio']['maximum'], 1.0)

    def test_event_history(self):
        apply_page(
            f"{self.cwd}/tests/test_data/test_event.yaml",
            event="S000000",
            ledger=self.ledger,
        )
        apply_page(
            f"{self.cwd}/tests/test_data/test_analysis_S000000.yaml",
            event="S000000",
            ledger=self.ledger
            )
        apply_page(
            f"{self.cwd}/tests/test_data/test_event_update.yaml",
            event="S000000",
            ledger=self.ledger,
            update_page=True
        )
        event = self.ledger.events["S000000"]
        self.assertTrue("version-1" in self.ledger.data.get("history", {}).get("S000000", {}))
        history = self.ledger.data['history']['S000000']
        self.assertEqual(history['version-1']['event time'],
                         900)
        self.assertEqual(history['version-1']['priors']['luminosity distance']['maximum'], 1000)
        self.assertTrue("date changed" in history['version-1'])
        
    def test_event_update_not_applied_without_flag(self):
        apply_page(
            f"{self.cwd}/tests/test_data/test_event.yaml",
            event="S000000",
            ledger=self.ledger,
        )
        apply_page(
            f"{self.cwd}/tests/test_data/test_analysis_S000000.yaml",
            event="S000000",
            ledger=self.ledger,
            )
        apply_page(
            f"{self.cwd}/tests/test_data/test_event_update.yaml",
            event="S000000",
            ledger=self.ledger,
        )
        event = self.ledger.events["S000000"]
        self.assertFalse("event time" in event['productions'][0])
        self.assertEqual(event['event time'], 900)
        self.assertEqual(event['priors']['luminosity distance']['maximum'], 1000)
        self.assertEqual(event['priors']['mass ratio']['maximum'], 1.0)

        
class DetcharTests(AsimovTestCase):
    """Tests to ensure that various detector characterisation related
    data are handled correctly.
    These should include:
    - minimum frequencies
    - maximum frequencies
    - data channels
    - frame types"""

    def test_event_non_standard_fmin(self):
        """Check event-specific fmin overwrites project default."""
        apply_page(
            f"{self.cwd}/tests/test_data/testing_pe.yaml",
            event=None,
            ledger=self.ledger,
        )
        apply_page(
            f"{self.cwd}/tests/test_data/event_non_standard_settings.yaml",
            event=None,
            ledger=self.ledger,
        )

        event = self.ledger.get_event("Nonstandard fmin")[0]

        self.assertEqual(event.meta["quality"]["minimum frequency"]["H1"], 62)
        self.assertEqual(event.meta["quality"]["minimum frequency"]["L1"], 92)
        self.assertEqual(event.meta["quality"]["minimum frequency"]["V1"], 62)

    def test_event_non_standard_channels(self):
        """Check event-specific channel overwrites project default."""
        apply_page(
            f"{self.cwd}/tests/test_data/testing_pe.yaml",
            event=None,
            ledger=self.ledger,
        )
        apply_page(
            f"{self.cwd}/tests/test_data/event_non_standard_settings.yaml",
            event=None,
            ledger=self.ledger,
        )

        event = self.ledger.get_event("Nonstandard fmin")[0]

        self.assertEqual(event.meta["data"]["channels"]["L1"], "L1:WeirdChannel")
        self.assertEqual(event.meta["data"]["channels"]["H1"], "H1:WeirdChannel")
        self.assertEqual(event.meta["data"]["channels"]["V1"], "V1:OddChannel")

    def test_event_non_standard_frames(self):
        """Check event-specific frame-type overwrites project default."""
        apply_page(
            f"{self.cwd}/tests/test_data/testing_pe.yaml",
            event=None,
            ledger=self.ledger,
        )
        apply_page(
            f"{self.cwd}/tests/test_data/event_non_standard_settings.yaml",
            event=None,
            ledger=self.ledger,
        )

        event = self.ledger.get_event("Nonstandard fmin")[0]

        self.assertEqual(event.meta["data"]["frame types"]["L1"], "NonstandardFrameL1")
        self.assertEqual(event.meta["data"]["frame types"]["H1"], "NonstandardFrame")
        self.assertEqual(event.meta["data"]["frame types"]["V1"], "UnusualFrameType")


class StrategyTests(AsimovTestCase):
    """
    Tests to ensure that strategy blueprints are handled correctly.
    """
    
    def test_single_parameter_strategy(self):
        """Test that a single-parameter strategy creates multiple analyses."""
        # First add the event
        apply_page(
            f"{self.cwd}/tests/test_data/test_strategy_event.yaml",
            ledger=self.ledger,
        )
        
        # Apply the strategy blueprint
        apply_page(
            f"{self.cwd}/tests/test_data/test_strategy_single.yaml",
            event="S000000",
            ledger=self.ledger
        )
        
        event = self.ledger.get_event("S000000")[0]
        
        # Should have created 3 analyses from the strategy
        self.assertEqual(len(event.productions), 3)
        
        # Check that each analysis has the correct waveform
        analysis_names = {prod.name for prod in event.productions}
        expected_names = {
            "bilby-IMRPhenomXPHM",
            "bilby-SEOBNRv4PHM",
            "bilby-IMRPhenomD"
        }
        self.assertEqual(analysis_names, expected_names)
        
        # Check that each analysis has the correct waveform set
        for prod in event.productions:
            if prod.name == "bilby-IMRPhenomXPHM":
                self.assertEqual(prod.meta["waveform"]["approximant"], "IMRPhenomXPHM")
            elif prod.name == "bilby-SEOBNRv4PHM":
                self.assertEqual(prod.meta["waveform"]["approximant"], "SEOBNRv4PHM")
            elif prod.name == "bilby-IMRPhenomD":
                self.assertEqual(prod.meta["waveform"]["approximant"], "IMRPhenomD")
    
    def test_multi_parameter_strategy_matrix(self):
        """Test that a multi-parameter strategy creates all combinations."""
        # First add the event
        apply_page(
            f"{self.cwd}/tests/test_data/test_strategy_event.yaml",
            ledger=self.ledger,
        )
        
        # Apply the strategy blueprint
        apply_page(
            f"{self.cwd}/tests/test_data/test_strategy_matrix.yaml",
            event="S000000",
            ledger=self.ledger
        )
        
        event = self.ledger.get_event("S000000")[0]
        
        # Should have created 4 analyses (2 waveforms x 2 samplers)
        self.assertEqual(len(event.productions), 4)
        
        # Check that each analysis has the correct combination
        analysis_names = {prod.name for prod in event.productions}
        expected_names = {
            "bilby-IMRPhenomXPHM-dynesty",
            "bilby-IMRPhenomXPHM-emcee",
            "bilby-SEOBNRv4PHM-dynesty",
            "bilby-SEOBNRv4PHM-emcee"
        }
        self.assertEqual(analysis_names, expected_names)
        
        # Verify parameter combinations
        for prod in event.productions:
            if "IMRPhenomXPHM" in prod.name:
                self.assertEqual(prod.meta["waveform"]["approximant"], "IMRPhenomXPHM")
            elif "SEOBNRv4PHM" in prod.name:
                self.assertEqual(prod.meta["waveform"]["approximant"], "SEOBNRv4PHM")
            
            if "dynesty" in prod.name:
                self.assertEqual(prod.meta["sampler"]["sampler"], "dynesty")
            elif "emcee" in prod.name:
                self.assertEqual(prod.meta["sampler"]["sampler"], "emcee")
