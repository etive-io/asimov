import logging
import sys
import os

if sys.version_info < (3, 10):
    from importlib_metadata import entry_points
else:
    from importlib.metadata import entry_points

discovered_pipelines = entry_points(group="asimov.pipelines")

logger = logging.getLogger(__name__)


known_pipelines = {
}

# Only register testing pipelines when in testing mode
# This prevents them from appearing as valid options in production
if os.environ.get('ASIMOV_TESTING'):
    from asimov.pipelines.testing import (
        SimpleTestPipeline,
        SubjectTestPipeline,
        ProjectTestPipeline
    )
    known_pipelines["simpletestpipeline"] = SimpleTestPipeline
    known_pipelines["subjecttestpipeline"] = SubjectTestPipeline
    known_pipelines["projecttestpipeline"] = ProjectTestPipeline

for pipeline in discovered_pipelines:
    try:
        known_pipelines[pipeline.name] = pipeline.load()
    except Exception as e:
        import warnings
        warnings.warn(
            f"Failed to load pipeline plugin '{pipeline.name}' ({pipeline.value}): {e}",
            ImportWarning,
            stacklevel=2,
        )
