"""
Strategies which ship with asimov.

``chain`` is the smallest useful plugin strategy: it expands one blueprint into
a chain of analyses, each of which needs the one before. It is used to test the
strategy machinery without a real workflow, and is a template for plugin
authors: see :class:`asimov.strategies.Strategy`.
"""
from copy import deepcopy
from typing import Any, Dict, List

from asimov.strategies import Strategy, StrategyContext, StrategyError


class ChainStrategy(Strategy):
    """
    Expand a blueprint into ``length`` analyses, each needing the one before.

    .. code-block:: yaml

        kind: analysis
        name: fit
        pipeline: bilby
        strategy:
          type: chain
          length: 3

    makes ``fit-001``, ``fit-002`` (which needs ``fit-001``) and ``fit-003``
    (which needs ``fit-002``). Everything else in the blueprint is copied to
    each of them. The first keeps any ``needs`` of the blueprint.

    Options
    -------
    length : int
        How many analyses. Default 3.
    """

    name = "chain"

    def validate(self, spec: Dict[str, Any]) -> None:
        length = spec.get("length", 3)
        if isinstance(length, bool) or not isinstance(length, int) or length < 1:
            raise StrategyError(f"'length' must be a whole number of at least 1, not {length!r}.")
        unknown = set(spec) - {"type", "length"}
        if unknown:
            raise StrategyError(f"Unknown option(s) for the chain strategy: {', '.join(sorted(unknown))}.")

    def expand(self, blueprint: Dict[str, Any], context: StrategyContext) -> List[Dict[str, Any]]:
        length = blueprint["strategy"].get("length", 3)
        base = deepcopy(blueprint)
        base.pop("strategy")
        documents = []
        for number in range(1, length + 1):
            document = deepcopy(base)
            document["name"] = f"{blueprint['name']}-{number:03d}"
            if number > 1:
                document["needs"] = [documents[-1]["name"]]
            documents.append(document)
        return documents
