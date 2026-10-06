"""
Analyses API blueprint.

Provides CRUD operations for event analyses.
"""

import json
import logging
import os
from flask import Blueprint, request, jsonify
from pydantic import ValidationError
from asimov.api.utils import get_ledger
from asimov.api.auth import require_auth
from asimov.api.models import AnalysisCreate, AnalysisUpdate
from asimov.event import Production

bp = Blueprint('analyses', __name__)
logger = logging.getLogger(__name__)


@bp.route('/<event_name>/<analysis_name>', methods=['GET'])
def get_analysis(event_name, analysis_name):
    """
    Get specific analysis from an event.

    Parameters
    ----------
    event_name : str
        The event name.
    analysis_name : str
        The analysis name.

    Returns
    -------
    json
        Analysis data if found, error message otherwise.
    """
    ledger = get_ledger()
    try:
        events = ledger.get_event(event_name)
    except (KeyError, ValueError):
        return jsonify({'error': 'Event not found'}), 404

    event = events[0]
    analysis = next((p for p in event.productions if p.name == analysis_name), None)

    if not analysis:
        return jsonify({'error': 'Analysis not found'}), 404

    return jsonify({'analysis': analysis.to_dict(event=False)})


@bp.route('/<event_name>/<analysis_name>/telemetry', methods=['GET'])
def get_analysis_telemetry(event_name, analysis_name):
    """
    Get telemetry events recorded for an analysis.

    Reads events live from the analysis's local ``telemetry.jsonl`` file -
    the same run-directory-based storage the built-in local telemetry sink
    writes to. Not cached, not stored in the ledger.

    Parameters
    ----------
    event_name : str
        The event name.
    analysis_name : str
        The analysis name.

    Query parameters
    -----------------
    event_type : str, optional
        Only return events with this ``event_type``.
    since : str, optional
        Only return events with a timestamp >= this ISO 8601 string
        (compared as strings, which works for ISO 8601 timestamps).

    Returns
    -------
    json
        A list of telemetry events, or an error message.
    """
    ledger = get_ledger()
    try:
        events = ledger.get_event(event_name)
    except (KeyError, ValueError):
        return jsonify({'error': 'Event not found'}), 404

    event = events[0]
    analysis = next((p for p in event.productions if p.name == analysis_name), None)

    if not analysis:
        return jsonify({'error': 'Analysis not found'}), 404

    try:
        rundir = analysis.rundir
    except Exception:
        rundir = None

    telemetry_events = []
    path = os.path.join(rundir, "telemetry.jsonl") if rundir else None
    if path and os.path.isfile(path):
        try:
            with open(path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        telemetry_events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except OSError:
            logger.exception(
                "Unexpected error reading telemetry for %s/%s", event_name, analysis_name
            )
            return jsonify({'error': 'Could not read telemetry'}), 500

    event_type = request.args.get('event_type')
    if event_type:
        telemetry_events = [e for e in telemetry_events if e.get('event_type') == event_type]

    since = request.args.get('since')
    if since:
        telemetry_events = [e for e in telemetry_events if e.get('timestamp', '') >= since]

    return jsonify({'telemetry': telemetry_events})


@bp.route('/<event_name>', methods=['POST'])
@require_auth
def create_analysis(event_name):
    """
    Add analysis to an event.

    Requires authentication.

    Parameters
    ----------
    event_name : str
        The event name.

    Returns
    -------
    json
        Created analysis data or error message.
    """
    try:
        payload = request.get_json(silent=True)
        if payload is None:
            return jsonify({'error': 'Invalid or missing JSON payload'}), 400

        data = AnalysisCreate(**payload)
        ledger = get_ledger()

        try:
            events = ledger.get_event(event_name)
        except (KeyError, ValueError):
            return jsonify({'error': 'Event not found'}), 404

        event = events[0]

        if any(p.name == data.name for p in event.productions):
            return jsonify({'error': 'Analysis already exists'}), 409

        analysis = Production(
            subject=event,
            name=data.name,
            pipeline=data.pipeline,
            comment=data.comment or '',
        )

        if data.dependencies:
            analysis.dependencies = data.dependencies

        if data.meta:
            analysis.meta.update(data.meta)

        event.add_production(analysis)
        ledger.update_event(event)

        return jsonify({'analysis': analysis.to_dict(event=False)}), 201

    except ValidationError as e:
        return jsonify({'error': 'Validation error', 'details': e.errors()}), 400
    except Exception as e:
        logger.exception("Unexpected error creating analysis")
        return jsonify({'error': str(e)}), 500


@bp.route('/<event_name>/<analysis_name>', methods=['PUT'])
@require_auth
def update_analysis(event_name, analysis_name):
    """
    Update analysis.

    Requires authentication.

    Parameters
    ----------
    event_name : str
        The event name.
    analysis_name : str
        The analysis name.

    Returns
    -------
    json
        Updated analysis data or error message.
    """
    try:
        payload = request.get_json(silent=True)
        if payload is None:
            return jsonify({'error': 'Invalid or missing JSON payload'}), 400

        data = AnalysisUpdate(**payload)
        ledger = get_ledger()

        try:
            events = ledger.get_event(event_name)
        except (KeyError, ValueError):
            return jsonify({'error': 'Event not found'}), 404

        event = events[0]
        analysis = next((p for p in event.productions if p.name == analysis_name), None)

        if not analysis:
            return jsonify({'error': 'Analysis not found'}), 404

        if data.status is not None:
            analysis.status = data.status
        if data.comment is not None:
            analysis.comment = data.comment
        if data.meta:
            analysis.meta.update(data.meta)

        ledger.update_event(event)
        return jsonify({'analysis': analysis.to_dict(event=False)})

    except ValidationError as e:
        return jsonify({'error': 'Validation error', 'details': e.errors()}), 400
    except Exception as e:
        logger.exception("Unexpected error updating analysis")
        return jsonify({'error': str(e)}), 500


@bp.route('/<event_name>/<analysis_name>', methods=['DELETE'])
@require_auth
def delete_analysis(event_name, analysis_name):
    """
    Delete analysis from event.

    Requires authentication.

    Parameters
    ----------
    event_name : str
        The event name.
    analysis_name : str
        The analysis name.

    Returns
    -------
    Empty response with 204 status on success, error message otherwise.
    """
    ledger = get_ledger()

    try:
        events = ledger.get_event(event_name)
    except (KeyError, ValueError):
        return jsonify({'error': 'Event not found'}), 404

    event = events[0]
    analysis = next((p for p in event.productions if p.name == analysis_name), None)

    if not analysis:
        return jsonify({'error': 'Analysis not found'}), 404

    event.productions.remove(analysis)
    ledger.update_event(event)
    return '', 204
