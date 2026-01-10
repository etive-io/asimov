"""
Authentication module for the API.

This module provides simple API key authentication for the REST API.
SciTokens support will be added in a future PR.
"""

from functools import wraps
from flask import request, jsonify, g
from asimov import config
import yaml
import os


def load_api_keys():
    """
    Load API keys from config file.

    Returns
    -------
    dict
        Dictionary mapping API keys to usernames.
    """
    try:
        keys_file = config.get("api", "api_keys_file")
        if os.path.exists(keys_file):
            with open(keys_file, 'r') as f:
                data = yaml.safe_load(f)
                return data.get('api_keys', {})
    except Exception:
        pass
    return {}


API_KEYS = load_api_keys()


def verify_token(token):
    """
    Verify API token.

    Parameters
    ----------
    token : str
        The API token to verify.

    Returns
    -------
    str or None
        Username if token is valid, None otherwise.
    """
    if token in API_KEYS:
        return API_KEYS[token]  # Returns username/identifier
    return None


def require_auth(f):
    """
    Decorator for endpoints requiring authentication.

    Parameters
    ----------
    f : function
        The endpoint function to decorate.

    Returns
    -------
    function
        The decorated function.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization')

        if not auth_header:
            return jsonify({'error': 'Authorization header missing'}), 401

        try:
            scheme, token = auth_header.split(' ', 1)
            if scheme.lower() != 'bearer':
                return jsonify({'error': 'Invalid authorization scheme'}), 401

            user = verify_token(token)
            if not user:
                return jsonify({'error': 'Invalid token'}), 401

            # Store user in request context
            g.current_user = user
            return f(*args, **kwargs)

        except ValueError:
            return jsonify({'error': 'Invalid authorization header'}), 401

    return decorated
