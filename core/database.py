# core/database.py
import motor.motor_asyncio
import asyncio
import logging
import datetime
import traceback
from typing import Dict, List, Any, Optional, Union, Callable, Coroutine

class DatabaseManager:
    """Centralized database access with enhanced reliability"""
    
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        self.logger = logging.getLogger('axis_bot.database')
        
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
            "last_error": None
        }
    
    def get_collection(self, name: str):
        """Get a MongoDB collection with caching"""
        if name not in self.collections:
            self.collections[name] = self.db[name]
        return self.collections[name]
    
    async def safe_operation(self, operation_func: Callable, *args, **kwargs):
        """Safely execute a database operation with retry logic"""
        retry_count = 0
        last_error = None
        
        while retry_count < self.max_retries:
            try:
                self.stats["operations"] += 1
                return await operation_func(*args, **kwargs)
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
                        await self.bot.process_events("on_database_error", operation_func.__name__, e, args, kwargs)
                
                # Exponential backoff
                backoff_time = self.retry_delay * (2 ** (retry_count - 1))
                await asyncio.sleep(backoff_time)
        
        # If we get here, all retries failed
        raise last_error
    
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
        total_pages = (total + per_page - 1) // per_page
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
        # Add created_at timestamp if not present
        if "created_at" not in document:
            document["created_at"] = datetime.datetime.now()
            
        coll = self.get_collection(collection)
        return await self.safe_operation(coll.insert_one, document)
    
    async def insert_many(self, collection: str, documents: List[Dict]):
        """Insert multiple documents with retry logic"""
        # Add created_at timestamp if not present
        for doc in documents:
            if "created_at" not in doc:
                doc["created_at"] = datetime.datetime.now()
                
        coll = self.get_collection(collection)
        return await self.safe_operation(coll.insert_many, documents)
    
    async def update_one(self, collection: str, query: Dict, update: Dict, **kwargs):
        """Update a single document with retry logic"""
        # Add updated_at timestamp to $set if not present
        if "$set" not in update:
            update["$set"] = {}
        
        if "updated_at" not in update["$set"]:
            update["$set"]["updated_at"] = datetime.datetime.now()
            
        coll = self.get_collection(collection)
        return await self.safe_operation(coll.update_one, query, update, **kwargs)
    
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
        from bson.objectid import ObjectId
        try:
            object_id = ObjectId(id_str)
            return await self.find_one(collection, {"_id": object_id}, **kwargs)
        except Exception as e:
            self.logger.error(f"Invalid ObjectID format: {id_str}", exc_info=True)
            return None
    
    async def update_by_id(self, collection: str, id_str: str, update: Dict, **kwargs):
        """Update a document by its ID string"""
        from bson.objectid import ObjectId
        try:
            object_id = ObjectId(id_str)
            return await self.update_one(collection, {"_id": object_id}, update, **kwargs)
        except Exception as e:
            self.logger.error(f"Invalid ObjectID format: {id_str}", exc_info=True)
            return None
    
    async def delete_by_id(self, collection: str, id_str: str):
        """Delete a document by its ID string"""
        from bson.objectid import ObjectId
        try:
            object_id = ObjectId(id_str)
            return await self.delete_one(collection, {"_id": object_id})
        except Exception as e:
            self.logger.error(f"Invalid ObjectID format: {id_str}", exc_info=True)
            return None
    
    async def get_database_stats(self):
        """Get statistics about database operations"""
        stats = {
            **self.stats,
            "collections": list(self.collections.keys()),
            "collection_count": len(self.collections)
        }
        
        return stats
    
    async def backup_collection(self, collection_name: str, backup_suffix: str = None):
        """Create a backup of a collection"""
        if backup_suffix is None:
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_suffix = f"backup_{timestamp}"
            
        backup_collection_name = f"{collection_name}_{backup_suffix}"
        
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
            return True
        except Exception as e:
            self.logger.error(f"Error creating backup of {collection_name}: {e}", exc_info=True)
            return False
