"""
Flask application factory for the asimov REST API.
"""

import os
from flask import Flask
from flask_cors import CORS
from asimov import config
from .blueprints import events, productions
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
    # Allow tests to bypass secret key requirement using ASIMOV_TESTING env var
    if not secret_key and not os.environ.get('ASIMOV_TESTING'):
        raise RuntimeError(
            "SECRET_KEY is not configured. Please set the 'api.secret_key' configuration "
            "to a strong, unpredictable value before starting the application."
        )
    app.config['SECRET_KEY'] = secret_key or 'test-secret-key-only-for-testing'

    # CORS for web interface
    cors_origins = config.get('api', 'cors_origins', fallback=None)

    if cors_origins:
        # Use configured, comma-separated list of allowed origins, scoped to API routes
        allowed_origins = [origin.strip() for origin in cors_origins.split(",") if origin.strip()]
        CORS(app, resources={r"/api/*": {"origins": allowed_origins}})
    else:
        # If no explicit CORS configuration is provided, only enable permissive CORS in development/testing.
        # In production, CORS must be explicitly configured via the 'api.cors_origins' setting.
        if app.config.get("ENV") == "development" or app.debug or os.environ.get('ASIMOV_TESTING'):
            CORS(app, resources={r"/api/*": {"origins": "*"}})

    # Register blueprints
    app.register_blueprint(events.bp, url_prefix='/api/v1/events')
    app.register_blueprint(productions.bp, url_prefix='/api/v1/productions')

    # Register error handlers
    register_error_handlers(app)

    # Health check endpoint
    @app.route('/api/v1/health')
    def health_check():
        return {'status': 'ok', 'version': 'v1'}

    return app
