# utils/command_loader.py
import os
import importlib
import inspect
from discord.ext import commands
from typing import List, Dict, Any

class CommandLoader:
    """Utility for dynamically loading commands"""
    
    @staticmethod
    async def load_all_commands(bot):
        """Load all commands from the commands directory"""
        commands_dir = "commands"
        loaded_count = 0
        error_count = 0
        
        # Get all command categories (subdirectories)
        categories = [d for d in os.listdir(commands_dir) 
                     if os.path.isdir(os.path.join(commands_dir, d)) and not d.startswith('__')]
        
        for category in categories:
            category_path = os.path.join(commands_dir, category)
            
            # Get all command files in this category
            command_files = [f for f in os.listdir(category_path) 
                            if f.endswith('.py') and not f.startswith('__')]
            
            for command_file in command_files:
                # Get module name
                module_name = f"{commands_dir}.{category}.{command_file[:-3]}"
                
                try:
                    # Load the command module
                    await bot.load_extension(module_name)
                    loaded_count += 1
                    print(f"Loaded command: {module_name}")
                except Exception as e:
                    error_count += 1
                    print(f"Error loading command {module_name}: {e}")
        
        print(f"Command loading complete: {loaded_count} loaded, {error_count} errors")
        return loaded_count, error_count
    
    @staticmethod
    async def load_category(bot, category: str):
        """Load all commands in a specific category"""
        commands_dir = "commands"
        category_path = os.path.join(commands_dir, category)
        
        # Check if category exists
        if not os.path.isdir(category_path):
            print(f"Category '{category}' does not exist")
            return 0, 0
        
        loaded_count = 0
        error_count = 0
        
        # Get all command files in this category
        command_files = [f for f in os.listdir(category_path) 
                        if f.endswith('.py') and not f.startswith('__')]
        
        for command_file in command_files:
            # Get module name
            module_name = f"{commands_dir}.{category}.{command_file[:-3]}"
            
            try:
                # Load the command module
                await bot.load_extension(module_name)
                loaded_count += 1
                print(f"Loaded command: {module_name}")
            except Exception as e:
                error_count += 1
                print(f"Error loading command {module_name}: {e}")
        
        print(f"Category '{category}' loading complete: {loaded_count} loaded, {error_count} errors")
        return loaded_count, error_count
