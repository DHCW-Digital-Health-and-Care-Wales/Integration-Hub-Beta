"""
Route modules — plain view functions grouped by concern, registered onto the
Flask app in ``dashboard.app`` via explicit ``app.add_url_rule(...)`` calls.

These are intentionally *not* Flask ``Blueprint`` objects: a ``Blueprint``
always namespaces its endpoints as ``blueprintname.funcname`` (there is no
supported way to opt out of this — see ``flask.sansio.blueprints.
BlueprintSetupState.add_url_rule``), which would silently break the 80+
``url_for(...)`` calls across the Jinja templates that reference flat
endpoint names such as ``url_for('index')``. Registering the same plain
functions directly on ``app`` with an explicit ``endpoint=`` keeps every
existing endpoint name — and therefore every template and test patch target
that doesn't reference the route's *module* — unchanged.
"""

from __future__ import annotations
