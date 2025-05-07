# systems/tickets/storage.py
import discord
import datetime
from typing import Dict, List, Any, Optional

class TicketStorage:
    """Storage handler for the ticket system"""
    
    def __init__(self, system):
        self.system = system
        self.bot = system.bot
        self.db = self.bot.db
    
    async def get_settings(self, guild_id: int) -> Dict[str, Any]:
        """Get ticket settings for a guild"""
        settings = await self.bot.db["ticket_config"].find_one({"guild_id": guild_id})
        
        if not settings:
            # Create default settings
            settings = {
                "guild_id": guild_id,
                "enabled": False,
                "panel_channel_id": None,
                "transcript_channel_id": None,
                "ticket_category_id": None,
                "ticket_types": ["Support", "Bug Report", "Other"],
                "moderator_roles": [],
                "panel_title": "Support Tickets",
                "panel_description": "Click a button below to create a ticket",
                "created_at": datetime.datetime.now().isoformat(),
                "updated_at": datetime.datetime.now().isoformat()
            }
            
            await self.bot.db["ticket_config"].insert_one(settings)
        
        return settings
    
    async def update_settings(self, guild_id: int, updates: Dict[str, Any]) -> bool:
        """Update ticket settings for a guild"""
        updates["updated_at"] = datetime.datetime.now().isoformat()
        
        result = await self.bot.db["ticket_config"].update_one(
            {"guild_id": guild_id},
            {"$set": updates}
        )
        
        # Update cache if exists
        if hasattr(self.system, "settings_cache") and guild_id in self.system.settings_cache:
            self.system.settings_cache[guild_id].update(updates)
        
        return result.modified_count > 0
    
    async def create_ticket(self, guild_id: int, user_id: int, channel_id: int, 
                          ticket_type: str) -> str:
        """Create a new ticket entry"""
        ticket_data = {
            "guild_id": guild_id,
            "user_id": user_id,
            "channel_id": channel_id,
            "ticket_type": ticket_type,
            "status": "open",
            "created_at": datetime.datetime.now().isoformat(),
            "updated_at": datetime.datetime.now().isoformat(),
            "closed_at": None,
            "closed_by": None,
            "messages": []
        }
        
        result = await self.bot.db["tickets_active"].insert_one(ticket_data)
        return str(result.inserted_id)
    
    async def get_ticket(self, channel_id: int) -> Optional[Dict[str, Any]]:
        """Get a ticket by channel ID"""
        return await self.bot.db["tickets_active"].find_one({"channel_id": channel_id})
    
    async def close_ticket(self, channel_id: int, closed_by: int) -> bool:
        """Close a ticket"""
        ticket = await self.get_ticket(channel_id)
        
        if not ticket:
            return False
        
        # Update ticket status
        await self.bot.db["tickets_active"].update_one(
            {"channel_id": channel_id},
            {"$set": {
                "status": "closed",
                "closed_at": datetime.datetime.now().isoformat(),
                "closed_by": closed_by,
                "updated_at": datetime.datetime.now().isoformat()
            }}
        )
        
        # Move to archived tickets
        ticket["status"] = "closed"
        ticket["closed_at"] = datetime.datetime.now().isoformat()
        ticket["closed_by"] = closed_by
        ticket["updated_at"] = datetime.datetime.now().isoformat()
        
        await self.bot.db["tickets_archived"].insert_one(ticket)
        await self.bot.db["tickets_active"].delete_one({"channel_id": channel_id})
        
        return True
    
    async def add_message(self, channel_id: int, message_data: Dict[str, Any]) -> bool:
        """Add a message to a ticket"""
        result = await self.bot.db["tickets_active"].update_one(
            {"channel_id": channel_id},
            {
                "$push": {"messages": message_data},
                "$set": {"updated_at": datetime.datetime.now().isoformat()}
            }
        )
        
        return result.modified_count > 0
    
    async def get_user_tickets(self, guild_id: int, user_id: int) -> List[Dict[str, Any]]:
        """Get all tickets for a user in a guild"""
        active = await self.bot.db["tickets_active"].find({
            "guild_id": guild_id,
            "user_id": user_id
        }).to_list(length=100)
        
        archived = await self.bot.db["tickets_archived"].find({
            "guild_id": guild_id,
            "user_id": user_id
        }).to_list(length=100)
        
        return active + archived
