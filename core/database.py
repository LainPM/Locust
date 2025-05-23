import motor.motor_asyncio
import datetime

class DatabaseManager:
    def __init__(self, mongo_uri):
        self.client = motor.motor_asyncio.AsyncIOMotorClient(mongo_uri)
        self.db = self.client["discord_bot_data"] # Or your preferred DB name

        self.warnings = self.db["warnings"]
        self.mutes = self.db["mutes"]
        self.kicks = self.db["kicks"]
        self.bans = self.db["bans"]
        self.modlog_settings = self.db["modlog_settings"] # Keep for future use

    # --- Utility: Case ID (Optional, but good for modlogs) ---
    async def get_next_case_id(self, guild_id: int):
        last_case = 0
        # Consider searching across all relevant collections or having a dedicated counter
        for collection_name in ["warnings", "mutes", "kicks", "bans"]:
            collection = self.db[collection_name]
            # Ensure case_id is treated as an integer for sorting and comparison
            # Corrected to match the provided snippet in the task description
            doc = await collection.find_one({"guild_id": guild_id}, sort=[("case_id", -1)])
            if doc and "case_id" in doc and isinstance(doc["case_id"], int) and doc["case_id"] > last_case:
                last_case = doc["case_id"]
        return last_case + 1

    # --- Warning Methods ---
    async def add_warning(self, guild_id: int, user_id: int, moderator_id: int, reason: str):
        timestamp = datetime.datetime.now(datetime.timezone.utc)
        case_id = await self.get_next_case_id(guild_id)
        warning_doc = {
            "guild_id": guild_id,
            "user_id": user_id,
            "moderator_id": moderator_id,
            "reason": reason,
            "timestamp": timestamp,
            "case_id": case_id
        }
        await self.warnings.insert_one(warning_doc)
        return warning_doc # Return the document, which includes the _id and case_id

    async def get_warnings(self, guild_id: int, user_id: int):
        return await self.warnings.find({"guild_id": guild_id, "user_id": user_id}, sort=[("timestamp", -1)]).to_list(length=None)

    # --- Mute Methods ---
    async def add_mute(self, guild_id: int, user_id: int, moderator_id: int, reason: str, duration_str: str = None, expires_at: datetime.datetime = None):
        timestamp = datetime.datetime.now(datetime.timezone.utc)
        case_id = await self.get_next_case_id(guild_id)
        mute_doc = {
            "guild_id": guild_id,
            "user_id": user_id,
            "moderator_id": moderator_id,
            "reason": reason,
            "duration_str": duration_str,
            "expires_at": expires_at,
            "timestamp": timestamp,
            "active": True, 
            "case_id": case_id
        }
        await self.mutes.insert_one(mute_doc)
        return mute_doc

    async def get_mutes(self, guild_id: int, user_id: int):
        # Also fetch active mutes for checking purposes elsewhere
        return await self.mutes.find({"guild_id": guild_id, "user_id": user_id}, sort=[("timestamp", -1)]).to_list(length=None)

    async def get_active_mute(self, guild_id: int, user_id: int):
        return await self.mutes.find_one({"guild_id": guild_id, "user_id": user_id, "active": True, "$or": [{"expires_at": None}, {"expires_at": {"$gt": datetime.datetime.now(datetime.timezone.utc)}}]})

    async def deactivate_mute_by_id(self, mute_doc_id): # Pass ObjectId directly
        await self.mutes.update_one({"_id": mute_doc_id}, {"$set": {"active": False}})
        
    async def deactivate_user_mutes(self, guild_id: int, user_id: int):
        await self.mutes.update_many(
            {"guild_id": guild_id, "user_id": user_id, "active": True},
            {"$set": {"active": False}}
        )

    # --- Kick Methods ---
    async def add_kick(self, guild_id: int, user_id: int, moderator_id: int, reason: str):
        timestamp = datetime.datetime.now(datetime.timezone.utc)
        case_id = await self.get_next_case_id(guild_id)
        kick_doc = {
            "guild_id": guild_id,
            "user_id": user_id,
            "moderator_id": moderator_id,
            "reason": reason,
            "timestamp": timestamp,
            "case_id": case_id
        }
        await self.kicks.insert_one(kick_doc)
        return kick_doc

    async def get_kicks(self, guild_id: int, user_id: int):
        return await self.kicks.find({"guild_id": guild_id, "user_id": user_id}, sort=[("timestamp", -1)]).to_list(length=None)

    # --- Ban Methods ---
    async def add_ban(self, guild_id: int, user_id: int, moderator_id: int, reason: str):
        timestamp = datetime.datetime.now(datetime.timezone.utc)
        case_id = await self.get_next_case_id(guild_id)
        ban_doc = {
            "guild_id": guild_id,
            "user_id": user_id,
            "moderator_id": moderator_id,
            "reason": reason,
            "timestamp": timestamp,
            "case_id": case_id # Storing as active, assuming bans are active until unbanned
        }
        await self.bans.insert_one(ban_doc)
        return ban_doc

    async def get_bans(self, guild_id: int, user_id: int):
        # For bans, usually all records are relevant as "active" unless specifically marked as "unbanned"
        return await self.bans.find({"guild_id": guild_id, "user_id": user_id}, sort=[("timestamp", -1)]).to_list(length=None)

    # --- Modlog Settings Methods (Example placeholders) ---
    async def set_modlog_channel(self, guild_id: int, channel_id: int):
        await self.modlog_settings.update_one(
            {"guild_id": guild_id},
            {"$set": {"channel_id": channel_id}},
            upsert=True
        )

    async def get_modlog_channel(self, guild_id: int):
        doc = await self.modlog_settings.find_one({"guild_id": guild_id})
        return doc["channel_id"] if doc else None
