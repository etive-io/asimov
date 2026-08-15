import logging
import sys

if sys.version_info < (3, 10):
    from importlib_metadata import entry_points
else:
    from importlib.metadata import entry_points

from asimov.pipelines.bilby import Bilby
from asimov.pipelines.rift import Rift

discovered_pipelines = entry_points(group="asimov.pipelines")

logger = logging.getLogger(__name__)


known_pipelines = {
    "bilby": Bilby,
    "rift": Rift,
}


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
