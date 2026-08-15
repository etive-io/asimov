"""
Blueprint path constants for tests.

Provides absolute paths to local blueprint files that are v0.7-compatible
(minimum frequency in the 'likelihood' section).  These should be used
instead of the external asimov-data URLs so that unit tests are not
dependent on network access and do not fail due to upstream data lagging
behind code changes.
"""
import os

_BLUEPRINTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_data", "blueprints")

DEFAULTS_PE = os.path.join(_BLUEPRINTS_DIR, "production-pe.yaml")
DEFAULTS_PE_PRIORS = os.path.join(_BLUEPRINTS_DIR, "production-pe-priors.yaml")

EVENTS = {
    "GW150914_095045": os.path.join(_BLUEPRINTS_DIR, "GW150914_095045.yaml"),
    "GW190924_021846": os.path.join(_BLUEPRINTS_DIR, "GW190924_021846.yaml"),
    "GW190929_012149": os.path.join(_BLUEPRINTS_DIR, "GW190929_012149.yaml"),
    "GW191109_010717": os.path.join(_BLUEPRINTS_DIR, "GW191109_010717.yaml"),
}

# GWTC-2.1 event blueprints
GWTC21_EVENTS = {
    "GW150914_095045": os.path.join(_BLUEPRINTS_DIR, "gwtc-2-1", "GW150914_095045.yaml"),
}

PIPELINES = {
    "bilby": os.path.join(_BLUEPRINTS_DIR, "bilby.yaml"),
    "bayeswave": os.path.join(_BLUEPRINTS_DIR, "bayeswave.yaml"),
    "rift": os.path.join(_BLUEPRINTS_DIR, "rift.yaml"),
}
