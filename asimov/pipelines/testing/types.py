"""
A toy analysis type, which shows what a type for a real domain looks like (#238).

``toy-step`` is a generic analysis with a ``round`` and a ``stream``, the way an
iterative fit has components which are fitted in rounds. It is registered only
under ``ASIMOV_TESTING`` and ``ASIMOV_TOY_STRATEGY``, as the toy strategy is, and
is made by that strategy with ``typed: true``.

It uses each hook of :class:`asimov.analysis.SimpleAnalysis` once, and nothing
else: that is the whole of what a type can rely on.
"""
import os

from asimov.analysis import SimpleAnalysis
from asimov.analysis_types import compare


class ToyStep(SimpleAnalysis):
    """
    A step of a toy iterative fit: the analysis of one ``stream`` in one ``round``.

    ``round`` and ``stream`` are in the metadata, which is what is stored; the
    properties are typed views of it.
    """

    #: The terms of the ledger vocabulary which this type brings (see
    #: :mod:`asimov.vocabulary`), so that ``asimov vocabulary check`` knows them.
    vocabulary = {
        "terms": {
            "round": {"type": "integer", "description": "The round of the iterative fit this is a step of."},
            "stream": {"type": "string", "description": "The stream of the fit which this is a step of."},
        }
    }

    @property
    def round(self):
        """The round, as a whole number (None if it is missing or is not one)."""
        value = self.meta.get("round")
        if isinstance(value, bool):
            return None
        try:
            return value if isinstance(value, int) else int(str(value))
        except (TypeError, ValueError):
            return None

    @property
    def stream(self):
        """The stream, as text (None if there is none)."""
        value = self.meta.get("stream")
        return str(value) if value not in (None, "") else None

    def validate(self):
        problems = []
        if self.round is None or self.round < 1:
            problems.append(f"'round' must be a whole number of at least 1, not {self.meta.get('round')!r}")
        if self.stream is None:
            problems.append("'stream' is needed: it says which stream this is a step of")
        return problems

    def match_attribute(self, attribute, match):
        # ``round: "<3"``, ``round: ">=2"``: numbers are compared as numbers
        if attribute == ["round"]:
            return self.round is not None and compare(self.round, match)
        return None

    def rundir_name(self):
        # Rounds in directories of their own: working/<subject>/round-<n>/<name>
        if self.round is None:
            return self.name
        return os.path.join(f"round-{self.round}", self.name)

    def card_details(self):
        return [("Round", self.round), ("Stream", self.stream)]
