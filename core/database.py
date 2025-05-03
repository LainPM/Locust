# core/database.py
import motor.motor_asyncio
from typing import Dict, List, Any, Optional

class DatabaseManager:
    """Centralized database access"""
    
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        
        # Collection cache
        self.collections = {}
    
    def get_collection(self, name: str):
        """Get a MongoDB collection with caching"""
        if name not in self.collections:
            self.collections[name] = self.db[name]
        return self.collections[name]
    
    async def find_one(self, collection: str, query: Dict):
        """Find a single document"""
        coll = self.get_collection(collection)
        return await coll.find_one(query)
    
    async def find(self, collection: str, query: Dict, **kwargs):
        """Find multiple documents"""
        coll = self.get_collection(collection)
        cursor = coll.find(query, **kwargs)
        return await cursor.to_list(length=None)
    
    async def insert_one(self, collection: str, document: Dict):
        """Insert a single document"""
        coll = self.get_collection(collection)
        return await coll.insert_one(document)
    
    async def update_one(self, collection: str, query: Dict, update: Dict, **kwargs):
        """Update a single document"""
        coll = self.get_collection(collection)
        return await coll.update_one(query, update, **kwargs)
    
    async def delete_one(self, collection: str, query: Dict):
        """Delete a single document"""
        coll = self.get_collection(collection)
        return await coll.delete_one(query)
    
    async def count_documents(self, collection: str, query: Dict):
        """Count documents matching a query"""
        coll = self.get_collection(collection)
        return await coll.count_documents(query)
