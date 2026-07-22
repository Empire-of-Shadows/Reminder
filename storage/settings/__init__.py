"""ImperialReminder's storage seam (bot-owned, NEVER vendored).

The only storage code ImperialReminder writes by hand: ``bindings`` (URIs, cache
choice, watched collections) and ``collections`` (the collection registry AND the
shared ``db_manager`` singleton the rest of the bot imports as
``from storage.settings.collections import db_manager``).

This module is intentionally a docstring only. Do NOT re-export from ``.collections``
here: importing ``.collections`` constructs ``db_manager`` (which needs the Mongo env),
so eager re-exports would make every ``storage.settings`` import require a configured
environment.
"""
