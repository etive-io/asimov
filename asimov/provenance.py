"""
Provenance assembly for asimov analyses.

This module builds a `W3C PROV <https://www.w3.org/TR/prov-o/>`_ document
(expressed as JSON-LD) describing how a single analysis was produced: the
configuration and inputs it used, the activity that ran it, the software
agents involved, and the outputs it generated.

Design note
-----------

Everything here is built exclusively from the public, backend-agnostic
interfaces of :class:`asimov.ledger.Ledger` (``get_event``/``get_subject``,
an analysis's ``.meta``/``.to_dict()``) and :class:`asimov.storage.Store`
(``manifest.list_resources``, ``fetch_file``). Nothing here imports
``asimov.database`` or inspects a particular ledger engine's internals, so
this works unchanged against the YAML ledger, the current database ledger
(SQLite/TinyDB/etc.), and any future ``Ledger`` subclass.
"""

import json
import os
import urllib.parse
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Optional

import asimov
from asimov import config
from asimov.storage import Store

PROV_CONTEXT = {
    "prov": "http://www.w3.org/ns/prov#",
    "asimov": "https://etive-io.github.io/asimov/ns#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
}

# Files written by the environment-capture hook (see ``asimov.environment``
# and ``Pipeline._capture_environment``/``_store_environment_files``).
_ENVIRONMENT_METADATA_FILE = "environment.json"
_ENVIRONMENT_ASSET_FILES = {
    "environment.json",
    "environment-pip.txt",
    "environment-conda.txt",
}


class ProvenanceError(LookupError):
    """Raised when the requested subject/analysis can't be found in the ledger."""


def _resolve_analysis(ledger, subject_name: str, analysis_name: str):
    """
    Look up a subject and one of its analyses via the generic ``Ledger`` API.

    Returns
    -------
    (subject, analysis)
    """
    # Ledger backends currently disagree on how a missing subject is
    # signalled (YAMLLedger raises KeyError, DatabaseLedger raises
    # ValueError; neither returns an empty list) - handle all of those
    # uniformly here rather than depending on one particular backend's
    # behaviour.
    try:
        subjects = ledger.get_subject(subject_name)
    except (KeyError, ValueError):
        subjects = []
    if not subjects:
        raise ProvenanceError(f"No subject named {subject_name!r} in this ledger.")
    subject = subjects[0]

    analysis = next(
        (a for a in subject.productions if a.name == analysis_name), None
    )
    if analysis is None:
        raise ProvenanceError(
            f"No analysis named {analysis_name!r} on subject {subject_name!r}."
        )
    return subject, analysis


def _entity_id(kind: str, subject_name: str, analysis_name: str, suffix: str = "") -> str:
    # Names in asimov aren't restricted to URI-safe characters (blueprints
    # can use names with spaces, colons, etc.), so each component is
    # percent-encoded before being joined - this also stops a literal ":"
    # in a name from being mistaken for one of the separators below.
    components = [subject_name, analysis_name]
    if suffix:
        components.append(suffix)
    encoded = ":".join(
        urllib.parse.quote(str(component), safe="") for component in components
    )
    return f"urn:asimov:{kind}:{encoded}"


def _effective_configuration(analysis) -> dict:
    """
    The analysis's full effective configuration.

    Unlike ``Analysis.to_dict()``, this does not strip out values that
    happen to match a project/pipeline default. That diffing exists so the
    ledger doesn't duplicate defaults it already records elsewhere when an
    analysis is saved back into it - a standalone provenance/crate export
    has nowhere else to record those defaults, so it needs the values
    actually used, not just what this analysis explicitly overrode.
    ``analysis.meta`` already has defaults merged in (see
    ``Analysis.__init__``, which merges pipeline and event/subject defaults
    into it), so this builds from that directly rather than going through
    ``to_dict()``.
    """
    effective = deepcopy(analysis.meta)
    for internal_key in ("ledger", "pipelines", "productions"):
        effective.pop(internal_key, None)
    effective["name"] = analysis.name
    effective["event"] = analysis.event.name
    pipeline = analysis.pipeline
    effective["pipeline"] = pipeline if isinstance(pipeline, str) else pipeline.name.lower()
    effective["comment"] = analysis.comment
    effective["status"] = analysis.status
    if analysis.review:
        effective["review"] = analysis.review.to_dicts()
    return effective


def _pipeline_version_from_pip_freeze(pip_freeze: str, pipeline_name: str) -> Optional[str]:
    """Best-effort lookup of a pipeline's own version from a captured ``pip freeze``."""
    needle = pipeline_name.lower()
    for line in pip_freeze.splitlines():
        if "==" not in line:
            continue
        name, _, version = line.partition("==")
        if name.strip().lower() == needle:
            return version.strip()
    return None


def _read_environment(store: Store, subject_name: str, analysis_name: str) -> dict:
    """
    Fetch and parse the environment-capture files for an analysis, if any
    were recorded (see #88). Returns ``{}`` if none are present, or if the
    manifest doesn't know about this subject/analysis at all - both are
    normal for analyses that predate environment capture, or haven't been
    built yet.
    """
    try:
        resources = store.manifest.list_resources(subject_name, analysis_name)
    except (KeyError, FileNotFoundError):
        return {}

    environment: dict[str, Any] = {}

    if _ENVIRONMENT_METADATA_FILE in resources:
        try:
            path = store.fetch_file(subject_name, analysis_name, _ENVIRONMENT_METADATA_FILE)
            with open(path, "r") as metadata_file:
                environment["metadata"] = json.load(metadata_file)
        except (OSError, ValueError):
            pass

    if "environment-pip.txt" in resources:
        try:
            path = store.fetch_file(subject_name, analysis_name, "environment-pip.txt")
            with open(path, "r") as pip_file:
                environment["pip_freeze"] = pip_file.read()
        except OSError:
            pass

    return environment


def build_provenance(
    ledger,
    subject_name: str,
    analysis_name: str,
    *,
    store: Optional[Store] = None,
) -> dict:
    """
    Assemble a PROV-O provenance document (as a JSON-LD-able dict) for one analysis.

    Parameters
    ----------
    ledger : asimov.ledger.Ledger
        Any ledger backend (YAML, database, or otherwise) - only the generic
        ``Ledger`` interface is used.
    subject_name : str
        The name of the event/subject the analysis belongs to.
    analysis_name : str
        The name of the analysis itself.
    store : asimov.storage.Store, optional
        The results store to read output/environment files from. Defaults to
        the project's configured store.

    Returns
    -------
    dict
        A JSON-LD document with ``@context`` and ``@graph`` describing the
        analysis's configuration, inputs, the run itself, the software
        agents involved, and its outputs.

    Notes
    -----
    This intentionally omits any record of *who* applied the blueprint that
    created or changed this analysis's configuration - asimov doesn't track
    that yet (see issue #143). Once it does, that can be added here as an
    additional ``prov:Agent``/``prov:Activity`` pair without needing to
    change the shape of anything already emitted.
    """
    subject, analysis = _resolve_analysis(ledger, subject_name, analysis_name)

    if store is None:
        store = Store(root=config.get("storage", "directory"))

    pipeline_name = getattr(analysis.pipeline, "name", str(analysis.pipeline))
    config_id = _entity_id("config", subject_name, analysis_name)
    activity_id = _entity_id("activity", subject_name, analysis_name)
    asimov_agent_id = "urn:asimov:agent:asimov"
    pipeline_agent_id = (
        f"urn:asimov:agent:pipeline:{urllib.parse.quote(pipeline_name.lower(), safe='')}"
    )

    graph: list[dict] = []

    config_entity = {
        "@id": config_id,
        "@type": "prov:Entity",
        "asimov:kind": "configuration",
        "asimov:value": json.loads(json.dumps(_effective_configuration(analysis), default=str)),
    }
    graph.append(config_entity)

    used_ids = [config_id]

    environment = _read_environment(store, subject_name, analysis_name)
    environment_id = None
    pipeline_version = None
    if environment:
        environment_id = _entity_id("environment", subject_name, analysis_name)
        env_metadata = environment.get("metadata", {})
        graph.append(
            {
                "@id": environment_id,
                "@type": "prov:Entity",
                "asimov:kind": "software-environment",
                "asimov:capturedAt": env_metadata.get("timestamp"),
                "asimov:pythonVersion": env_metadata.get("python_version"),
                "asimov:environmentType": env_metadata.get("environment_type"),
            }
        )
        used_ids.append(environment_id)
        if "pip_freeze" in environment:
            pipeline_version = _pipeline_version_from_pip_freeze(
                environment["pip_freeze"], pipeline_name
            )

    # Dependencies are other *activities* (upstream analyses), not entities,
    # so they belong on `prov:wasInformedBy` (activity-to-activity) rather
    # than `prov:used` (whose range is `prov:Entity`) - see `used_ids` below.
    dependency_activity_ids = [
        _entity_id("activity", subject_name, dependency_name)
        for dependency_name in (getattr(analysis, "resolved_dependencies", None) or [])
    ]

    output_entities = []
    try:
        resources = store.manifest.list_resources(subject_name, analysis_name)
    except (KeyError, FileNotFoundError):
        resources = {}
    for filename, resource in resources.items():
        if filename in _ENVIRONMENT_ASSET_FILES:
            continue
        output_id = _entity_id("output", subject_name, analysis_name, suffix=resource["uuid"])
        output_entities.append(
            {
                "@id": output_id,
                "@type": "prov:Entity",
                "asimov:kind": "output-file",
                "asimov:filename": filename,
                "asimov:hash": resource["hash"],
                "asimov:hashAlgorithm": "md5",
                "asimov:uuid": resource["uuid"],
                "prov:wasGeneratedBy": {"@id": activity_id},
            }
        )
    graph.extend(output_entities)

    activity = {
        "@id": activity_id,
        "@type": "prov:Activity",
        "asimov:status": getattr(analysis, "status", None),
        "asimov:pipeline": pipeline_name,
        "prov:used": [{"@id": entity_id} for entity_id in used_ids],
        "prov:wasAssociatedWith": [{"@id": asimov_agent_id}, {"@id": pipeline_agent_id}],
    }
    if dependency_activity_ids:
        activity["prov:wasInformedBy"] = [
            {"@id": dependency_id} for dependency_id in dependency_activity_ids
        ]
    graph.append(activity)

    graph.append(
        {
            "@id": asimov_agent_id,
            "@type": "prov:SoftwareAgent",
            "asimov:name": "asimov",
            "asimov:version": asimov.__version__,
        }
    )
    graph.append(
        {
            "@id": pipeline_agent_id,
            "@type": "prov:SoftwareAgent",
            "asimov:name": pipeline_name,
            "asimov:version": pipeline_version,
        }
    )

    return {
        "@context": PROV_CONTEXT,
        "@graph": graph,
        "asimov:subject": subject_name,
        "asimov:analysis": analysis_name,
        "asimov:generatedAt": datetime.now(timezone.utc).isoformat(),
    }


def write_provenance(document: dict, destination: str) -> str:
    """Write a provenance document to ``destination`` as pretty-printed JSON."""
    os.makedirs(os.path.dirname(os.path.abspath(destination)) or ".", exist_ok=True)
    with open(destination, "w") as provenance_file:
        json.dump(document, provenance_file, indent=2, default=str)
    return destination
