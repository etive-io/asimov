"""
Serving more than one project from one API (see #184).

Every request which is for a project (the ``events`` and ``analyses`` routes)
is handled in four steps, before the route's own code runs:

1. Find out who is asking, and name the project: from the URL
   (``/api/v1/projects/<project>/events/...``), or, on the older routes
   without a project in them, the only project the instance has.
2. Check that they may. ``read`` for requests which only look, ``write`` for
   the rest (see :mod:`asimov.access`).
3. Make the project's context active for the request, with the caller as the
   principal, so that the route works on that project's ledger and what it
   records is attributed to them.
4. When the request ends, close the project's ledger.

A project the caller may not read looks the same as one which doesn't exist,
so that asking doesn't reveal which projects there are.

Without a registry the API behaves as it always has, serving the project its
configuration names, and the project routes don't exist.
"""

import contextlib
import logging

from flask import g, jsonify, request

from asimov import access
from asimov.access import AccessDenied
from asimov.api.auth import authenticate
from asimov.principal import Principal, acting_as
from asimov.registry import AmbiguousProject, UnknownProject

logger = logging.getLogger(__name__)

#: The blueprints whose routes are for a project.
SCOPED = frozenset({"events", "analyses", "project_events", "project_analyses"})

_SAFE = frozenset({"GET", "HEAD", "OPTIONS"})

def _not_found():
    return jsonify({"error": "Project not found"}), 404


def _principal():
    username = authenticate()
    return Principal.person(username) if username else Principal.person("anonymous")


def init_app(app, registry):
    """
    Make ``app`` resolve a project for each request.

    Parameters
    ----------
    app : flask.Flask
    registry : asimov.registry.ProjectRegistry or None
        The projects it serves. ``None`` leaves the API as it was.
    """
    app.config["ASIMOV_PROJECT_REGISTRY"] = registry

    @app.url_value_preprocessor
    def take_project_name(endpoint, values):
        # The routes' own functions don't take a project: it is dealt with here.
        g.project_name = values.pop("project", None) if values else None

    @app.before_request
    def enter_project():
        if request.blueprint not in SCOPED:
            return None
        if registry is None:
            # The project routes need a registry. The others work as they did.
            return _not_found() if getattr(g, "project_name", None) else None
        principal = _principal()
        try:
            entry = registry.get(getattr(g, "project_name", None))
        except (UnknownProject, AmbiguousProject):
            return _not_found()
        try:
            access.authorize(principal, entry, access.READ)
        except AccessDenied:
            return _not_found()
        if request.method not in _SAFE:
            try:
                access.authorize(principal, entry, access.WRITE)
            except AccessDenied as error:
                return jsonify({"error": str(error)}), 403
        try:
            context = entry.context()
        except Exception:
            logger.exception("Could not open the project %s", entry.name)
            return jsonify({"error": "Project unavailable"}), 503
        stack = contextlib.ExitStack()
        stack.enter_context(context.activate())
        stack.enter_context(acting_as(principal))
        g.project_stack = stack
        g.project_context = context
        g.project_entry = entry
        return None

    @app.teardown_request
    def leave_project(error):
        stack = g.pop("project_stack", None)
        context = g.pop("project_context", None)
        if stack is not None:
            stack.close()
        if context is not None:
            context.reload_ledger()

    def list_projects():
        """
        List the projects the caller may read.

        Only the name and owning groups are given: not where a project is, or
        how its ledger is reached.
        """
        if registry is None:
            return jsonify({"error": "Resource not found"}), 404
        principal = _principal()
        visible = []
        for entry in registry.list():
            try:
                access.authorize(principal, entry, access.READ)
            except AccessDenied:
                continue
            visible.append({"name": entry.name, "groups": list(entry.groups)})
        return jsonify({"projects": visible})

    app.add_url_rule("/api/v1/projects/", "list_projects", list_projects, methods=["GET"])
