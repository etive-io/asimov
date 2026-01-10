"""
Flask application factory for the asimov REST API.
"""

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
    app.config['SECRET_KEY'] = config.get('api', 'secret_key', fallback='dev-secret-key')

    # CORS for web interface
    CORS(app)

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
