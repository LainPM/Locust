import os
import discord
import asyncio
import datetime
import hashlib
import json
import traceback
import motor.motor_asyncio

from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv

__all__ = [
    "os",
    "discord",
    "asyncio",
    "datetime",
    "hashlib",
    "json",
    "traceback",
    "motor.motor_asyncio",

    "dotenv",
    "discord.ext.commands",
    "discord.app_commands",
]

def initializeDependencies():
    # Load environment variables from .env file
    load_dotenv()

    # Set up intents
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True

    MONGO_URI = os.getenv("MONGO_URI")

    original_sync = app_commands.CommandTree.sync

    return intents, MONGO_URI, original_sync
