"""
Productions API blueprint.

Provides CRUD operations for analysis productions.
"""

from flask import Blueprint, request, jsonify
from pydantic import ValidationError
from asimov.api.utils import get_ledger
from asimov.api.auth import require_auth
from asimov.api.models import ProductionCreate, ProductionUpdate

bp = Blueprint('productions', __name__)


@bp.route('/<event_name>/<production_name>', methods=['GET'])
def get_production(event_name, production_name):
    """
    Get specific production from an event.

    Parameters
    ----------
    event_name : str
        The event name.
    production_name : str
        The production name.

    Returns
    -------
    json
        Production data if found, error message otherwise.
    """
    ledger = get_ledger()
    try:
        events = ledger.get_event(event_name)
    except KeyError:
        return jsonify({'error': 'Event not found'}), 404

    event = events[0]
    production = next((p for p in event.productions if p.name == production_name), None)

    if not production:
        return jsonify({'error': 'Production not found'}), 404

    return jsonify({'production': production.to_dict()})


@bp.route('/<event_name>', methods=['POST'])
@require_auth
def create_production(event_name):
    """
    Add production to an event.

    Requires authentication.

    Parameters
    ----------
    event_name : str
        The event name.

    Returns
    -------
    json
        Created production data or error message.
    """
    try:
        payload = request.get_json(silent=True)
        if payload is None:
            return jsonify({'error': 'Invalid or missing JSON payload'}), 400

        data = ProductionCreate(**payload)
        ledger = get_ledger()

        try:
            events = ledger.get_event(event_name)
        except KeyError:
            return jsonify({'error': 'Event not found'}), 404

        event = events[0]

        # Check if production already exists
        if any(p.name == data.name for p in event.productions):
            return jsonify({'error': 'Production already exists'}), 409

        # Add production using event method
        event.add_production(
            name=data.name,
            pipeline=data.pipeline,
            comment=data.comment,
            dependencies=data.dependencies
        )

        # Update metadata if provided
        production = next(p for p in event.productions if p.name == data.name)
        production.meta.update(data.meta)

        ledger.update_event(event)
        return jsonify({'production': production.to_dict()}), 201

    except ValidationError as e:
        return jsonify({'error': 'Validation error', 'details': e.errors()}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/<event_name>/<production_name>', methods=['PUT'])
@require_auth
def update_production(event_name, production_name):
    """
    Update production.

    Requires authentication.

    Parameters
    ----------
    event_name : str
        The event name.
    production_name : str
        The production name.

    Returns
    -------
    json
        Updated production data or error message.
    """
    try:
        payload = request.get_json(silent=True)
        if payload is None:
            return jsonify({'error': 'Invalid or missing JSON payload'}), 400

        data = ProductionUpdate(**payload)
        ledger = get_ledger()

        try:
            events = ledger.get_event(event_name)
        except KeyError:
            return jsonify({'error': 'Event not found'}), 404

        event = events[0]
        production = next((p for p in event.productions if p.name == production_name), None)

        if not production:
            return jsonify({'error': 'Production not found'}), 404

        if data.status:
            production.status = data.status
        if data.comment:
            production.comment = data.comment
        if data.meta:
            production.meta.update(data.meta)

        ledger.update_event(event)
        return jsonify({'production': production.to_dict()})

    except ValidationError as e:
        return jsonify({'error': 'Validation error', 'details': e.errors()}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/<event_name>/<production_name>', methods=['DELETE'])
@require_auth
def delete_production(event_name, production_name):
    """
    Delete production from event.

    Requires authentication.

    Parameters
    ----------
    event_name : str
        The event name.
    production_name : str
        The production name.

    Returns
    -------
    Empty response with 204 status on success, error message otherwise.
    """
    ledger = get_ledger()

    try:
        events = ledger.get_event(event_name)
    except KeyError:
        return jsonify({'error': 'Event not found'}), 404

    event = events[0]
    production = next((p for p in event.productions if p.name == production_name), None)

    if not production:
        return jsonify({'error': 'Production not found'}), 404

    event.productions.remove(production)
    ledger.update_event(event)
    return '', 204
