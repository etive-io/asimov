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
import secrets


def load_api_keys():
    """
    Load API keys from config file or environment variable.

    Priority order:
    1. _api_keys_cache (for testing only)
    2. ASIMOV_API_KEYS_FILE environment variable
    3. api_keys_file from config file
    4. ASIMOV_API_KEY environment variable (single key:user pair)

    Returns
    -------
    dict
        Dictionary mapping API keys to usernames.

    Raises
    ------
    RuntimeError
        If no API keys are configured in production (when TESTING env var is not set).
    """
    # Check for test cache first (for unit tests)
    global _api_keys_cache
    if _api_keys_cache is not None:
        return _api_keys_cache

    # Try environment variable for API keys file path
    keys_file = os.environ.get('ASIMOV_API_KEYS_FILE')

    # Fall back to config file
    if not keys_file:
        try:
            keys_file = config.get("api", "api_keys_file")
        except Exception:
            keys_file = None

    # Load from file if it exists
    if keys_file and os.path.exists(keys_file):
        try:
            with open(keys_file, 'r') as f:
                data = yaml.safe_load(f)
                keys = data.get('api_keys', {})
                if keys:
                    return keys
        except (OSError, IOError, yaml.YAMLError):
            # Ignore expected file and YAML parsing errors and fall back to
            # other configuration mechanisms.
            pass

    # Try single API key from environment variable
    single_key = os.environ.get('ASIMOV_API_KEY')
    if single_key:
        # Format: "token:username"
        if ':' in single_key:
            token, username = single_key.split(':', 1)
            return {token: username}
        else:
            # If no username specified, use 'api-user'
            return {single_key: 'api-user'}

    # If we're not in testing mode and no keys were found, fail securely
    if not os.environ.get('ASIMOV_TESTING'):
        raise RuntimeError(
            "No API keys configured. Set ASIMOV_API_KEYS_FILE or ASIMOV_API_KEY "
            "environment variable, or configure api_keys_file in asimov.conf"
        )

    # In testing mode, return empty dict (tests will inject keys via _api_keys_cache)
    return {}


# Module-level cache that can be overridden for testing
_api_keys_cache = None


def get_api_keys():
    """
    Get API keys, loading them if not cached.

    Returns
    -------
    dict
        Dictionary mapping API keys to usernames.
    """
    return load_api_keys()


def verify_token(token):
    """
    Verify API token using constant-time comparison.

    Parameters
    ----------
    token : str
        The API token to verify.

    Returns
    -------
    str or None
        Username if token is valid, None otherwise.
    """
    keys = get_api_keys()
    # Use constant-time comparison to prevent timing attacks
    for valid_token, username in keys.items():
        if secrets.compare_digest(token, valid_token):
            return username
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
