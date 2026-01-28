"""
Error handlers for the API.
"""

from flask import jsonify
from pydantic import ValidationError
from asimov.event import DescriptionException
from asimov.pipeline import PipelineException


def register_error_handlers(app):
    """
    Register error handlers for the Flask app.

    Parameters
    ----------
    app : Flask
        The Flask application instance.
    """

    @app.errorhandler(ValidationError)
    def handle_validation_error(e):
        """Handle Pydantic validation errors."""
        return jsonify({
            'error': 'Validation error',
            'details': e.errors()
        }), 400

    @app.errorhandler(DescriptionException)
    def handle_description_error(e):
        """Handle asimov DescriptionException."""
        return jsonify({
            'error': e.message,
            'production': e.production
        }), 400

    @app.errorhandler(PipelineException)
    def handle_pipeline_error(e):
        """Handle asimov PipelineException."""
        return jsonify({
            'error': str(e),
            'issue': getattr(e, 'issue', None)
        }), 500

    @app.errorhandler(404)
    def handle_not_found(e):
        """Handle 404 Not Found errors."""
        return jsonify({'error': 'Resource not found'}), 404

    @app.errorhandler(500)
    def handle_server_error(e):
        """Handle 500 Internal Server Error."""
        return jsonify({'error': 'Internal server error'}), 500
