"""
Flask application factory for the asimov REST API.
"""

import os
import secrets
from flask import Flask
from flask_cors import CORS
from asimov import config
from .blueprints import events, analyses
from .errors import register_error_handlers


def create_app():
    """
    Create and configure Flask app.

    Returns
    -------
    Flask
        Configured Flask application instance.
    """
    app = Flask(__name__)

    # Configuration
    secret_key = config.get('api', 'secret_key', fallback=None)
    if not secret_key and not os.environ.get('ASIMOV_TESTING'):
        raise RuntimeError(
            "SECRET_KEY is not configured. Please set the 'api.secret_key' configuration "
            "to a strong, unpredictable value before starting the application."
        )
    # Generate a random key per process when running in API test mode so
    # no predictable literal leaks into networked environments.
    app.config['SECRET_KEY'] = secret_key or secrets.token_hex(32)

    # CORS for web interface
    cors_origins = config.get('api', 'cors_origins', fallback=None)

    if cors_origins:
        # Use configured, comma-separated list of allowed origins, scoped to API routes
        allowed_origins = [origin.strip() for origin in cors_origins.split(",") if origin.strip()]
        CORS(app, resources={r"/api/*": {"origins": allowed_origins}})
    elif app.config.get("ENV") == "development" or app.debug:
        # Only open permissive CORS in explicit development/debug mode.
        # Test suites use the Flask test client directly and don't need CORS.
        CORS(app, resources={r"/api/*": {"origins": "*"}})

    # Register blueprints
    app.register_blueprint(events.bp, url_prefix='/api/v1/events')
    app.register_blueprint(analyses.bp, url_prefix='/api/v1/analyses')

    # Register error handlers
    register_error_handlers(app)

    # Health check endpoint
    @app.route('/api/v1/health')
    def health_check():
        return {'status': 'ok', 'version': 'v1'}

    return app
