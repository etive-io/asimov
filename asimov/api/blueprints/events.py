"""
Events API blueprint.

Provides CRUD operations for gravitational wave events.
"""

from flask import Blueprint, request, jsonify, g
from pydantic import ValidationError
from asimov.event import Event
from asimov.api.utils import get_ledger
from asimov.api.auth import require_auth
from asimov.api.models import EventCreate, EventUpdate

bp = Blueprint('events', __name__)


@bp.route('/', methods=['GET'])
def list_events():
    """
    List all events.

    Returns
    -------
    json
        List of all events with their data.
    """
    ledger = get_ledger()
    events = ledger.get_event()
    return jsonify({
        'events': [e.to_dict() for e in events]
    })


@bp.route('/<name>', methods=['GET'])
def get_event(name):
    """
    Get specific event by name.

    Parameters
    ----------
    name : str
        The event name.

    Returns
    -------
    json
        Event data if found, error message otherwise.
    """
    ledger = get_ledger()
    try:
        events = ledger.get_event(name)
        if not events:
            return jsonify({'error': 'Event not found'}), 404
        return jsonify({'event': events[0].to_dict()})
    except KeyError:
        return jsonify({'error': 'Event not found'}), 404


@bp.route('/', methods=['POST'])
@require_auth
def create_event():
    """
    Create new event.

    Requires authentication.

    Returns
    -------
    json
        Created event data or error message.
    """
    try:
        data = EventCreate(**request.json)
        ledger = get_ledger()

        # Check if event already exists
        try:
            existing = ledger.get_event(data.name)
            if existing:
                return jsonify({'error': 'Event already exists'}), 409
        except KeyError:
            # Event doesn't exist, which is what we want
            pass

        # Create event
        event = Event(name=data.name, ledger=ledger)
        if data.repository:
            event.repository.url = data.repository
        if data.working_directory:
            event.work_dir = data.working_directory
        event.meta.update(data.meta)

        ledger.add_event(event)
        return jsonify({'event': event.to_dict()}), 201

    except ValidationError as e:
        return jsonify({'error': 'Validation error', 'details': e.errors()}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/<name>', methods=['PUT'])
@require_auth
def update_event(name):
    """
    Update existing event.

    Requires authentication.

    Parameters
    ----------
    name : str
        The event name.

    Returns
    -------
    json
        Updated event data or error message.
    """
    try:
        data = EventUpdate(**request.json)
        ledger = get_ledger()

        try:
            events = ledger.get_event(name)
        except KeyError:
            return jsonify({'error': 'Event not found'}), 404

        event = events[0]

        if data.repository:
            event.repository.url = data.repository
        if data.working_directory:
            event.work_dir = data.working_directory
        if data.meta:
            event.meta.update(data.meta)

        ledger.update_event(event)
        return jsonify({'event': event.to_dict()})

    except ValidationError as e:
        return jsonify({'error': 'Validation error', 'details': e.errors()}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/<name>', methods=['DELETE'])
@require_auth
def delete_event(name):
    """
    Delete event.

    Requires authentication.

    Parameters
    ----------
    name : str
        The event name.

    Returns
    -------
    Empty response with 204 status on success, error message otherwise.
    """
    ledger = get_ledger()
    try:
        events = ledger.get_event(name)
    except KeyError:
        return jsonify({'error': 'Event not found'}), 404

    ledger.delete_event(events[0].name)
    return '', 204


@bp.route('/<name>/productions', methods=['GET'])
def list_productions(name):
    """
    List all productions for an event.

    Parameters
    ----------
    name : str
        The event name.

    Returns
    -------
    json
        List of productions for the event.
    """
    ledger = get_ledger()
    try:
        events = ledger.get_event(name)
    except KeyError:
        return jsonify({'error': 'Event not found'}), 404

    event = events[0]
    return jsonify({
        'productions': [p.to_dict() for p in event.productions]
    })
