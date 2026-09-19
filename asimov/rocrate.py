"""
RO-Crate packaging for asimov analyses.

Builds an `RO-Crate <https://www.researchobject.org/ro-crate/>`_ - a
directory of a metadata file plus a handful of small files - that captures
everything needed to understand exactly how an analysis was configured and
run: its configuration, its software environment, and its provenance graph
(see :mod:`asimov.provenance`).

This is deliberately **export-only** for now (see issue #154): it packages
an existing analysis for archival, sharing, or citation. Importing a crate
back into a project to recreate the analysis is tracked separately, since
that touches the blueprint/apply path more invasively than a read-only
export does.

Large result files (posterior samples, etc.) are not copied into the crate.
They're referenced by the hash/UUID already recorded in the analysis's
:class:`asimov.storage.Store` manifest, so the crate stays small regardless
of how big the underlying analysis outputs are; a consumer with access to
the same results store can resolve them from those references.

Like :mod:`asimov.provenance`, everything here goes through the generic
``Ledger``/``Store`` interfaces only, so it works with any ledger backend.
"""

import json
import os
import shutil
from datetime import datetime, timezone
from typing import Optional

from asimov import config
from asimov.provenance import _ENVIRONMENT_ASSET_FILES, _resolve_analysis, build_provenance
from asimov.storage import Store

RO_CRATE_CONTEXT = "https://w3id.org/ro/crate/1.1/context"


def package_analysis(
    ledger,
    subject_name: str,
    analysis_name: str,
    destination: str,
    *,
    store: Optional[Store] = None,
) -> str:
    """
    Export an RO-Crate for one analysis.

    Parameters
    ----------
    ledger : asimov.ledger.Ledger
        Any ledger backend.
    subject_name : str
        The name of the event/subject the analysis belongs to.
    analysis_name : str
        The name of the analysis itself.
    destination : str
        Path to the (not-yet-existing) directory the crate should be
        written to.
    store : asimov.storage.Store, optional
        The results store to read output/environment files from. Defaults
        to the project's configured store.

    Returns
    -------
    str
        The path to the crate directory (same as ``destination``).
    """
    subject, analysis = _resolve_analysis(ledger, subject_name, analysis_name)

    if store is None:
        store = Store(root=config.get("storage", "directory"))

    provenance_document = build_provenance(
        ledger, subject_name, analysis_name, store=store
    )

    os.makedirs(destination, exist_ok=False)

    provenance_path = os.path.join(destination, "provenance.json")
    with open(provenance_path, "w") as provenance_file:
        json.dump(provenance_document, provenance_file, indent=2, default=str)

    config_path = os.path.join(destination, "config.json")
    with open(config_path, "w") as config_file:
        json.dump(analysis.to_dict(event=False), config_file, indent=2, default=str)

    has_part = [{"@id": "provenance.json"}, {"@id": "config.json"}]
    file_entities = [
        {
            "@id": "provenance.json",
            "@type": "File",
            "name": "W3C PROV-O provenance graph for this analysis",
            "encodingFormat": "application/ld+json",
        },
        {
            "@id": "config.json",
            "@type": "File",
            "name": "Analysis configuration",
            "encodingFormat": "application/json",
        },
    ]

    environment_dir = os.path.join(destination, "environment")
    try:
        resources = store.manifest.list_resources(subject_name, analysis_name)
    except (KeyError, FileNotFoundError):
        resources = {}

    for filename in sorted(_ENVIRONMENT_ASSET_FILES & resources.keys()):
        os.makedirs(environment_dir, exist_ok=True)
        source_path = store.fetch_file(subject_name, analysis_name, filename)
        crate_relative_path = f"environment/{filename}"
        shutil.copyfile(source_path, os.path.join(destination, crate_relative_path))
        has_part.append({"@id": crate_relative_path})
        file_entities.append(
            {
                "@id": crate_relative_path,
                "@type": "File",
                "name": f"Captured software environment: {filename}",
            }
        )

    # Output files stay in the results store rather than being copied into
    # the crate; they're referenced here by the hash/UUID already recorded
    # in the store's manifest.
    output_entities = []
    for filename, resource in resources.items():
        if filename in _ENVIRONMENT_ASSET_FILES:
            continue
        entity_id = f"asimov:store-file:{resource['uuid']}"
        output_entities.append(
            {
                "@id": entity_id,
                "@type": "File",
                "name": filename,
                "identifier": resource["uuid"],
                "md5": resource["hash"],
                "asimov:externallyStored": True,
                "description": (
                    "Not bundled in this crate; resolvable from the asimov "
                    "results store by its UUID/hash."
                ),
            }
        )
        has_part.append({"@id": entity_id})

    root_dataset = {
        "@id": "./",
        "@type": "Dataset",
        "name": f"asimov analysis: {subject_name}/{analysis_name}",
        "description": (
            f"An asimov RO-Crate export of the analysis {analysis_name!r} "
            f"on subject {subject_name!r}, packaged for reproducibility."
        ),
        "datePublished": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "hasPart": has_part,
    }

    metadata_descriptor = {
        "@id": "ro-crate-metadata.json",
        "@type": "CreativeWork",
        "conformsTo": {"@id": "https://w3id.org/ro/crate/1.1"},
        "about": {"@id": "./"},
    }

    ro_crate_metadata = {
        "@context": RO_CRATE_CONTEXT,
        "@graph": (
            [metadata_descriptor, root_dataset]
            + file_entities
            + output_entities
            + provenance_document["@graph"]
        ),
    }

    metadata_path = os.path.join(destination, "ro-crate-metadata.json")
    with open(metadata_path, "w") as metadata_file:
        json.dump(ro_crate_metadata, metadata_file, indent=2, default=str)

    return destination
