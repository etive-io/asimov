Principals: who is making a change
==================================

A *principal* names the party behind an action on a project: a person, an agent
(such as an MCP client), or the monitor, and who they are acting for.
:class:`asimov.principal.Principal` is the one definition shared by the audit
trail, accounting and guardrails, so each of them attributes changes the same
way.

A principal says *who*. It decides nothing about what they may do, and
asimov does no authentication here. The identity layer which will supply a
principal with a group and role (OIDC login, groups and project grants) plugs in
through :func:`asimov.principal.set_principal_provider`.

Making a principal
------------------

.. code-block:: python

    from asimov.principal import Principal

    Principal.person("dw")
    Principal.agent("claude-session-1", acting_for=Principal.person("dw"))
    Principal.monitor()
    Principal.local_user()      # the operating system user

``group`` and ``role`` are optional. They are set by the identity layer, and are
recorded as they were at the time, since membership changes.

A principal serialises with ``to_dict()`` and ``Principal.from_dict()``. A lone
person is just ``{kind: person, identifier: dw}``; ``acting for`` nests.

``to_prov()`` gives the principal as W3C PROV agents in the form of the
provenance export: a ``prov:Person`` or ``prov:SoftwareAgent``, linked to who it
acts for with ``prov:actedOnBehalfOf``.

Who is acting
-------------

:func:`asimov.principal.current_principal` answers "who is making this change
now", in this order:

1. the principal chosen with :func:`~asimov.principal.acting_as`;
2. the active project's own, ``ProjectContext.principal``;
3. what the provider from ``set_principal_provider`` returns;
4. the local user.

On the command line nothing needs setting up: changes are attributed to the
local user, and ``asimov monitor`` runs as the monitor.

A service attributes each request to its caller:

.. code-block:: python

    with acting_as(Principal.agent("session-7", acting_for=Principal.person("dw"))):
        apply_page(...)

``acting_as`` applies to the current thread or task, so requests handled side by
side, even for the same project, are attributed to their own callers.

Who requested an analysis
-------------------------

When an analysis is applied, asimov records who requested it under ``requested
by`` on the analysis, and ``analysis.requested_by`` gives it back as a
``Principal``. The value always comes from the current principal. A ``requested
by`` in a blueprint is replaced, so a blueprint cannot name someone else.
Applying a blueprint again to an analysis which already exists doesn't change who
requested it.

This covers analyses applied with ``asimov apply`` as ``kind: analysis``,
``kind: projectanalysis`` and ``kind: analysisbundle``. Analyses written inline in
an event blueprint aren't covered, since applying those doesn't work today.

API reference
-------------

.. autoclass:: asimov.principal.Principal
   :members:

.. autofunction:: asimov.principal.current_principal

.. autofunction:: asimov.principal.acting_as

.. autofunction:: asimov.principal.set_principal_provider
