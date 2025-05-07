# utils/migration_manager.py
import logging
import datetime
import json
import os
from typing import Dict, List, Any, Optional

class MigrationManager:
    """Manages database schema migrations"""
    
    def __init__(self, db_manager):
        self.db = db_manager
        self.logger = logging.getLogger('axis_bot.migrations')
        
        # Schema versions for collections
        self.collection_versions = {
            "leveling_users": 2,
            "leveling_settings": 1,
            "moderation_blacklist": 2,
            "moderation_whitelist": 1,
            "moderation_settings": 1,
            "moderation_logs": 2,
            "starboard_settings": 1,
            "starboard_posts": 2,
            "marketplace_settings": 1,
            "marketplace_posts": 2,
            "tickets_settings": 1,
            "tickets_active": 2,
            "tickets_archived": 2,
            "fun_settings": 1,
            "utility_settings": 1
        }
        
        # Migration scripts directory
        self.migrations_dir = "migrations"
        
        # Ensure migrations directory exists
        os.makedirs(self.migrations_dir, exist_ok=True)
    
    async def check_all_collections(self):
        """Check and migrate all collections if needed"""
        self.logger.info("Checking schema versions for all collections")
        
        # Log collections to check
        collection_names = list(self.collection_versions.keys())
        self.logger.info(f"Collections to check: {', '.join(collection_names)}")
        
        # Create migration context for tracking migrations
        migration_context = {
            "start_time": datetime.datetime.now(),
            "collections_checked": [],
            "migrations_performed": [],
            "errors": []
        }
        
        # Check each collection
        for collection, target_version in self.collection_versions.items():
            migration_context["collections_checked"].append(collection)
            
            try:
                await self.check_collection_version(collection, target_version, migration_context)
            except Exception as e:
                error_info = {
                    "collection": collection,
                    "error": str(e),
                    "time": datetime.datetime.now()
                }
                migration_context["errors"].append(error_info)
                self.logger.error(f"Error checking {collection}: {str(e)}", exc_info=True)
        
        # Log migration summary
        migration_context["end_time"] = datetime.datetime.now()
        migration_context["duration"] = (migration_context["end_time"] - migration_context["start_time"]).total_seconds()
        
        # Save migration log
        await self._save_migration_log(migration_context)
        
        # Return summary
        return {
            "collections_checked": len(migration_context["collections_checked"]),
            "migrations_performed": len(migration_context["migrations_performed"]),
            "errors": len(migration_context["errors"]),
            "duration_seconds": migration_context["duration"]
        }
    
    async def check_collection_version(self, collection: str, target_version: int, context: Dict = None):
        """Check and update schema version for a collection"""
        if context is None:
            context = {
                "start_time": datetime.datetime.now(),
                "collections_checked": [collection],
                "migrations_performed": [],
                "errors": []
            }
        
        self.logger.info(f"Checking schema version for {collection}")
        
        # Get current version from metadata
        metadata = await self.db.find_one("system_metadata", {"collection": collection})
        
        if not metadata:
            # Create metadata entry
            self.logger.info(f"No metadata found for {collection}, creating with version {target_version}")
            
            await self.db.insert_one("system_metadata", {
                "collection": collection,
                "schema_version": target_version,
                "created_at": datetime.datetime.now(),
                "updated_at": datetime.datetime.now()
            })
            
            return
        
        current_version = metadata.get("schema_version", 1)
        
        if current_version < target_version:
            self.logger.info(f"Migrating {collection} from v{current_version} to v{target_version}")
            
            # Perform migration
            await self.migrate_collection(collection, current_version, target_version, context)
        else:
            self.logger.info(f"Collection {collection} is up to date (v{current_version})")
    
    async def migrate_collection(self, collection: str, current_version: int, target_version: int, context: Dict):
        """Migrate a collection schema from one version to another"""
        # Create a backup first
        backup_name = f"{collection}_before_migration_v{current_version}_to_v{target_version}"
        await self.db.backup_collection(collection, backup_name)
        
        self.logger.info(f"Created backup: {backup_name}")
        
        # Execute migrations one version at a time
        for version in range(current_version + 1, target_version + 1):
            migration_start = datetime.datetime.now()
            
            try:
                # Find migration script
                migration_function = self._get_migration_function(collection, version)
                
                if migration_function:
                    # Execute the migration
                    self.logger.info(f"Executing migration to v{version}")
                    await migration_function(self.db)
                    
                    # Update schema version
                    await self.db.update_one(
                        "system_metadata",
                        {"collection": collection},
                        {"$set": {
                            "schema_version": version,
                            "updated_at": datetime.datetime.now(),
                            "last_migration": datetime.datetime.now()
                        }}
                    )
                    
                    # Log migration
                    migration_info = {
                        "collection": collection,
                        "from_version": version - 1,
                        "to_version": version,
                        "start_time": migration_start,
                        "end_time": datetime.datetime.now(),
                        "duration": (datetime.datetime.now() - migration_start).total_seconds()
                    }
                    
                    context["migrations_performed"].append(migration_info)
                    
                    self.logger.info(f"Migrated {collection} to v{version}")
                else:
                    self.logger.warning(f"No migration script found for {collection} to v{version}")
            except Exception as e:
                error_info = {
                    "collection": collection,
                    "from_version": version - 1,
                    "to_version": version,
                    "error": str(e),
                    "time": datetime.datetime.now()
                }
                
                context["errors"].append(error_info)
                self.logger.error(f"Error migrating {collection} to v{version}: {str(e)}", exc_info=True)
                
                # Don't continue with further migrations if one fails
                break
    
    def _get_migration_function(self, collection, version):
        """Get the migration function for a specific collection and version"""
        # Check for migration function in this class
        method_name = f"_migrate_{collection}_to_v{version}"
        if hasattr(self, method_name) and callable(getattr(self, method_name)):
            return getattr(self, method_name)
        
        # Check for external migration script
        script_path = os.path.join(self.migrations_dir, f"{collection}_v{version}.py")
        if os.path.exists(script_path):
            # Load external migration
            migration_module = self._load_migration_script(script_path)
            if migration_module and hasattr(migration_module, "migrate"):
                return migration_module.migrate
        
        return None
    
    def _load_migration_script(self, script_path):
        """Load a migration script module"""
        import importlib.util
        
        try:
            # Load the module
            spec = importlib.util.spec_from_file_location("migration_module", script_path)
            migration_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(migration_module)
            
            return migration_module
        except Exception as e:
            self.logger.error(f"Error loading migration script {script_path}: {str(e)}", exc_info=True)
            return None
    
    async def _save_migration_log(self, context):
        """Save migration log to database and file"""
        # Save to database
        await self.db.insert_one("system_migration_logs", {
            "timestamp": datetime.datetime.now(),
            "collections_checked": context["collections_checked"],
            "migrations_performed": context["migrations_performed"],
            "errors": context["errors"],
            "duration": context["duration"]
        })
        
        # Save to file
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        log_file = os.path.join(self.migrations_dir, f"migration_log_{timestamp}.json")
        
        # Convert datetime objects to strings for JSON serialization
        log_data = self._prepare_log_for_json(context)
        
        with open(log_file, 'w') as f:
            json.dump(log_data, f, indent=2)
    
    def _prepare_log_for_json(self, data):
        """Convert datetime objects to strings for JSON serialization"""
        if isinstance(data, dict):
            return {k: self._prepare_log_for_json(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._prepare_log_for_json(item) for item in data]
        elif isinstance(data, datetime.datetime):
            return data.isoformat()
        else:
            return data
    
    # Example migration methods
    
    async def _migrate_leveling_users_to_v2(self, db):
        """Migrate leveling_users to v2 (adds messages_count field)"""
        self.logger.info("Running leveling_users migration to v2")
        
        # Find all documents without messages_count field
        async for document in db.get_collection("leveling_users").find({"messages_count": {"$exists": False}}):
            # Add new field based on existing field
            messages_count = document.get("messages", 0)
            
            await db.update_one(
                "leveling_users",
                {"_id": document["_id"]},
                {"$set": {"messages_count": messages_count}}
            )
    
    async def _migrate_moderation_logs_to_v2(self, db):
        """Migrate moderation_logs to v2 (adds index on timestamp)"""
        self.logger.info("Running moderation_logs migration to v2")
        
        # Create index on timestamp for faster queries
        await db.ensure_index(
            "moderation_logs",
            {"guild_id": 1, "timestamp": -1},
            name="logs_timestamp_index"
        )
        
        # Add expiry field for auto-cleanup if missing
        await db.update_many(
            "moderation_logs",
            {"expiry": {"$exists": False}},
            {"$set": {"expiry": None}}
        )
