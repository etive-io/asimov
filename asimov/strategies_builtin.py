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

    The names can be chosen with a template:

    .. code-block:: yaml

        strategy:
          type: chain
          length: 3
          names: "{name}-r{n:02d}"

    makes ``fit-r01``, ``fit-r02`` and ``fit-r03``.

    Options
    -------
    length : int
        How many analyses. Default 3.
    names : str
        A template for the names. ``{name}`` is the name of the blueprint and
        ``{n}`` the number of the analysis, from 1; a format can follow the
        name of the field (``{n:03d}``), as in Python. Default
        ``"{name}-{n:03d}"``. The names must differ from one another, so the
        template must use ``{n}``.
    """

    name = "chain"

    #: The template for the names of the analyses, when there isn't one.
    DEFAULT_NAMES = "{name}-{n:03d}"

    def validate(self, spec: Dict[str, Any]) -> None:
        length = spec.get("length", 3)
        if isinstance(length, bool) or not isinstance(length, int) or length < 1:
            raise StrategyError(f"'length' must be a whole number of at least 1, not {length!r}.")
        unknown = set(spec) - {"type", "length", "names"}
        if unknown:
            raise StrategyError(f"Unknown option(s) for the chain strategy: {', '.join(sorted(unknown))}.")
        template = spec.get("names", self.DEFAULT_NAMES)
        if not isinstance(template, str):
            raise StrategyError(f"'names' must be a template such as '{{name}}-{{n:03d}}', not {template!r}.")
        try:
            first, second = (template.format(name="name", n=n) for n in (1, 2))
        except (KeyError, IndexError, ValueError, AttributeError) as error:
            raise StrategyError(
                f"'names' is not a usable template ({error!r}). "
                "It can use {name} and {n}, for example '{name}-{n:03d}'."
            ) from error
        if first == second:
            raise StrategyError(
                f"'names' ({template!r}) gives the same name to every analysis; it must use {{n}}."
            )

    def expand(self, blueprint: Dict[str, Any], context: StrategyContext) -> List[Dict[str, Any]]:
        spec = blueprint["strategy"]
        length = spec.get("length", 3)
        template = spec.get("names", self.DEFAULT_NAMES)
        base = deepcopy(blueprint)
        base.pop("strategy")
        documents = []
        for number in range(1, length + 1):
            document = deepcopy(base)
            document["name"] = template.format(name=blueprint["name"], n=number)
            if number > 1:
                document["needs"] = [documents[-1]["name"]]
            documents.append(document)
        return documents
