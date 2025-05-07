# systems/leveling/rewards.py
import discord
from typing import Dict, Any

class RewardManager:
    """Handles role rewards for leveling up"""
    
    def __init__(self, system):
        self.system = system
        self.bot = system.bot
    
    async def check_role_rewards(self, guild: discord.Guild, member: discord.Member, level: int):
        """Check and apply role rewards for a user"""
        # Get guild settings
        guild_id = guild.id
        settings = await self.system.get_settings(guild_id)
        
        # Check if there are any role rewards
        role_rewards = settings.get("role_rewards", {})
        if not role_rewards:
            return
        
        # Convert level to string for dict lookup
        level_str = str(level)
        
        # Check if this level has a reward
        if level_str in role_rewards:
            role_id_str = role_rewards[level_str]
            try:
                role_id = int(role_id_str)
                role = guild.get_role(role_id)
                
                if role and role not in member.roles:
                    # Check if bot has permission to assign roles
                    if guild.me.guild_permissions.manage_roles:
                        # Check if role is assignable by bot
                        if role < guild.me.top_role:
                            await member.add_roles(role, reason=f"Reached level {level}")
                            print(f"Assigned role {role.name} to {member.name} for reaching level {level}")
                        else:
                            print(f"Cannot assign role {role.name} - higher than bot's highest role")
                    else:
                        print(f"Cannot assign role {role.name} - missing Manage Roles permission")
            except Exception as e:
                print(f"Error assigning role reward: {e}")
