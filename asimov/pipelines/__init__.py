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


class PipelineNotInstalled(KeyError):
    """A pipeline which an analysis names is not installed."""

    def __init__(self, name, installed=()):
        self.name = name
        self.installed = list(installed)
        super().__init__(name)

    def __str__(self):
        return (
            f"The pipeline '{self.name}' is not installed. (The plugin which provides it may be "
            f"missing.) The installed pipelines are: {', '.join(self.installed) or 'none'}."
        )


def get_pipeline_class(name):
    """
    The class of the pipeline with this name (which is not case-sensitive).

    Raises
    ------
    PipelineNotInstalled
        (a ``KeyError``) If there is no such pipeline; the message says which are installed.
    """
    try:
        return known_pipelines[str(name).lower()]
    except KeyError:
        raise PipelineNotInstalled(name, sorted(known_pipelines)) from None

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

# The command pipeline is part of asimov. (It is also in the entry points, so it
# is listed with the others; this keeps it available whatever the installed
# metadata says.)
from asimov.pipelines.command import CommandPipeline  # noqa: E402

known_pipelines["command"] = CommandPipeline

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
