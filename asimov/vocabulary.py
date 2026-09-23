"""
The asimov ledger vocabulary.

This module provides a machine-readable description of the keys which may
appear in an asimov ledger or blueprint, so that asimov, its plugins, and
tools which review them can agree on a single name (and a single meaning)
for each quantity.

The core vocabulary is stored in ``vocabulary.yaml`` alongside this module.
Pipeline plugins can extend it with terms that only make sense to their
pipeline by registering an entry point in the ``asimov.vocabulary`` group,
whose name is the pipeline name and whose value resolves to one of

* a dictionary with a ``terms`` key (and optionally ``assets``), in the same
  format as ``vocabulary.yaml``;
* a path (``str``, ``os.PathLike`` or ``importlib.resources`` traversable)
  to a YAML file in that format;
* a callable returning either of the above.

For example, in a plugin's ``pyproject.toml``::

    [project.entry-points."asimov.vocabulary"]
    mypipeline = "asimov_mypipeline:vocabulary"

Examples
--------
>>> from asimov.vocabulary import get_vocabulary
>>> vocabulary = get_vocabulary()
>>> vocabulary.lookup("likelihood.minimum frequency").units
'Hz'
>>> blueprint = {"pipeline": "jim", "jim": {"data": {"psd_files": {}}}}
>>> [finding.suggestion for finding in vocabulary.check(blueprint)]
['psds']
"""

import difflib
import importlib.resources
import logging
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

import yaml

if sys.version_info < (3, 10):
    from importlib_metadata import entry_points
else:
    from importlib.metadata import entry_points

logger = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "asimov.vocabulary"

TERM_TYPES = {
    "section",
    "string",
    "float",
    "integer",
    "boolean",
    "list",
    "mapping",
    "any",
}

Path = Tuple[str, ...]

#: Synonyms too generic to identify a term outside of its own section.
GENERIC_SYNONYMS = {
    "type", "name", "method", "algorithm", "model", "kwargs", "settings",
    "group", "account", "image", "env", "threads", "result", "results",
    "configuration", "cache", "gpu", "disk", "memory", "mem", "frames",
    "duration", "partition", "gps", "psd", "channel", "seed",
}


def _normalise(name: str) -> str:
    """Normalise a key for fuzzy comparison (case, underscores, hyphens)."""
    return " ".join(str(name).lower().replace("_", " ").replace("-", " ").split())


def split_path(path: Union[str, Iterable[str]]) -> Path:
    """
    Convert a dotted path (``"likelihood.minimum frequency"``) into a tuple.

    Tuples and lists are returned unchanged (as a tuple), which allows keys
    that themselves contain a ``.`` to be looked up.
    """
    if isinstance(path, str):
        return tuple(part for part in path.split(".") if part)
    return tuple(path)


def join_path(path: Iterable[str]) -> str:
    """Convert a tuple path into its dotted form."""
    return ".".join(path)


@dataclass
class Term:
    """
    A single term in the ledger vocabulary.

    Attributes
    ----------
    name : str
        The canonical key.
    path : tuple of str
        The full path of the term from the root of the ledger.
    description : str
        What the value means.
    type : str
        The type of the value (see ``TERM_TYPES``).
    per_ifo : bool
        Whether the value is a mapping from detector to ``type``.
    units : str, optional
        Physical units of the value.
    open : bool
        Whether the section accepts arbitrary children.
    overlay : bool
        Whether the children of this section are keyed by pipeline name
        and may each contain any term from the vocabulary.
    aliases : list of str
        Accepted alternative spellings.
    synonyms : list of str
        Names commonly used to mean this term, used for suggestions only.
    deprecated : dict, optional
        ``{"replaced by": path, "since": version}``.
    owner : str, optional
        The pipeline which owns the term, if it is not generic.
    used_by : list of str
        The functions or pipelines which read the term.
    children : dict
        Child terms, keyed by canonical name.
    """

    name: str
    path: Path
    description: str
    type: str = "any"
    per_ifo: bool = False
    units: Optional[str] = None
    open: bool = False
    overlay: bool = False
    aliases: List[str] = field(default_factory=list)
    synonyms: List[str] = field(default_factory=list)
    deprecated: Optional[Dict[str, str]] = None
    owner: Optional[str] = None
    used_by: List[str] = field(default_factory=list)
    children: Dict[str, "Term"] = field(default_factory=dict)

    @property
    def dotted(self) -> str:
        """The dotted path of the term."""
        return join_path(self.path)

    @property
    def is_section(self) -> bool:
        return self.type == "section"

    @property
    def replaced_by(self) -> Optional[str]:
        if self.deprecated:
            return self.deprecated.get("replaced by")
        return None

    def child(self, key: str) -> Optional["Term"]:
        """Return the child term with the given key or alias."""
        if key in self.children:
            return self.children[key]
        for term in self.children.values():
            if key in term.aliases:
                return term
        return None

    def walk(self):
        """Iterate over this term and all of its descendants."""
        yield self
        for term in self.children.values():
            yield from term.walk()

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain dictionary representation of the term."""
        data = {
            "path": self.dotted,
            "description": self.description,
            "type": self.type,
        }
        for attribute, key in (
            ("per_ifo", "per ifo"),
            ("units", "units"),
            ("open", "open"),
            ("overlay", "overlay"),
            ("aliases", "aliases"),
            ("synonyms", "synonyms"),
            ("deprecated", "deprecated"),
            ("owner", "owner"),
            ("used_by", "used by"),
        ):
            value = getattr(self, attribute)
            if value:
                data[key] = value
        if self.children:
            data["children"] = {
                name: term.to_dict() for name, term in self.children.items()
            }
        return data

    @classmethod
    def from_dict(
        cls, name: str, data: Dict[str, Any], parent: Path = (), owner=None
    ) -> "Term":
        """Build a term (and its children) from a vocabulary file entry."""
        if not isinstance(data, dict):
            raise ValueError(f"Vocabulary entry '{name}' must be a mapping.")
        if "description" not in data:
            raise ValueError(f"Vocabulary entry '{name}' has no description.")
        path = parent + (name,)
        owner = data.get("owner", owner)
        children = data.get("children") or {}
        term_type = data.get("type", "section" if children else "any")
        if term_type not in TERM_TYPES:
            raise ValueError(
                f"Vocabulary entry '{name}' has unknown type '{term_type}'."
            )
        term = cls(
            name=name,
            path=path,
            description=" ".join(str(data["description"]).split()),
            type=term_type,
            per_ifo=bool(data.get("per ifo", False)),
            units=data.get("units"),
            open=bool(data.get("open", False)),
            overlay=bool(data.get("overlay", False)),
            aliases=list(data.get("aliases") or []),
            synonyms=list(data.get("synonyms") or []),
            deprecated=data.get("deprecated"),
            owner=owner,
            used_by=list(data.get("used by") or []),
        )
        for child_name, child_data in children.items():
            term.children[child_name] = cls.from_dict(
                child_name, child_data, path, owner=owner
            )
        return term


@dataclass
class Asset:
    """A standard name for an entry in ``Pipeline.collect_assets()``."""

    name: str
    description: str
    synonyms: List[str] = field(default_factory=list)
    owner: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data = {"description": self.description}
        if self.synonyms:
            data["synonyms"] = self.synonyms
        if self.owner:
            data["owner"] = self.owner
        return data


@dataclass
class Finding:
    """
    The result of checking one key against the vocabulary.

    Attributes
    ----------
    path : tuple of str
        The path of the key in the checked document.
    kind : str
        One of ``unknown`` (not in the vocabulary), ``alias`` (a
        non-canonical spelling), ``deprecated``, ``foreign`` (owned by a
        different pipeline), ``duplicate`` (a key in a pipeline's own
        namespace which means the same as a standard term), or ``type``
        (a section given a scalar).
    message : str
        A human-readable explanation.
    suggestion : str, optional
        The dotted path of the term which should probably be used instead.
    """

    path: Path
    kind: str
    message: str
    suggestion: Optional[str] = None

    @property
    def dotted(self) -> str:
        return join_path(self.path)

    def to_dict(self) -> Dict[str, Any]:
        data = {"path": self.dotted, "kind": self.kind, "message": self.message}
        if self.suggestion:
            data["suggestion"] = self.suggestion
        return data

    def __str__(self):
        return f"{self.dotted}: [{self.kind}] {self.message}"


class Vocabulary:
    """
    The ledger vocabulary: a tree of :class:`Term` objects and a set of
    standard :class:`Asset` names.

    Parameters
    ----------
    data : dict
        The parsed contents of a vocabulary file.
    """

    def __init__(self, data: Dict[str, Any], owner: Optional[str] = None):
        self.version = data.get("version", 1)
        self.root = Term(
            name="",
            path=(),
            description="The root of the ledger.",
            type="section",
        )
        self.assets: Dict[str, Asset] = {}
        #: Terms from plugins which clashed with an existing term.
        self.conflicts: List[Tuple[str, str]] = []
        self.plugins: List[str] = []
        self.merge(data, owner=owner)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def from_file(cls, path) -> "Vocabulary":
        with open(path, "r") as handle:
            return cls(yaml.safe_load(handle))

    @classmethod
    def core(cls) -> "Vocabulary":
        """Load the core vocabulary shipped with asimov."""
        resource = importlib.resources.files("asimov").joinpath("vocabulary.yaml")
        return cls(yaml.safe_load(resource.read_text()))

    def merge(self, data: Dict[str, Any], owner: Optional[str] = None):
        """
        Merge additional terms (for example from a plugin) into the vocabulary.

        Terms which already exist are not replaced: they are recorded in
        :attr:`conflicts` so that the clash can be reported.  New children
        can be added beneath existing sections.
        """
        for name, entry in (data.get("terms") or {}).items():
            self._merge_term(self.root, name, entry, owner)
        for name, entry in (data.get("assets") or {}).items():
            if name in self.assets:
                if owner is not None:
                    self.conflicts.append((f"assets.{name}", owner))
                continue
            self.assets[name] = Asset(
                name=name,
                description=" ".join(str(entry.get("description", "")).split()),
                synonyms=list(entry.get("synonyms") or []),
                owner=entry.get("owner", owner),
            )

    def _merge_term(self, parent: Term, name: str, entry: Dict[str, Any], owner):
        existing = parent.child(name)
        if existing is None:
            parent.children[name] = Term.from_dict(name, entry, parent.path, owner)
            return
        # Allow a plugin to add children beneath an existing section
        # without redefining the section itself.
        new_children = entry.get("children") or {}
        redefined = set(entry) - {"children"}
        if redefined and owner is not None:
            self.conflicts.append((join_path(existing.path), owner))
        for child_name, child_entry in new_children.items():
            self._merge_term(existing, child_name, child_entry, owner)

    def load_plugins(self):
        """Merge the vocabularies registered by installed plugins."""
        for entry_point in entry_points(group=ENTRY_POINT_GROUP):
            try:
                data = _resolve_plugin_vocabulary(entry_point.load())
                self.merge(data, owner=entry_point.name)
                self.plugins.append(entry_point.name)
            except Exception as error:  # pragma: no cover - defensive
                logger.warning(
                    "Failed to load vocabulary from plugin '%s' (%s): %s",
                    entry_point.name,
                    entry_point.value,
                    error,
                )
        return self

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def terms(self) -> Iterable[Term]:
        """Iterate over every term in the vocabulary."""
        for term in self.root.children.values():
            yield from term.walk()

    def lookup(self, path: Union[str, Iterable[str]]) -> Optional[Term]:
        """
        Find the term at a path, following aliases and ``pipelines`` overlays.

        Returns ``None`` if the path is not in the vocabulary (including
        paths beneath an ``open`` section, which are allowed but undefined).
        """
        term = self.root
        parts = list(split_path(path))
        while parts:
            key = parts.pop(0)
            if term.overlay:
                # Skip the pipeline-name level of an overlay section.
                if not parts:
                    return None
                term = self.root
                key = parts.pop(0)
            child = term.child(key)
            if child is None:
                return None
            term = child
        return None if term is self.root else term

    def suggest(
        self, key: str, parent: Union[str, Iterable[str]] = ()
    ) -> Optional[Term]:
        """
        Suggest the term somebody probably meant when they used ``key``.

        Synonyms and normalised spellings within the same section are
        preferred, then synonyms anywhere in the vocabulary, then close
        spellings within the same section.
        """
        normalised = _normalise(key)
        parent_term = self.lookup(parent) if split_path(parent) else self.root
        siblings = list(parent_term.children.values()) if parent_term else []

        def names(term):
            return [term.name] + term.aliases + term.synonyms

        if parent_term is not None:
            match = self.suggest_in(key, parent_term)
            if match is not None:
                return match
        match = self.match(key)
        if match is not None:
            return match
        candidates = {}
        for term in siblings:
            for name in names(term):
                candidates.setdefault(_normalise(name), term)
        match = difflib.get_close_matches(normalised, candidates, n=1, cutoff=0.75)
        if match:
            return candidates[match[0]]
        return None

    def suggest_in(self, key: str, section: Term) -> Optional[Term]:
        """Find a child of ``section`` whose name, alias or synonym is ``key``."""
        normalised = _normalise(key)
        for term in section.children.values():
            if normalised in {
                _normalise(name) for name in [term.name] + term.aliases + term.synonyms
            }:
                return term
        return None

    def match(self, key: str) -> Optional[Term]:
        """
        Find a term anywhere in the vocabulary whose name, alias or synonym
        is (after normalising case, underscores and hyphens) ``key``.

        Synonyms in :data:`GENERIC_SYNONYMS` are ignored, since they only
        identify a term within its own section.  Terms owned by plugins are
        not matched, so that a plugin's own vocabulary cannot shadow core.
        Non-deprecated terms are preferred over deprecated ones.
        """
        normalised = _normalise(key)
        if normalised in GENERIC_SYNONYMS:
            return None
        matches = [
            term
            for term in self.terms()
            if term.owner not in self.plugins
            and normalised
            in {_normalise(name) for name in [term.name] + term.aliases + term.synonyms}
        ]
        # Prefer a current term over a deprecated location for the same thing.
        matches.sort(key=lambda term: term.deprecated is not None)
        return matches[0] if matches else None

    def suggest_asset(self, name: str) -> Optional[Asset]:
        """Suggest the standard asset name for a non-standard one."""
        normalised = _normalise(name)
        for asset in self.assets.values():
            if normalised in {_normalise(n) for n in [asset.name] + asset.synonyms}:
                return asset
        return None

    def check(
        self,
        document: Dict[str, Any],
        pipeline: Optional[str] = None,
        parent: Path = (),
    ) -> List[Finding]:
        """
        Check a ledger or blueprint document against the vocabulary.

        Parameters
        ----------
        document : dict
            The (parsed) document to check.
        pipeline : str, optional
            The pipeline the document is for.  If given, terms owned by a
            different pipeline are reported as ``foreign``.  The document's
            own ``pipeline`` key is used if this is not given.
        parent : tuple of str, optional
            The path of ``document`` within the ledger, if it is a fragment.

        Returns
        -------
        list of :class:`Finding`
        """
        if pipeline is None and isinstance(document, dict):
            pipeline = document.get("pipeline")
        parent_term = self.lookup(parent) if parent else self.root
        findings: List[Finding] = []
        if parent_term is None:
            return findings
        self._check_section(document, parent_term, tuple(parent), pipeline, findings)
        return findings

    def _check_section(self, data, term: Term, path: Path, pipeline, findings):
        if not isinstance(data, dict):
            return
        if term.overlay:
            for pipeline_name, block in data.items():
                if isinstance(block, dict) and not term.open:
                    self._check_section(
                        block,
                        self.root,
                        path + (pipeline_name,),
                        pipeline_name,
                        findings,
                    )
            return
        if term.open and not term.children:
            return
        for key, value in data.items():
            key = str(key)
            key_path = path + (key,)
            child = term.child(key)
            if child is None:
                if term.open:
                    continue
                if pipeline and term is self.root and key.lower() == pipeline.lower():
                    # A pipeline's own namespace which the plugin has not
                    # registered: its contents are the plugin's business,
                    # except where they duplicate a standard term.
                    self._check_namespace(value, key_path, findings)
                    continue
                suggestion = self.suggest(key, term.path)
                message = f"'{key}' is not in the asimov ledger vocabulary."
                if suggestion is not None:
                    message += f" Did you mean '{suggestion.dotted}'?"
                findings.append(
                    Finding(
                        key_path,
                        "unknown",
                        message,
                        suggestion.dotted if suggestion else None,
                    )
                )
                continue
            if key != child.name:
                findings.append(
                    Finding(
                        key_path,
                        "alias",
                        f"'{key}' is an alias; use '{child.name}' instead.",
                        child.dotted,
                    )
                )
            if child.deprecated:
                since = child.deprecated.get("since")
                findings.append(
                    Finding(
                        key_path,
                        "deprecated",
                        f"'{child.dotted}' is deprecated"
                        + (f" since v{since}" if since else "")
                        + (
                            f"; use '{child.replaced_by}' instead."
                            if child.replaced_by
                            else "."
                        ),
                        child.replaced_by,
                    )
                )
            if pipeline and child.owner and child.owner.lower() != pipeline.lower():
                findings.append(
                    Finding(
                        key_path,
                        "foreign",
                        f"'{child.dotted}' belongs to the '{child.owner}' "
                        f"pipeline, not '{pipeline}'.",
                    )
                )
            if child.is_section and value is not None and not isinstance(value, dict):
                findings.append(
                    Finding(
                        key_path,
                        "type",
                        f"'{child.dotted}' is a section, but was given "
                        f"a {type(value).__name__}.",
                    )
                )
                continue
            if child.children or child.overlay:
                self._check_section(value, child, key_path, pipeline, findings)

    def _check_namespace(self, data, path: Path, findings, section=None):
        """
        Report keys in a pipeline namespace which duplicate standard terms.

        Sections in the namespace which mirror a standard section (for
        example ``mypipeline: data:``) are descended into rather than being
        reported themselves, so that the duplicated quantity is named.
        """
        if not isinstance(data, dict):
            return
        section = section or self.root
        for key, value in data.items():
            key_path = path + (str(key),)
            match = section.child(str(key)) or self.suggest_in(str(key), section)
            if match is None:
                match = self.match(str(key))
            if match is not None and match.children and isinstance(value, dict):
                self._check_namespace(value, key_path, findings, match)
                continue
            if match is not None:
                findings.append(
                    Finding(
                        key_path,
                        "duplicate",
                        f"'{join_path(key_path)}' duplicates the standard term "
                        f"'{match.dotted}' ({match.description})",
                        match.dotted,
                    )
                )
                continue
            self._check_namespace(value, key_path, findings, self.root)

    def duplicates(self) -> List[Finding]:
        """
        Report plugin-registered terms which duplicate a core term.

        A plugin should only register quantities that have no meaning to
        other pipelines; anything else belongs in the core vocabulary.
        """
        findings = []
        for term in self.terms():
            if term.owner not in self.plugins:
                continue
            for name in [term.name] + term.synonyms:
                match = self.match(name)
                if match is not None and match is not term:
                    findings.append(
                        Finding(
                            term.path,
                            "duplicate",
                            f"'{term.dotted}' (registered by '{term.owner}') "
                            f"duplicates the standard term '{match.dotted}'.",
                            match.dotted,
                        )
                    )
                    break
        return findings

    def check_file(self, path, pipeline: Optional[str] = None) -> List[Finding]:
        """Check every document in a (possibly multi-document) YAML file."""
        findings = []
        with open(path, "r") as handle:
            for document in yaml.safe_load_all(handle):
                if isinstance(document, dict):
                    findings += self.check(document, pipeline=pipeline)
        return findings

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Return the whole vocabulary as a plain dictionary."""
        return {
            "version": self.version,
            "plugins": list(self.plugins),
            "terms": {
                name: term.to_dict() for name, term in self.root.children.items()
            },
            "assets": {name: asset.to_dict() for name, asset in self.assets.items()},
            "conflicts": [
                {"path": path, "plugin": plugin} for path, plugin in self.conflicts
            ],
        }


def _resolve_plugin_vocabulary(obj) -> Dict[str, Any]:
    """Turn whatever a plugin's entry point resolves to into a dictionary."""
    if callable(obj):
        obj = obj()
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "read_text"):
        return yaml.safe_load(obj.read_text())
    if isinstance(obj, (str, os.PathLike)):
        with open(obj, "r") as handle:
            return yaml.safe_load(handle)
    raise TypeError(
        f"A vocabulary entry point must resolve to a dict or a YAML path, "
        f"not {type(obj).__name__}."
    )


_VOCABULARY = None


def get_vocabulary(plugins: bool = True, refresh: bool = False) -> Vocabulary:
    """
    Return the ledger vocabulary.

    Parameters
    ----------
    plugins : bool, optional
        Include terms registered by installed plugins. Defaults to True.
    refresh : bool, optional
        Rebuild the vocabulary rather than returning the cached copy.
    """
    global _VOCABULARY
    if not plugins:
        return Vocabulary.core()
    if _VOCABULARY is None or refresh:
        _VOCABULARY = Vocabulary.core().load_plugins()
    return _VOCABULARY
