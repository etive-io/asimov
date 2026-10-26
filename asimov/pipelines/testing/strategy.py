"""
A toy strategy for testing the graph features together (#241).

It is registered only under ``ASIMOV_TESTING`` and ``ASIMOV_TOY_STRATEGY``
(the testing pipelines need only the first), and doubles as an example for authors of strategy plugins.
"""
from typing import Any, Dict, List

from asimov.strategies import Strategy, StrategyContext, StrategyError


class ToyRoundsStrategy(Strategy):
    """
    Expand a blueprint into rounds of steps, one subject per component.

    .. code-block:: yaml

        kind: analysis
        name: toy
        strategy:
          type: toy-rounds
          components: [A, B]
          rounds: 3

    makes the subjects ``component-A``, ``component-B`` and ``shared``; in each
    round ``r`` a ``step-r<r>`` in each component, which needs
    ``shared/combine-r<r-1>``; and a ``combine-r<r>`` in ``shared`` which needs
    every ``step-r<r>``. So there are edges both ways across subjects.

    Options
    -------
    components : list of str
        Default ``[A, B]``.
    rounds : int
        Default 3.
    cycle : bool
        Make ``combine-r1`` need the last step, which is a cycle, to test that
        one is refused. Default false.
    """

    name = "toy-rounds"

    def validate(self, spec: Dict[str, Any]) -> None:
        rounds = spec.get("rounds", 3)
        if isinstance(rounds, bool) or not isinstance(rounds, int) or rounds < 1:
            raise StrategyError(f"'rounds' must be a whole number of at least 1, not {rounds!r}.")
        components = spec.get("components", ["A", "B"])
        if not isinstance(components, list) or not components or len(set(components)) != len(components):
            raise StrategyError("'components' must be a list of different names.")
        unknown = set(spec) - {"type", "components", "rounds", "cycle"}
        if unknown:
            raise StrategyError(f"Unknown option(s) for toy-rounds: {', '.join(sorted(unknown))}.")

    def expand(self, blueprint: Dict[str, Any], context: StrategyContext) -> List[Dict[str, Any]]:
        spec = blueprint["strategy"]
        components = [f"component-{c}" for c in spec.get("components", ["A", "B"])]
        rounds = spec.get("rounds", 3)
        documents = [
            {"kind": "event", "name": subject, "interferometers": ["H1"]}
            for subject in components + ["shared"]
        ]

        def step(subject, r, needs):
            return {
                "kind": "analysis",
                "name": f"step-r{r}",
                "event": subject,
                "pipeline": "simpletestpipeline",
                "status": "ready",
                "needs": needs,
            }

        for r in range(1, rounds + 1):
            before = [f"shared/combine-r{r - 1}"] if r > 1 else []
            for subject in components:
                documents.append(step(subject, r, list(before)))
            combine = step("shared", r, [f"{subject}/step-r{r}" for subject in components])
            combine["name"] = f"combine-r{r}"
            if spec.get("cycle") and r == 1:
                combine["needs"].append(f"{components[0]}/step-r{rounds}")
            documents.append(combine)
        return documents
