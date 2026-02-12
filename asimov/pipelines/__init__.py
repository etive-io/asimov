import sys

if sys.version_info < (3, 10):
    from importlib_metadata import entry_points
else:
    from importlib.metadata import entry_points

from asimov.pipelines.rift import Rift

discovered_pipelines = entry_points(group="asimov.pipelines")


known_pipelines = {
    "rift": Rift,
}


for pipeline in discovered_pipelines:
    known_pipelines[pipeline.name] = pipeline.load()
