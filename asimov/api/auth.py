"""
Authentication module for the API.

This module provides simple API key authentication for the REST API.
SciTokens support will be added in a future PR.
"""

from functools import wraps
from flask import request, jsonify, g
from asimov import config
import logging
import yaml
import os
import secrets

logger = logging.getLogger(__name__)

#: Where the app keeps the identity providers it trusts (see asimov.identity).
PROVIDERS = "ASIMOV_IDENTITY_PROVIDERS"


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
        if secrets.compare_digest(token, str(valid_token)):
            return username
    return None


def _bearer(header):
    """The token in an Authorization header, or ``None``."""
    try:
        scheme, token = header.split(' ', 1)
    except ValueError:
        return None
    return token.strip() if scheme.lower() == 'bearer' else None


def identify(token):
    """
    Who a bearer token belongs to: an API key, or an identity provider's token.

    An API key is tried first. A token which isn't one is checked as an OIDC
    token if the app trusts any identity providers (#182); what it proves is
    put in ``g.identity`` for the rest of the request.

    Returns
    -------
    str or None
        The user's identifier, or ``None`` if the token is neither.
    """
    seen = g.get("_identified")
    if seen is not None and secrets.compare_digest(seen[0], token):
        # Already checked for this request.
        return seen[1]
    user = _identify(token)
    g._identified = (token, user)
    return user


def _identify(token):
    try:
        user = verify_token(token)
    except RuntimeError:
        # No API keys are configured; an identity token may still do.
        user = None
    if user:
        return user
    # Imported here: a context proxy at module level breaks autodoc.
    from flask import current_app

    providers = current_app.config.get(PROVIDERS)
    if not providers or token.count('.') != 2:
        return None
    from asimov.identity import InvalidToken

    try:
        identity = providers.verify(token)
    except InvalidToken as error:
        logger.info("Refused an identity token: %s", error)
        return None
    g.identity = identity
    return identity.principal.identifier


def authenticate():
    """
    Who the request is from, if it says.

    Unlike :func:`require_auth` this never refuses the request: it is for
    work which needs to know who is asking whether or not the endpoint
    insists on it.

    Returns
    -------
    str or None
        The username the request's token belongs to, or ``None`` if it has no
        valid token (or no tokens are configured).
    """
    header = request.headers.get('Authorization')
    token = _bearer(header) if header else None
    return identify(token) if token else None


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

            user = identify(token)
            if not user:
                return jsonify({'error': 'Invalid token'}), 401

            # Store user in request context
            g.current_user = user
            return f(*args, **kwargs)

        except ValueError:
            return jsonify({'error': 'Invalid authorization header'}), 401

    return decorated
