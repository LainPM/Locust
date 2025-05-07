# core/database.py
import motor.motor_asyncio
import asyncio
import logging
import datetime
import traceback
import json
import os
from bson.objectid import ObjectId
from typing import Dict, List, Any, Optional, Union, Callable, Coroutine, TypeVar, Generic

class DatabaseManager:
    """Enhanced database manager with proper collection namespacing and advanced features"""
    
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger('axis_bot.database')
        
        # Initialize MongoDB connection
        mongo_uri = os.getenv("MONGO_URI")
        if not mongo_uri:
            raise ValueError("MONGO_URI environment variable not set")
            
        self.client = motor.motor_asyncio.AsyncIOMotorClient(mongo_uri)
        self.db = self.client.get_database("axis_bot")
        
        # Collection cache
        self.collections = {}
        
        # Connection status
        self.is_connected = False
        
        # Retry settings
        self.max_retries = 3
        self.retry_delay = 1  # seconds
        
        # Track operations for stats
        self.stats = {
            "operations": 0,
            "errors": 0,
            "retries": 0,
            "last_error": None,
            "last_operation_time": None
        }
        
        # Schema versions for collections
        self.schema_versions = {
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
        
        # Initialize with validation rules
        self.validation_rules = {}
        self._setup_validation_rules()
    
    def _setup_validation_rules(self):
        """Set up validation rules for collections"""
        # Leveling system validation
        self.validation_rules["leveling_users"] = {
            "required_fields": ["user_id", "guild_id", "xp", "level"],
            "field_types": {
                "user_id": int,
                "guild_id": int,
                "xp": int,
                "level": int,
                "messages": int
            },
            "min_values": {
                "xp": 0,
                "level": 0,
                "messages": 0
            }
        }
        
        # Moderation system validation
        self.validation_rules["moderation_blacklist"] = {
            "required_fields": ["guild_id", "item", "match_type"],
            "field_types": {
                "guild_id": int,
                "item": str,
                "match_type": str
            }
        }
        
        # Add more validation rules for other collections...
    
    async def initialize(self):
        """Initialize database connection and verify collections"""
        try:
            # Test connection
            await self.client.admin.command('ping')
            self.is_connected = True
            self.logger.info("Database connection established")
            
            # Create metadata collection if it doesn't exist
            if "system_metadata" not in await self.db.list_collection_names():
                await self.db.create_collection("system_metadata")
                self.logger.info("Created system metadata collection")
            
            # Initialize system metadata if needed
            for collection_name, version in self.schema_versions.items():
                metadata = await self.find_one("system_metadata", {"collection": collection_name})
                if not metadata:
                    await self.insert_one("system_metadata", {
                        "collection": collection_name,
                        "schema_version": version,
                        "created_at": datetime.datetime.now(),
                        "updated_at": datetime.datetime.now()
                    })
                    self.logger.info(f"Initialized schema version for {collection_name}")
            
            return True
        
        except Exception as e:
            self.is_connected = False
            self.logger.error(f"Failed to initialize database: {str(e)}", exc_info=True)
            return False
    
    def get_collection(self, name: str):
        """Get a MongoDB collection with caching"""
        if name not in self.collections:
            self.collections[name] = self.db[name]
        return self.collections[name]
    
    def get_system_collection(self, system_name: str, collection_name: str):
        """Get a MongoDB collection with system prefix for proper namespacing"""
        prefixed_name = f"{system_name.lower()}_{collection_name}"
        return self.get_collection(prefixed_name)
    
    async def safe_operation(self, operation_func: Callable, *args, **kwargs):
        """Safely execute a database operation with retry logic"""
        retry_count = 0
        last_error = None
        
        while retry_count < self.max_retries:
            try:
                self.stats["operations"] += 1
                self.stats["last_operation_time"] = datetime.datetime.now()
                result = await operation_func(*args, **kwargs)
                return result
            
            except Exception as e:
                retry_count += 1
                self.stats["retries"] += 1
                last_error = e
                
                error_message = f"Database operation failed (attempt {retry_count}/{self.max_retries}): {str(e)}"
                if retry_count < self.max_retries:
                    self.logger.warning(error_message)
                else:
                    self.stats["errors"] += 1
                    self.stats["last_error"] = str(e)
                    self.logger.error(error_message, exc_info=True)
                    
                    # Emit event for other systems to handle
                    if hasattr(self.bot, "process_events"):
                        try:
                            await self.bot.process_events("on_database_error", 
                                                          operation_func.__name__, 
                                                          e, args, kwargs)
                        except Exception as event_error:
                            self.logger.error(f"Error emitting database error event: {str(event_error)}")
                
                # Exponential backoff
                backoff_time = self.retry_delay * (2 ** (retry_count - 1))
                await asyncio.sleep(backoff_time)
        
        # If we get here, all retries failed
        raise last_error
    
    def validate_document(self, collection_name: str, document: Dict[str, Any]):
        """Validate document against collection rules"""
        # Skip validation if no rules for this collection
        if collection_name not in self.validation_rules:
            return True
        
        rules = self.validation_rules[collection_name]
        
        # Check required fields
        if "required_fields" in rules:
            for field in rules["required_fields"]:
                if field not in document:
                    raise ValueError(f"Missing required field '{field}' in {collection_name} document")
        
        # Check field types
        if "field_types" in rules:
            for field, expected_type in rules["field_types"].items():
                if field in document and document[field] is not None:
                    if not isinstance(document[field], expected_type):
                        raise ValueError(f"Field '{field}' in {collection_name} must be {expected_type.__name__}")
        
        # Check minimum values
        if "min_values" in rules:
            for field, min_value in rules["min_values"].items():
                if field in document and document[field] is not None:
                    if document[field] < min_value:
                        raise ValueError(f"Field '{field}' in {collection_name} must be >= {min_value}")
        
        return True
    
    async def find_one(self, collection: str, query: Dict, **kwargs):
        """Find a single document with retry logic"""
        coll = self.get_collection(collection)
        return await self.safe_operation(coll.find_one, query, **kwargs)
    
    async def find(self, collection: str, query: Dict, **kwargs):
        """Find multiple documents with retry logic"""
        coll = self.get_collection(collection)
        
        # Create a function to get all results in one go
        async def get_all_results():
            cursor = coll.find(query, **kwargs)
            return await cursor.to_list(length=None)
        
        return await self.safe_operation(get_all_results)
    
    async def find_with_pagination(self, collection: str, query: Dict, page: int = 1, 
                                   per_page: int = 10, sort_field: str = None, 
                                   sort_direction: int = -1, **kwargs):
        """Find documents with pagination support"""
        coll = self.get_collection(collection)
        
        # Calculate skip value
        skip = (page - 1) * per_page
        
        # Get total count for pagination info
        total = await self.count_documents(collection, query)
        
        # Create cursor with pagination
        cursor = coll.find(query, **kwargs)
        
        # Apply sorting if specified
        if sort_field:
            cursor = cursor.sort(sort_field, sort_direction)
        
        # Apply pagination
        cursor = cursor.skip(skip).limit(per_page)
        
        # Get paginated results
        results = await self.safe_operation(cursor.to_list, length=per_page)
        
        # Calculate pagination info
        total_pages = (total + per_page - 1) // per_page if total > 0 else 1
        has_next = page < total_pages
        has_prev = page > 1
        
        return {
            "results": results,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "total_pages": total_pages,
                "has_next": has_next,
                "has_prev": has_prev
            }
        }
    
    async def insert_one(self, collection: str, document: Dict):
        """Insert a single document with retry logic"""
        # Add timestamps
        if "created_at" not in document:
            document["created_at"] = datetime.datetime.now()
        if "updated_at" not in document:
            document["updated_at"] = document["created_at"]
        
        # Validate document
        self.validate_document(collection, document)
            
        coll = self.get_collection(collection)
        return await self.safe_operation(coll.insert_one, document)
    
    async def insert_many(self, collection: str, documents: List[Dict]):
        """Insert multiple documents with retry logic"""
        # Add timestamps and validate documents
        now = datetime.datetime.now()
        for doc in documents:
            if "created_at" not in doc:
                doc["created_at"] = now
            if "updated_at" not in doc:
                doc["updated_at"] = now
            
            # Validate document
            self.validate_document(collection, doc)
                
        coll = self.get_collection(collection)
        return await self.safe_operation(coll.insert_many, documents)
    
    async def update_one(self, collection: str, query: Dict, update: Dict, **kwargs):
        """Update a single document with retry logic"""
        # Add updated_at timestamp to $set if not present
        if "$set" not in update:
            update["$set"] = {}
        
        if "updated_at" not in update["$set"]:
            update["$set"]["updated_at"] = datetime.datetime.now()
        
        # If returnDocument is specified and set to 'after', we need to validate
        # the updated document after the operation
        return_after = kwargs.get("return_document", "before") == "after"
        
        coll = self.get_collection(collection)
        result = await self.safe_operation(coll.update_one, query, update, **kwargs)
        
        # If validation is needed for the updated document, fetch it and validate
        if not return_after and collection in self.validation_rules:
            updated_doc = await self.find_one(collection, query)
            if updated_doc:
                try:
                    self.validate_document(collection, updated_doc)
                except ValueError as ve:
                    self.logger.warning(f"Updated document validation failed: {str(ve)}")
        
        return result
    
    async def update_many(self, collection: str, query: Dict, update: Dict, **kwargs):
        """Update multiple documents with retry logic"""
        # Add updated_at timestamp to $set if not present
        if "$set" not in update:
            update["$set"] = {}
        
        if "updated_at" not in update["$set"]:
            update["$set"]["updated_at"] = datetime.datetime.now()
            
        coll = self.get_collection(collection)
        return await self.safe_operation(coll.update_many, query, update, **kwargs)
    
    async def delete_one(self, collection: str, query: Dict):
        """Delete a single document with retry logic"""
        coll = self.get_collection(collection)
        return await self.safe_operation(coll.delete_one, query)
    
    async def delete_many(self, collection: str, query: Dict):
        """Delete multiple documents with retry logic"""
        coll = self.get_collection(collection)
        return await self.safe_operation(coll.delete_many, query)
    
    async def count_documents(self, collection: str, query: Dict):
        """Count documents matching a query"""
        coll = self.get_collection(collection)
        return await self.safe_operation(coll.count_documents, query)
    
    async def ensure_index(self, collection: str, keys: Dict, **kwargs):
        """Create an index if it doesn't exist"""
        coll = self.get_collection(collection)
        return await self.safe_operation(coll.create_index, keys, **kwargs)
    
    async def ensure_system_indexes(self, system_name: str, indexes: Dict[str, List]):
        """Create all required indexes for a system's collections
        
        Args:
            system_name: The name of the system
            indexes: Dictionary mapping collection names to index definitions
                     Example: {"users": [{"keys": {"guild_id": 1, "user_id": 1}, "unique": True}]}
        """
        for collection_name, index_list in indexes.items():
            prefixed_name = f"{system_name.lower()}_{collection_name}"
            coll = self.get_collection(prefixed_name)
            
            for index_def in index_list:
                keys = index_def.pop("keys")
                try:
                    await self.safe_operation(coll.create_index, keys, **index_def)
                    self.logger.info(f"Created index on {prefixed_name}: {keys}")
                except Exception as e:
                    self.logger.error(f"Failed to create index on {prefixed_name}: {str(e)}")
    
    async def aggregate(self, collection: str, pipeline: List[Dict]):
        """Run an aggregation pipeline with retry logic"""
        coll = self.get_collection(collection)
        
        # Create a function to get all aggregation results in one go
        async def get_aggregation_results():
            cursor = coll.aggregate(pipeline)
            return await cursor.to_list(length=None)
        
        return await self.safe_operation(get_aggregation_results)
    
    async def find_by_id(self, collection: str, id_str: str, **kwargs):
        """Find a document by its ID string"""
        try:
            object_id = ObjectId(id_str)
            return await self.find_one(collection, {"_id": object_id}, **kwargs)
        except Exception as e:
            self.logger.error(f"Invalid ObjectID format: {id_str}", exc_info=True)
            return None
    
    async def update_by_id(self, collection: str, id_str: str, update: Dict, **kwargs):
        """Update a document by its ID string"""
        try:
            object_id = ObjectId(id_str)
            return await self.update_one(collection, {"_id": object_id}, update, **kwargs)
        except Exception as e:
            self.logger.error(f"Invalid ObjectID format: {id_str}", exc_info=True)
            return None
    
    async def delete_by_id(self, collection: str, id_str: str):
        """Delete a document by its ID string"""
        try:
            object_id = ObjectId(id_str)
            return await self.delete_one(collection, {"_id": object_id})
        except Exception as e:
            self.logger.error(f"Invalid ObjectID format: {id_str}", exc_info=True)
            return None
    
    async def check_schema_version(self, collection: str):
        """Check and update schema version for a collection"""
        if collection not in self.schema_versions:
            return  # Skip collections not in our version tracking
            
        expected_version = self.schema_versions[collection]
        metadata = await self.find_one("system_metadata", {"collection": collection})
        
        if not metadata:
            # Create metadata entry
            await self.insert_one("system_metadata", {
                "collection": collection,
                "schema_version": expected_version,
                "created_at": datetime.datetime.now(),
                "updated_at": datetime.datetime.now()
            })
            self.logger.info(f"Created schema version entry for {collection}: v{expected_version}")
            return
        
        current_version = metadata.get("schema_version", 1)
        
        if current_version < expected_version:
            await self.migrate_schema(collection, current_version, expected_version)
    
    async def migrate_schema(self, collection: str, current_version: int, target_version: int):
        """Migrate a collection schema from one version to another"""
        self.logger.info(f"Starting migration of {collection} from v{current_version} to v{target_version}")
        
        # Perform backup first
        backup_name = f"{collection}_backup_v{current_version}"
        await self.backup_collection(collection, backup_name)
        
        # Execute migrations one version at a time
        for version in range(current_version + 1, target_version + 1):
            migration_method = f"_migrate_{collection}_to_v{version}"
            
            if hasattr(self, migration_method) and callable(getattr(self, migration_method)):
                try:
                    await getattr(self, migration_method)()
                    
                    # Update schema version
                    await self.update_one(
                        "system_metadata",
                        {"collection": collection},
                        {"$set": {
                            "schema_version": version,
                            "updated_at": datetime.datetime.now(),
                            "last_migration": datetime.datetime.now()
                        }}
                    )
                    
                    self.logger.info(f"Migrated {collection} to v{version}")
                    
                except Exception as e:
                    self.logger.error(f"Error migrating {collection} to v{version}: {str(e)}", exc_info=True)
                    raise
            else:
                self.logger.warning(f"No migration method found for {collection} to v{version}")
    
    # Example migration method - add more as needed
    async def _migrate_leveling_users_to_v2(self):
        """Migrate leveling_users to v2 schema (adds messages_count field)"""
        coll = self.get_collection("leveling_users")
        
        # Find all documents without the messages_count field
        async for document in coll.find({"messages_count": {"$exists": False}}):
            # Add missing field
            await coll.update_one(
                {"_id": document["_id"]},
                {"$set": {"messages_count": document.get("message_count", 0) or 0}}
            )
    
    async def backup_collection(self, collection_name: str, backup_suffix: str = None):
        """Create a backup of a collection"""
        if backup_suffix is None:
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_suffix = f"backup_{timestamp}"
            
        backup_collection_name = f"{collection_name}_{backup_suffix}"
        
        self.logger.info(f"Creating backup of {collection_name} to {backup_collection_name}")
        
        # Create a fresh backup collection
        if backup_collection_name in await self.db.list_collection_names():
            await self.db.drop_collection(backup_collection_name)
        
        # Get all documents from the source collection
        documents = await self.find(collection_name, {})
        
        # Skip if no documents
        if not documents:
            self.logger.warning(f"No documents found in {collection_name}, skipping backup")
            return False
        
        # Create backup collection and insert documents
        try:
            # We need to remove _id to avoid duplicates
            for doc in documents:
                if '_id' in doc:
                    doc['original_id'] = doc['_id']
                    del doc['_id']
            
            result = await self.insert_many(backup_collection_name, documents)
            self.logger.info(f"Backed up {len(documents)} documents from {collection_name} to {backup_collection_name}")
            
            # Add backup metadata
            await self.insert_one("system_metadata", {
                "collection": backup_collection_name,
                "backup_of": collection_name,
                "document_count": len(documents),
                "created_at": datetime.datetime.now()
            })
            
            return True
        except Exception as e:
            self.logger.error(f"Error creating backup of {collection_name}: {str(e)}", exc_info=True)
            return False
    
    async def restore_from_backup(self, backup_collection_name: str, target_collection_name: str = None, 
                                  drop_existing: bool = False):
        """Restore a collection from backup"""
        if target_collection_name is None:
            # Extract original collection name from backup name
            if '_backup_' in backup_collection_name:
                target_collection_name = backup_collection_name.split('_backup_')[0]
            else:
                raise ValueError("Cannot determine target collection name from backup name")
        
        self.logger.info(f"Restoring from {backup_collection_name} to {target_collection_name}")
        
        # Check if backup exists
        if backup_collection_name not in await self.db.list_collection_names():
            self.logger.error(f"Backup collection {backup_collection_name} not found")
            return False
        
        # Get backup documents
        backup_docs = await self.find(backup_collection_name, {})
        
        if not backup_docs:
            self.logger.warning(f"No documents found in backup {backup_collection_name}")
            return False
        
        # Process the documents to restore original IDs
        for doc in backup_docs:
            if 'original_id' in doc:
                doc['_id'] = doc['original_id']
                del doc['original_id']
        
        # If requested, drop the existing collection
        if drop_existing and target_collection_name in await self.db.list_collection_names():
            # Create one more backup just in case
            temp_backup = f"{target_collection_name}_pre_restore_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
            await self.backup_collection(target_collection_name, temp_backup)
            
            # Now drop the collection
            await self.db.drop_collection(target_collection_name)
            self.logger.info(f"Dropped existing collection {target_collection_name}")
        
        # Insert documents into target collection
        try:
            # Use bulk operations for efficiency
            bulk_operations = []
            
            for doc in backup_docs:
                # If the document already exists, update it, otherwise insert it
                bulk_operations.append(
                    pymongo.UpdateOne(
                        {"_id": doc["_id"]},
                        {"$set": doc},
                        upsert=True
                    )
                )
            
            # Execute bulk operations
            result = await self.get_collection(target_collection_name).bulk_write(bulk_operations)
            
            self.logger.info(f"Restored {result.upserted_count + result.modified_count} documents to {target_collection_name}")
            return True
        except Exception as e:
            self.logger.error(f"Error restoring from backup: {str(e)}", exc_info=True)
            return False
    
    async def get_database_stats(self):
        """Get statistics about database operations"""
        # Get collection statistics
        collection_stats = {}
        
        for collection_name in await self.db.list_collection_names():
            if collection_name != "system_metadata" and not collection_name.startswith("backup_"):
                doc_count = await self.count_documents(collection_name, {})
                collection_stats[collection_name] = doc_count
        
        # Get general database statistics
        db_stats = await self.db.command("dbStats")
        
        stats = {
            **self.stats,
            "collections": list(collection_stats.keys()),
            "collection_counts": collection_stats,
            "database_size_mb": db_stats.get("dataSize", 0) / (1024 * 1024),
            "storage_size_mb": db_stats.get("storageSize", 0) / (1024 * 1024),
            "total_collections": len(collection_stats)
        }
        
        return stats
    
    async def export_collection_to_json(self, collection_name: str, file_path: str = None):
        """Export a collection to a JSON file"""
        if file_path is None:
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            file_path = f"data/exports/{collection_name}_{timestamp}.json"
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        documents = await self.find(collection_name, {})
        
        # Convert ObjectId to string for JSON serialization
        for doc in documents:
            if '_id' in doc:
                doc['_id'] = str(doc['_id'])
            
            # Convert datetime objects to ISO format
            for key, value in doc.items():
                if isinstance(value, datetime.datetime):
                    doc[key] = value.isoformat()
        
        # Write to file
        with open(file_path, 'w') as f:
            json.dump(documents, f, indent=2)
        
        self.logger.info(f"Exported {len(documents)} documents from {collection_name} to {file_path}")
        return file_path
    
    async def import_collection_from_json(self, collection_name: str, file_path: str, drop_existing: bool = False):
        """Import a collection from a JSON file"""
        if not os.path.exists(file_path):
            self.logger.error(f"Import file {file_path} not found")
            return False
        
        # Read the file
        with open(file_path, 'r') as f:
            documents = json.load(f)
        
        if not documents:
            self.logger.warning(f"No documents found in import file {file_path}")
            return False
        
        # If requested, drop the existing collection
        if drop_existing and collection_name in await self.db.list_collection_names():
            # Create backup first
            await self.backup_collection(collection_name)
            
            # Drop the collection
            await self.db.drop_collection(collection_name)
            self.logger.info(f"Dropped existing collection {collection_name}")
        
        # Process documents for import
        for doc in documents:
            # Convert string IDs to ObjectId
            if '_id' in doc and isinstance(doc['_id'], str):
                try:
                    doc['_id'] = ObjectId(doc['_id'])
                except:
                    # If conversion fails, remove the ID to let MongoDB generate a new one
                    del doc['_id']
            
            # Convert ISO date strings back to datetime objects
            for key, value in doc.items():
                if isinstance(value, str) and 'T' in value and value.endswith('Z'):
                    try:
                        doc[key] = datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
                    except:
                        pass
        
        # Import the documents
        try:
            result = await self.insert_many(collection_name, documents)
            self.logger.info(f"Imported {len(documents)} documents to {collection_name}")
            return True
        except Exception as e:
            self.logger.error(f"Error importing documents: {str(e)}", exc_info=True)
            return False
    
    async def cleanup(self):
        """Clean up database resources"""
        try:
            # Close MongoDB connection
            self.client.close()
            self.logger.info("Database connection closed")
        except Exception as e:
            self.logger.error(f"Error closing database connection: {str(e)}", exc_info=True)
