import sys

if sys.version_info < (3, 10):
    from importlib_metadata import entry_points
else:
    from importlib.metadata import entry_points

from asimov.pipelines.bayeswave import BayesWave
from asimov.pipelines.bilby import Bilby
from asimov.pipelines.lalinference import LALInference
from asimov.pipelines.rift import Rift

from asimov.pipelines.pesummary import PESummary

discovered_pipelines = entry_points(group="asimov.pipelines")


known_pipelines = {
    "bayeswave": BayesWave,
    "bilby": Bilby,
    "rift": Rift,
    "lalinference": LALInference,
    "pesummary": PESummary,
}


for pipeline in discovered_pipelines:
    known_pipelines[pipeline.name] = pipeline.load()
