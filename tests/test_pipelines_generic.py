"""These tests are designed to be run on all pipelines to ensure that
they are generally compliant within asimov's specifications.  They can
include checking that ini files have the correct information and that
the pipelines report information as expected.
"""

import os
import io
import unittest
import shutil
import git
import contextlib

import asimov.event
from asimov.cli.project import make_project
from asimov.cli.application import apply_page
from asimov.ledger import YAMLLedger
from asimov.pipelines import known_pipelines

from asimov.testing import AsimovTestCase
from asimov import config
from asimov.utils import set_directory

exemplar = {
    "bayeswave": {
        "minimum frequency": "62",
        "segment length": "4",
        "psd length": "108.6",
        "ifo list": "['H1', 'L1', 'V1']",
        "segment start": "2",
        "data channels": "{ 'H1':'H1:WeirdChannel','L1':'L1:WeirdChannel','V1':'V1:OddChannel', }",
        "data frames": "{ 'H1':'NonstandardFrame','L1':'NonstandardFrameL1','V1':'UnusualFrameType', }",
        "window length": "71",
    },
    "bilby": {
        "minimum frequency": "{ H1:62,L1:92,V1:62, }",
        "segment length": "4",
        "psd length": "109.0", # Note that bilby is set-up to round the PSD length to the nearest second
        "ifo list": "['H1', 'L1', 'V1']",
        "segment start": "2",
        "data channels": "{ H1:WeirdChannel,L1:WeirdChannel,V1:OddChannel, }",
        "data frames": "{ 'H1':'NonstandardFrame','L1':'NonstandardFrameL1','V1':'UnusualFrameType', }",
        "window length": "71",
    },
    "rift": {
        "minimum frequency": '{ "H1":62,"L1":92,"V1":62, }',
        "segment length": "4",
        "psd length": "108.6",
        "ifo list": "['H1', 'L1', 'V1']",
        "data channels": '{ "H1":"H1:WeirdChannel","L1":"L1:WeirdChannel","V1":"V1:OddChannel", }',
        "data frames": '{ "H1":"NonstandardFrame","L1":"NonstandardFrameL1","V1":"UnusualFrameType", }',
        "window length": "71",
    },
    "lalinference": {
        "minimum frequency": "{ 'H1': 62, 'L1': 92,  'V1': 62  }",
        "segment length": "4",
        "ifo list": "['H1', 'L1', 'V1']",
        "data channels": "{'H1': 'H1:WeirdChannel', 'L1': 'L1:WeirdChannel', 'V1': 'V1:OddChannel'}",
        "data frames": "{'H1': 'NonstandardFrame', 'L1': 'NonstandardFrameL1', 'V1': 'UnusualFrameType'}",
    }
}


mappings = {
    "bayeswave": {
        "minimum frequency": ["input", "flow"],
        "segment length": ["input", "seglen"],
        "window length": ["input", "window"],
        "psd length": ["input", "psdlength"],
        "ifo list": ["input", "ifo-list"],
        "segment start": ["input", "segment-start"],
        "data channels": ["datafind", "channel-list"],
        "data frames": ["datafind", "frtype-list"],
    },
    "bilby": {
        "minimum frequency": ["test", "minimum-frequency"],
        "segment length": ["test", "duration"],
        "psd length": ["test", "psd-length"],
        "ifo list": ["test", "detectors"],
        "data channels": ["test", "channel-dict"],
    },
    "rift": {
        "data channels": ["datafind", "channel-list"],
        "data frames": ["datafind", "frtype-list"],
        "minimum frequency": ["lalinference", "flow"],
        "segment length": ["engine", "seglen"],
        "ifo list": ["analysis", "ifos"],
        "data channels": ["data", "channels"],
        "data frames": ["datafind", "types"],
    },
    "lalinference": {
        "minimum frequency": ["lalinference", "flow"],
        "segment length": ["engine", "seglen"],
        "ifo list": ["analysis", "ifos"],
        "data channels": ["data", "channels"],
        "data frames": ["datafind", "types"],
    },
}


class TestIniFileHandling(AsimovTestCase):
    """Test that for all pipelines the information in the ini file is
    correctly substituted."""

    def test_detchar_substitution(self):
        event = "Nonstandard fmin"
        
        for pipeline in known_pipelines.keys():
            if pipeline not in exemplar.keys():
                continue
            if pipeline in ["bilby", "gwdata"]: continue
            f = io.StringIO()
            with contextlib.redirect_stdout(f):

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

            f = io.StringIO()
            with contextlib.redirect_stdout(f):
                apply_page(
                    f"{self.cwd}/tests/test_data/{pipeline}_settings_nodeps.yaml",
                    event=event,
                    ledger=self.ledger,
                )

        for production in self.ledger.get_event(event)[0].productions:
            pipeline = production.pipeline.name.lower()
            if pipeline in ["bilby", "gwdata"]: continue
            f = io.StringIO()
            with contextlib.redirect_stdout(f):
                with set_directory(
                    os.path.join(
                        "checkouts", event, config.get("general", "calibration_directory")
                    )
                ):
                    production.make_config(f"{production.name}.ini")
            ini_location = os.path.join(
                config.get("project", "root"),
                "checkouts",
                event,
                config.get("general", "calibration_directory"),
                f"{production.name}.ini",
            )
            self.assertTrue(os.path.exists(ini_location))
            # Read the ini file and convert it to a dictionary for easy access

            import configparser

            pipeline_config = configparser.ConfigParser()
            try:
                pipeline_config.read(ini_location)
            except configparser.MissingSectionHeaderError:
                with open(ini_location, "r") as file_handle:
                    data = file_handle.read()
                with open(ini_location, "w") as file_handle:
                    data = """[test]
""" + data
                    file_handle.write(data)
                pipeline_config.read(ini_location)

            pipeline_config = {
                s: dict(pipeline_config.items(s)) for s in pipeline_config.sections()
            }
            for name, mapping in mappings[pipeline].items():
                with self.subTest(name=name, pipeline=pipeline):
                    self.assertEqual(
                        pipeline_config[mapping[0]][mapping[1]], exemplar[pipeline][name]
                    )
