"""
Productions API blueprint.

Provides CRUD operations for analysis productions.
"""

import logging
from flask import Blueprint, request, jsonify
from pydantic import ValidationError
from asimov.api.utils import get_ledger
from asimov.api.auth import require_auth
from asimov.api.models import ProductionCreate, ProductionUpdate
from asimov.event import Production

bp = Blueprint('productions', __name__)
logger = logging.getLogger(__name__)


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

    return jsonify({'production': production.to_dict(event=False)})


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

        # Workaround for deepcopy issue: temporarily remove ledger from event.meta
        # This prevents FileLock pickling errors when Production.__init__ and to_dict()
        # do deepcopy(event.meta)
        # NOTE: This may be redundant now that YAMLLedger implements __getstate__/__setstate__,
        # but kept for safety until thoroughly tested.
        ledger_backup = event.meta.pop('ledger', None)
        
        try:
            # Create production object
            production = Production(
                subject=event,
                name=data.name,
                pipeline=data.pipeline,
                comment=data.comment or '',
            )
            
            # Set dependencies if provided
            if data.dependencies:
                production.dependencies = data.dependencies
            
            # Update metadata if provided
            if data.meta:
                production.meta.update(data.meta)

            # Add production to event
            event.add_production(production)
            
            # Update ledger before restoring ledger reference
            ledger.update_event(event)
            
            return jsonify({'production': production.to_dict(event=False)}), 201
        finally:
            # Restore ledger to event.meta
            if ledger_backup is not None:
                event.meta['ledger'] = ledger_backup

    except ValidationError as e:
        return jsonify({'error': 'Validation error', 'details': e.errors()}), 400
    except Exception as e:
        logger.exception("Unexpected error creating production")
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

        # Workaround for deepcopy issue: temporarily remove ledger from event.meta
        # NOTE: This may be redundant now that YAMLLedger implements __getstate__/__setstate__,
        # but kept for safety until thoroughly tested.
        ledger_backup = event.meta.pop('ledger', None)
        
        try:
            if data.status:
                production.status = data.status
            if data.comment:
                production.comment = data.comment
            if data.meta:
                production.meta.update(data.meta)

            ledger.update_event(event)
            return jsonify({'production': production.to_dict(event=False)})
        finally:
            # Restore ledger to event.meta
            if ledger_backup is not None:
                event.meta['ledger'] = ledger_backup

    except ValidationError as e:
        return jsonify({'error': 'Validation error', 'details': e.errors()}), 400
    except Exception as e:
        logger.exception("Unexpected error updating production")
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
