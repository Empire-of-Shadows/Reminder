import os
import logging
import asyncio
from typing import Dict, List, Any, Callable
from datetime import datetime, timedelta

import pytz
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.asynchronous.collection import AsyncCollection
from pymongo import UpdateOne

from utils.env import load_project_env
from storage.core.collection_config import CollectionConfig
from storage.core.collection_manager import CollectionManager
from storage.core.connection_pool import ConnectionPool
from storage.database_properties import DatabaseProperties
from storage.define_collections import DefineCollections

# Load environment variables from docker/.env
load_project_env()
primary = os.getenv("MONGO_URI")
logger = logging.getLogger("DatabaseManager")


class DatabaseManager(DefineCollections, DatabaseProperties):
    """
    Comprehensive MongoDB database manager with connection pooling,
    CRUD operations, caching, error handling, and performance optimization.
    """

    def __init__(self, primary_uri: str = None, **additional_uris):
        self.primary_uri = primary_uri or primary

        if not self.primary_uri:
            raise ValueError("Primary MongoDB URI not provided")

        # Create connection pools for each URI
        self.connection_pools = {}
        self.connection_pools['primary'] = ConnectionPool(self.primary_uri, connection_name='primary')

        self.databases: Dict[str, AsyncDatabase] = {}
        self.collections: Dict[str, CollectionManager] = {}
        self._collection_configs: Dict[str, CollectionConfig] = {}
        self._initialized = False
        self._lock = asyncio.Lock()

        # Define collection configurations with indexes
        self._define_collection_configs()

    @property
    def is_connected(self) -> bool:
        """Check if the database manager is initialized and connected."""
        return self._initialized

    async def initialize(self):
        """Initialize the database manager with connection pooling and collection setup."""
        if self._initialized:
            return

        async with self._lock:
            if self._initialized:
                return

            try:
                logger.info("Initializing DatabaseManager...")

                # Initialize all connection pools
                for name, pool in self.connection_pools.items():
                    await pool.initialize()
                    logger.info(f"Initialized {name} connection pool")

                # Dynamically discover and initialize databases from all connections
                for connection_name, pool in self.connection_pools.items():
                    try:
                        client = await pool.get_client()

                        # Get list of database names (excluding system databases)
                        db_names = await client.list_database_names()
                        non_system_dbs = [db for db in db_names if db not in ['admin', 'local', 'config']]

                        logger.info(
                            f"Found {len(non_system_dbs)} databases in {connection_name} connection: {non_system_dbs}")

                        # Initialize databases for this connection
                        for db_name in non_system_dbs:
                            # Use connection name as prefix if it's not primary to avoid conflicts
                            db_key = db_name
                            if connection_name != 'primary' and db_name in self.databases:
                                # If database name conflicts with primary, use connection prefix
                                db_key = f"{connection_name}_{db_name}"
                                logger.debug(
                                    f"Database name conflict: {db_name} exists in multiple connections. Using {db_key}")

                            self.databases[db_key] = client[db_name]
                            logger.debug(f"Initialized database '{db_key}' from {connection_name} connection")

                    except Exception as e:
                        logger.warning(f"Error discovering databases from {connection_name} connection: {e}")
                        continue

                # Initialize collections with managers
                await self._initialize_collections()

                # Create indexes
                await self._create_all_indexes()

                self._initialized = True
                logger.info(f"DatabaseManager initialized successfully with {len(self.databases)} databases")

            except Exception as e:
                logger.error(f"Failed to initialize DatabaseManager: {e}")
                raise

    async def _initialize_collections(self):
        """Initialize collection managers."""
        for config_key, config in self._collection_configs.items():
            try:
                # Get the appropriate client based on the config's connection
                connection_name = config.connection
                if connection_name not in self.connection_pools:
                    logger.warning(
                        f"Connection '{connection_name}' not available for {config_key}, falling back to primary")
                    connection_name = 'primary'

                client = await self.connection_pools[connection_name].get_client()
                database = client[config.database]
                collection = database[config.name]

                # Create capped collection if specified
                if config.capped:
                    try:
                        await database.create_collection(
                            config.name,
                            capped=True,
                            size=config.max_size,
                            max=config.max_documents
                        )
                    except Exception:
                        # Collection might already exist
                        pass

                manager = CollectionManager(collection, config)
                self.collections[config_key] = manager

                logger.debug(f"Initialized collection manager for {config_key} on {connection_name} connection")

            except Exception as e:
                logger.error(f"Error initializing collection {config_key}: {e}")
                raise

    async def _create_all_indexes(self):
        """Create indexes for all collections."""
        for config_key, manager in self.collections.items():
            try:
                await manager.create_indexes()
            except Exception as e:
                logger.warning(f"Error creating indexes for {config_key}: {e}")

    def _ensure_initialized(self):
        """Ensure the database manager is initialized."""
        if not self._initialized:
            raise RuntimeError("DatabaseManager not initialized. Call initialize() first.")

    # Collection Access Methods

    def get_database(self, name: str) -> AsyncDatabase:
        """
        Get a database by name.

        Args:
            name: Database name

        Returns:
            Database instance
        """
        self._ensure_initialized()
        if name in self.databases:
            return self.databases[name]
        # Not discovered at init (the DB has no data yet, so it isn't enumerated
        # by list_database_names). Bind a lazy handle from the primary connection;
        # MongoDB creates the database on first write. This mirrors how predefined
        # collection configs (e.g. database='ImperialReminder') are bound.
        primary = self.connection_pools.get('primary')
        if primary is None:
            raise ValueError(f"Database '{name}' not found and no primary connection available")
        self.databases[name] = primary.client[name]
        return self.databases[name]

    def get_collection_manager(self, collection_key: str) -> CollectionManager:
        """
        Get a collection manager by key.

        Args:
            collection_key: Collection configuration key

        Returns:
            CollectionManager instance
        """
        self._ensure_initialized()
        if collection_key not in self.collections:
            raise ValueError(f"Collection '{collection_key}' not configured")
        return self.collections[collection_key]

    def get_raw_collection(self, database_name: str, collection_name: str) -> AsyncCollection:
        """
        Get raw collection access for advanced operations.

        Args:
            database_name: Database name
            collection_name: Collection name

        Returns:
            Raw collection instance
        """
        database = self.get_database(database_name)
        return database[collection_name]

    def get_client(self, connection_name: str = 'primary') -> AsyncMongoClient:
        """
        Get a client for a specific connection.

        Args:
            connection_name: Name of the connection pool ('primary', 'secondary', 'third', etc.)

        Returns:
            AsyncMongoClient instance
        """
        self._ensure_initialized()
        if connection_name not in self.connection_pools:
            raise ValueError(f"Connection '{connection_name}' not configured")
        return self.connection_pools[connection_name].client

    async def get_client_async(self, connection_name: str = 'primary') -> AsyncMongoClient:
        """
        Get a client for a specific connection asynchronously.

        Args:
            connection_name: Name of the connection pool ('primary', 'secondary', 'third', etc.)

        Returns:
            AsyncMongoClient instance
        """
        self._ensure_initialized()
        if connection_name not in self.connection_pools:
            raise ValueError(f"Connection '{connection_name}' not configured")
        return await self.connection_pools[connection_name].get_client()

    # Utility Methods

    async def get_database_stats(self) -> Dict[str, Any]:
        """Get comprehensive database statistics."""
        self._ensure_initialized()

        stats = {
            'databases': {},
            'total_collections': 0,
            'total_documents': 0,
            'total_size': 0,
            'connections': {}
        }

        try:
            # Get stats for each connection
            for connection_name, pool in self.connection_pools.items():
                try:
                    client = await pool.get_client()
                    connection_stats = await client.admin.command('serverStatus')
                    stats['connections'][connection_name] = {
                        'ok': connection_stats.get('ok', 0),
                        'host': connection_stats.get('host', 'unknown'),
                        'version': connection_stats.get('version', 'unknown')
                    }
                except Exception as e:
                    stats['connections'][connection_name] = f"error: {e}"

            # Get database stats (using primary connection for existing logic)
            client = await self.connection_pools['primary'].get_client()

            for db_name, database in self.databases.items():
                db_stats = await database.command('dbStats')
                collection_stats = {}

                for collection_key, manager in self.collections.items():
                    if manager.config.database == db_name:
                        coll_stats = await manager.get_stats()
                        collection_stats[manager.name] = coll_stats
                        stats['total_documents'] += coll_stats.get('count', 0)
                        stats['total_size'] += coll_stats.get('size', 0)

                stats['databases'][db_name] = {
                    'collections': db_stats.get('collections', 0),
                    'dataSize': db_stats.get('dataSize', 0),
                    'indexSize': db_stats.get('indexSize', 0),
                    'collection_details': collection_stats
                }

                stats['total_collections'] += db_stats.get('collections', 0)

            return stats

        except Exception as e:
            logger.error(f"Error getting database stats: {e}")
            return stats

    async def health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check on all connections."""
        health_status = {
            'status': 'healthy',
            'timestamp': datetime.now(tz=pytz.UTC).isoformat(),
            'connections': {},
            'databases': {},
            'collections': {}
        }

        try:
            # Check all connection pools
            for name, pool in self.connection_pools.items():
                try:
                    client = await pool.get_client()
                    await client.admin.command('ping')
                    health_status['connections'][name] = 'healthy'
                except Exception as e:
                    health_status['connections'][name] = f'error: {e}'
                    health_status['status'] = 'degraded'

            # Check each database (using primary connection for existing databases)
            for db_name in self.databases.keys():
                try:
                    db = self.get_database(db_name)
                    await db.command('ping')
                    health_status['databases'][db_name] = 'healthy'
                except Exception as e:
                    health_status['databases'][db_name] = f'error: {e}'
                    health_status['status'] = 'degraded'

            # Check collection managers
            for collection_key, manager in self.collections.items():
                try:
                    await manager.count_documents({})
                    health_status['collections'][collection_key] = 'healthy'
                except Exception as e:
                    health_status['collections'][collection_key] = f'error: {e}'
                    health_status['status'] = 'degraded'

        except Exception as e:
            health_status['status'] = 'unhealthy'
            health_status['error'] = str(e)

        return health_status

    async def close(self):
        """Close all database connections and cleanup resources."""
        try:
            logger.info("Closing DatabaseManager...")

            # Clear collections and databases
            self.collections.clear()
            self.databases.clear()

            # Close all connection pools
            for name, pool in self.connection_pools.items():
                await pool.close()
                logger.info(f"Closed {name} connection pool")

            self.connection_pools.clear()
            self._initialized = False
            logger.info("DatabaseManager closed successfully")

        except Exception as e:
            logger.error(f"Error closing DatabaseManager: {e}")


# Global database manager instance
db_manager = DatabaseManager()
