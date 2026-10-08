"""
Flask application factory for the asimov REST API.
"""

import os
import secrets
from flask import Flask
from flask_cors import CORS
from asimov import config
from .blueprints import events, analyses
from . import projects
from .errors import register_error_handlers


def configured_registry():
    """
    The registry the configuration names, if it names one.

    ``$ASIMOV_REGISTRY``, or ``registry`` in the ``[api]`` section, is the path
    of a registry file (see :class:`asimov.registry.FileRegistry`).

    Returns
    -------
    asimov.registry.FileRegistry or None
    """
    from asimov.registry import FileRegistry

    path = os.environ.get('ASIMOV_REGISTRY') or config.get('api', 'registry', fallback=None)
    return FileRegistry(path) if path else None


def create_app(registry=None):
    """
    Create and configure Flask app.

    Parameters
    ----------
    registry : asimov.registry.ProjectRegistry, optional
        The projects to serve. Defaults to the one the configuration names
        (see :func:`configured_registry`). Without one, the API serves the
        project the configuration names, on the routes without a project in
        them, as it always has.

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
        origins = cors_origins.strip() if cors_origins.strip() == '*' \
            else [o.strip() for o in cors_origins.split(",") if o.strip()]
        CORS(app, origins=origins)
    elif app.config.get("ENV") == "development" or app.debug:
        # Only open permissive CORS in explicit development/debug mode.
        # Test suites use the Flask test client directly and don't need CORS.
        CORS(app, origins="*")

    # Register blueprints. The routes without a project in them serve the
    # instance's only project, if it has a registry (see asimov.api.projects).
    app.register_blueprint(events.bp, url_prefix='/api/v1/events')
    app.register_blueprint(analyses.bp, url_prefix='/api/v1/analyses')
    app.register_blueprint(
        events.bp, name='project_events',
        url_prefix='/api/v1/projects/<project>/events')
    app.register_blueprint(
        analyses.bp, name='project_analyses',
        url_prefix='/api/v1/projects/<project>/analyses')
    projects.init_app(app, registry if registry is not None else configured_registry())

    # Register error handlers
    register_error_handlers(app)

    # Health check endpoint
    @app.route('/api/v1/health')
    def health_check():
        return {'status': 'ok', 'version': 'v1'}

    return app
