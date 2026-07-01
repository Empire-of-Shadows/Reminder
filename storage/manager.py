"""Concrete DatabaseManager for ImperialReminder (bot-owned, NOT vendored).

Composes the vendored engine base (``DatabaseManagerBase``) with this bot's two mixins
(``DefineCollections`` + ``DatabaseProperties``) and instantiates the shared ``db_manager``
the rest of the bot imports. The engine stays generic; the bot supplies its collections.

Previously this composition + the ``db_manager`` instance lived at the bottom of
``storage/database_manager.py``; that file is now the vendored engine base, so the concrete
instance moved here. Import sites use ``from storage.manager import db_manager``.
"""

from __future__ import annotations

from storage.database_manager import DatabaseManagerBase
from storage.define_collections import DefineCollections
from storage.database_properties import DatabaseProperties
from storage import bindings


class DatabaseManager(DatabaseManagerBase, DefineCollections, DatabaseProperties):
    """ImperialReminder's MongoDB manager: engine core + this bot's collection registry."""


# Global database manager instance (shared across the bot; initialized at startup).
db_manager = DatabaseManager(
    primary_uri=bindings.MONGO_URIS["primary"],
    cache=bindings.build_cache(),
    watched_collections=bindings.WATCHED_COLLECTIONS,
)
