# cogs/marketplace.py
import discord
from discord.ext import commands
from discord import app_commands
import datetime
import io
import aiohttp
import asyncio
from typing import Optional, Literal

class MarketPostModal(discord.ui.Modal):
    def __init__(self, post_type: str, cog):
        super().__init__(title=f"Create a {post_type} Post")
        self.post_type = post_type
        self.cog = cog
        
        self.title_input = discord.ui.TextInput(
            label="Title",
            placeholder="Enter a title for your post",
            required=True,
            max_length=100
        )
        self.add_item(self.title_input)
        
        self.description_input = discord.ui.TextInput(
            label="Description",
            placeholder="Describe your post in detail",
            required=True,
            style=discord.TextStyle.paragraph,
            max_length=2000
        )
        self.add_item(self.description_input)
        
        self.price_input = discord.ui.TextInput(
            label="Price/Rate",
            placeholder="e.g. 500 Robux, $10 USD, or Negotiable",
            required=True,
            max_length=100
        )
        self.add_item(self.price_input)
        
        self.image_url_input = discord.ui.TextInput(
            label="Image URL (Optional)",
            placeholder="Link to an image of your work/product",
            required=False,
            max_length=500
        )
        self.add_item(self.image_url_input)
        
        self.contact_input = discord.ui.TextInput(
            label="Contact Information",
            placeholder="How should people contact you? (Discord username, etc.)",
            required=True,
            max_length=200
        )
        self.add_item(self.contact_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        # Get server settings
        guild_id = interaction.guild.id
        server_settings = await self.cog.get_server_settings(guild_id)
        
        if not server_settings:
            return await interaction.followup.send("Marketplace hasn't been set up in this server. Please ask an admin to run `/setup marketposts`.", ephemeral=True)
        
        approvals_category_id = server_settings.get("approvals_category_id")
        approvals_category = interaction.guild.get_channel(approvals_category_id)
        
        if not approvals_category:
            return await interaction.followup.send("The approvals category could not be found. Please ask an admin to run `/setup marketposts`.", ephemeral=True)
        
        # Check if image URL is valid (if provided)
        image_file = None
        image_url = self.image_url_input.value.strip()
        
        if image_url:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(image_url) as resp:
                        if resp.status != 200:
                            await interaction.followup.send("The image URL you provided is invalid. Your post has still been submitted without an image.", ephemeral=True)
                            image_url = None
                        else:
                            # Check if it's actually an image
                            content_type = resp.headers.get('Content-Type', '')
                            if not content_type.startswith('image/'):
                                await interaction.followup.send("The URL provided doesn't point to an image. Your post has been submitted without an image.", ephemeral=True)
                                image_url = None
                            else:
                                image_data = await resp.read()
                                image_file = discord.File(io.BytesIO(image_data), filename="image.png")
            except Exception as e:
                await interaction.followup.send(f"There was an error processing your image URL. Your post has been submitted without an image.", ephemeral=True)
                image_url = None
        
        # Create a unique channel name
        timestamp = int(datetime.datetime.now().timestamp())
        safe_title = self.title_input.value.lower().replace(" ", "-")[:20]
        channel_name = f"{self.post_type.lower()}-{safe_title}-{timestamp}"
        
        # Create permissions for the approval channel
        approval_roles_ids = server_settings.get("approval_view_roles", [])
        approval_mod_roles_ids = server_settings.get("approval_mod_roles", [])
        
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, embed_links=True, attach_files=True, manage_channels=True)
        }
        
        # Add permissions for approval roles
        for role_id in approval_roles_ids:
            role = interaction.guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=False)
        
        # Add permissions for approval mod roles
        for role_id in approval_mod_roles_ids:
            role = interaction.guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        
        # Create the approval channel
        try:
            approval_channel = await interaction.guild.create_text_channel(
                name=channel_name,
                category=approvals_category,
                overwrites=overwrites,
                reason=f"Market post by {interaction.user}"
            )
        except discord.Forbidden:
            return await interaction.followup.send("I don't have permission to create channels. Please contact a server administrator.", ephemeral=True)
        except Exception as e:
            return await interaction.followup.send(f"An error occurred: {str(e)}", ephemeral=True)
        
        # Create the post embed
        post_embed = discord.Embed(
            title=self.title_input.value,
            description=self.description_input.value,
            color=self.get_color_for_post_type(self.post_type),
            timestamp=datetime.datetime.now()
        )
        post_embed.set_author(name=f"{self.post_type} by {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
        post_embed.add_field(name="Price/Rate", value=self.price_input.value, inline=True)
        post_embed.add_field(name="Contact", value=self.contact_input.value, inline=True)
        post_embed.add_field(name="Post Type", value=self.post_type, inline=True)
        post_embed.set_footer(text=f"Posted by: {interaction.user.name} • ID: {interaction.user.id}")
        
        if image_url:
            post_embed.set_image(url=image_url)
        
        # Save post data to database
        post_data = {
            "guild_id": guild_id,
            "channel_id": approval_channel.id,
            "user_id": interaction.user.id,
            "post_type": self.post_type,
            "title": self.title_input.value,
            "description": self.description_input.value,
            "price": self.price_input.value,
            "contact": self.contact_input.value,
            "image_url": image_url,
            "status": "pending",
            "created_at": datetime.datetime.now()
        }
        
        await self.cog.marketplace_posts.insert_one(post_data)
        
        # Create approval buttons
        view = PostApprovalView(self.cog, post_data)
        
        # Send to approval channel
        if image_file:
            await approval_channel.send(f"**New {self.post_type} Post Submission**\nSubmitted by: {interaction.user.mention}", embed=post_embed, file=image_file, view=view)
        else:
            await approval_channel.send(f"**New {self.post_type} Post Submission**\nSubmitted by: {interaction.user.mention}", embed=post_embed, view=view)
        
        # Notify the user
        await interaction.followup.send(f"Your {self.post_type} post has been submitted and is awaiting approval. You will be notified when it's approved or declined.", ephemeral=True)
    
    def get_color_for_post_type(self, post_type):
        if post_type == "Hiring":
            return discord.Color.from_rgb(66, 135, 245)  # Blue
        elif post_type == "For-Hire":
            return discord.Color.from_rgb(240, 173, 78)  # Orange
        elif post_type == "Selling":
            return discord.Color.from_rgb(92, 184, 92)   # Green
        else:
            return discord.Color.from_rgb(128, 128, 128) # Gray

class PostApprovalView(discord.ui.View):
    def __init__(self, cog, post_data):
        super().__init__(timeout=None)  # No timeout for approval buttons
        self.cog = cog
        self.post_data = post_data
    
    @discord.ui.button(label="Approve", style=discord.ButtonStyle.green, custom_id="approve_post")
    async def approve_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        # Get server settings
        guild_id = interaction.guild.id
        server_settings = await self.cog.get_server_settings(guild_id)
        
        if not server_settings:
            return await interaction.followup.send("Marketplace hasn't been set up in this server. Please run `/setup marketposts`.", ephemeral=True)
        
        # Check if user has appropriate role
        approval_mod_roles_ids = server_settings.get("approval_mod_roles", [])
        has_permission = False
        
        for role_id in approval_mod_roles_ids:
            role = interaction.guild.get_role(role_id)
            if role and role in interaction.user.roles:
                has_permission = True
                break
        
        if not has_permission:
            return await interaction.followup.send("You don't have permission to approve marketplace posts.", ephemeral=True)
        
        # Get the marketplace channel
        marketplace_channel_id = None
        if self.post_data["post_type"] == "Hiring":
            marketplace_channel_id = server_settings.get("hiring_channel_id")
        elif self.post_data["post_type"] == "For-Hire":
            marketplace_channel_id = server_settings.get("forhire_channel_id")
        elif self.post_data["post_type"] == "Selling":
            marketplace_channel_id = server_settings.get("selling_channel_id")
        
        marketplace_channel = interaction.guild.get_channel(marketplace_channel_id)
        
        if not marketplace_channel:
            return await interaction.followup.send(f"The {self.post_data['post_type']} channel could not be found. Please run `/setup marketposts`.", ephemeral=True)
        
        # Update post status in database
        await self.cog.marketplace_posts.update_one(
            {"_id": self.post_data["_id"]},
            {"$set": {
                "status": "approved",
                "approved_by": interaction.user.id,
                "approved_at": datetime.datetime.now()
            }}
        )
        
        # Get post author
        post_author = interaction.guild.get_member(self.post_data["user_id"])
        
        # Create the post embed
        post_embed = discord.Embed(
            title=self.post_data["title"],
            description=self.post_data["description"],
            color=self.get_color_for_post_type(self.post_data["post_type"]),
            timestamp=datetime.datetime.now()
        )
        
        if post_author:
            post_embed.set_author(name=f"{self.post_data['post_type']} by {post_author.display_name}", icon_url=post_author.display_avatar.url)
            post_embed.set_footer(text=f"Posted by: {post_author.name} • ID: {post_author.id}")
        else:
            post_embed.set_author(name=f"{self.post_data['post_type']} Post")
            post_embed.set_footer(text="Posted by: Unknown User")
        
        post_embed.add_field(name="Price/Rate", value=self.post_data["price"], inline=True)
        post_embed.add_field(name="Contact", value=self.post_data["contact"], inline=True)
        post_embed.add_field(name="Post Type", value=self.post_data["post_type"], inline=True)
        
        if self.post_data.get("image_url"):
            post_embed.set_image(url=self.post_data["image_url"])
        
        # Post to marketplace channel
        try:
            marketplace_message = await marketplace_channel.send(
                content=f"**New {self.post_data['post_type']} Post**" + (f" by {post_author.mention}" if post_author else ""),
                embed=post_embed
            )
            
            # Update approval message
            await interaction.message.edit(
                content=f"**{self.post_data['post_type']} Post Approved**\nApproved by: {interaction.user.mention}\nPosted in: {marketplace_channel.mention}",
                view=None
            )
            
            await interaction.followup.send(f"Post approved and published in {marketplace_channel.mention}.", ephemeral=True)
            
            # Notify the author
            if post_author:
                try:
                    notification_embed = discord.Embed(
                        title="Your Marketplace Post was Approved!",
                        description=f"Your {self.post_data['post_type']} post titled **\"{self.post_data['title']}\"** has been approved and published.",
                        color=discord.Color.green(),
                        timestamp=datetime.datetime.now()
                    )
                    notification_embed.add_field(name="View Your Post", value=f"[Click here]({marketplace_message.jump_url})", inline=False)
                    notification_embed.set_footer(text=f"Server: {interaction.guild.name}", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
                    
                    await post_author.send(embed=notification_embed)
                except discord.Forbidden:
                    await interaction.followup.send("Note: Could not DM the post author about the approval.", ephemeral=True)
                except Exception as e:
                    await interaction.followup.send(f"Note: Error sending DM to post author: {str(e)}", ephemeral=True)
            
            # Schedule approval channel for deletion (in 24 hours)
            await self.cog.schedule_channel_deletion(interaction.channel.id, 24)
            
        except Exception as e:
            await interaction.followup.send(f"An error occurred: {str(e)}", ephemeral=True)
    
    @discord.ui.button(label="Decline", style=discord.ButtonStyle.red, custom_id="decline_post")
    async def decline_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        # Get server settings
        guild_id = interaction.guild.id
        server_settings = await self.cog.get_server_settings(guild_id)
        
        if not server_settings:
            return await interaction.followup.send("Marketplace hasn't been set up in this server. Please run `/setup marketposts`.", ephemeral=True)
        
        # Check if user has appropriate role
        approval_mod_roles_ids = server_settings.get("approval_mod_roles", [])
        has_permission = False
        
        for role_id in approval_mod_roles_ids:
            role = interaction.guild.get_role(role_id)
            if role and role in interaction.user.roles:
                has_permission = True
                break
        
        if not has_permission:
            return await interaction.followup.send("You don't have permission to decline marketplace posts.", ephemeral=True)
        
        # Request reason for declining
        modal = DeclineReasonModal(self.cog, self.post_data)
        await interaction.response.send_modal(modal)
    
    def get_color_for_post_type(self, post_type):
        if post_type == "Hiring":
            return discord.Color.from_rgb(66, 135, 245)  # Blue
        elif post_type == "For-Hire":
            return discord.Color.from_rgb(240, 173, 78)  # Orange
        elif post_type == "Selling":
            return discord.Color.from_rgb(92, 184, 92)   # Green
        else:
            return discord.Color.from_rgb(128, 128, 128) # Gray

class DeclineReasonModal(discord.ui.Modal):
    def __init__(self, cog, post_data):
        super().__init__(title="Decline Post")
        self.cog = cog
        self.post_data = post_data
        
        self.reason_input = discord.ui.TextInput(
            label="Reason for declining",
            placeholder="Please provide a reason for declining this post",
            required=True,
            style=discord.TextStyle.paragraph,
            max_length=1000
        )
        self.add_item(self.reason_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        # Update post status in database
        await self.cog.marketplace_posts.update_one(
            {"_id": self.post_data["_id"]},
            {"$set": {
                "status": "declined",
                "declined_by": interaction.user.id,
                "declined_at": datetime.datetime.now(),
                "decline_reason": self.reason_input.value
            }}
        )
        
        # Update approval message
        await interaction.message.edit(
            content=f"**{self.post_data['post_type']} Post Declined**\nDeclined by: {interaction.user.mention}\nReason: {self.reason_input.value}",
            view=None
        )
        
        await interaction.followup.send("Post declined.", ephemeral=True)
        
        # Notify the author
        post_author = interaction.guild.get_member(self.post_data["user_id"])
        if post_author:
            try:
                notification_embed = discord.Embed(
                    title="Your Marketplace Post was Declined",
                    description=f"Your {self.post_data['post_type']} post titled **\"{self.post_data['title']}\"** has been declined.",
                    color=discord.Color.red(),
                    timestamp=datetime.datetime.now()
                )
                notification_embed.add_field(name="Reason", value=self.reason_input.value, inline=False)
                notification_embed.add_field(name="Next Steps", value="You can create a new post that addresses the issues mentioned above.", inline=False)
                notification_embed.set_footer(text=f"Server: {interaction.guild.name}", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
                
                await post_author.send(embed=notification_embed)
            except discord.Forbidden:
                await interaction.followup.send("Note: Could not DM the post author about the decline.", ephemeral=True)
            except Exception as e:
                await interaction.followup.send(f"Note: Error sending DM to post author: {str(e)}", ephemeral=True)
        
        # Schedule approval channel for deletion (in 24 hours)
        await self.cog.schedule_channel_deletion(interaction.channel.id, 24)

class SetupMarketModal(discord.ui.Modal):
    def __init__(self, cog):
        super().__init__(title="Marketplace Setup")
        self.cog = cog
        
        self.hiring_channel = discord.ui.TextInput(
            label="Hiring Channel ID",
            placeholder="Channel ID for hiring posts",
            required=True
        )
        self.add_item(self.hiring_channel)
        
        self.forhire_channel = discord.ui.TextInput(
            label="For-Hire Channel ID",
            placeholder="Channel ID for for-hire posts",
            required=True
        )
        self.add_item(self.forhire_channel)
        
        self.selling_channel = discord.ui.TextInput(
            label="Selling Channel ID", 
            placeholder="Channel ID for selling posts",
            required=True
        )
        self.add_item(self.selling_channel)
        
        self.approvals_category = discord.ui.TextInput(
            label="Approvals Category ID",
            placeholder="Category ID for approval channels",
            required=True
        )
        self.add_item(self.approvals_category)
        
        self.approval_roles = discord.ui.TextInput(
            label="Role IDs (comma separated)",
            placeholder="Approval role IDs (view, mod) separated by commas",
            required=True
        )
        self.add_item(self.approval_roles)
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        # Parse channel IDs
        try:
            hiring_channel_id = int(self.hiring_channel.value.strip())
            forhire_channel_id = int(self.forhire_channel.value.strip())
            selling_channel_id = int(self.selling_channel.value.strip())
            approvals_category_id = int(self.approvals_category.value.strip())
        except ValueError:
            return await interaction.followup.send("Invalid channel or category ID. Please provide valid IDs.", ephemeral=True)
        
        # Parse role IDs
        role_ids = self.approval_roles.value.replace(" ", "").split(",")
        if len(role_ids) < 2:
            return await interaction.followup.send("Please provide at least two role IDs: one for viewing approvals and one for moderating.", ephemeral=True)
        
        # First role ID is for viewing, rest are for moderating
        view_role_id = role_ids[0]
        mod_role_ids = role_ids[1:]
        
        try:
            view_role_id = int(view_role_id)
            mod_role_ids = [int(role_id) for role_id in mod_role_ids]
        except ValueError:
            return await interaction.followup.send("Invalid role ID format. Please provide valid role IDs.", ephemeral=True)
        
        # Verify channels and roles exist
        hiring_channel = interaction.guild.get_channel(hiring_channel_id)
        forhire_channel = interaction.guild.get_channel(forhire_channel_id)
        selling_channel = interaction.guild.get_channel(selling_channel_id)
        approvals_category = interaction.guild.get_channel(approvals_category_id)
        
        if not all([hiring_channel, forhire_channel, selling_channel]):
            return await interaction.followup.send("One or more marketplace channels could not be found. Please check the IDs.", ephemeral=True)
        
        if not approvals_category or not isinstance(approvals_category, discord.CategoryChannel):
            return await interaction.followup.send("The approvals category could not be found or is not a category. Please check the ID.", ephemeral=True)
        
        view_role = interaction.guild.get_role(view_role_id)
        if not view_role:
            return await interaction.followup.send(f"The approval viewing role (ID: {view_role_id}) could not be found.", ephemeral=True)
        
        mod_roles = []
        for role_id in mod_role_ids:
            role = interaction.guild.get_role(role_id)
            if role:
                mod_roles.append(role)
            else:
                return await interaction.followup.send(f"An approval moderator role (ID: {role_id}) could not be found.", ephemeral=True)
        
        # Save settings to database
        guild_id = interaction.guild.id
        
        settings = {
            "guild_id": guild_id,
            "hiring_channel_id": hiring_channel_id,
            "forhire_channel_id": forhire_channel_id,
            "selling_channel_id": selling_channel_id,
            "approvals_category_id": approvals_category_id,
            "approval_view_roles": [view_role_id],
            "approval_mod_roles": mod_role_ids,
            "updated_at": datetime.datetime.now()
        }
        
        # Update or insert settings
        await self.cog.marketplace_settings.update_one(
            {"guild_id": guild_id},
            {"$set": settings},
            upsert=True
        )
        
        # Confirmation message
        embed = discord.Embed(
            title="Marketplace Setup Complete",
            description="The marketplace system has been configured successfully.",
            color=discord.Color.green(),
            timestamp=datetime.datetime.now()
        )
        
        embed.add_field(name="Hiring Channel", value=hiring_channel.mention, inline=True)
        embed.add_field(name="For-Hire Channel", value=forhire_channel.mention, inline=True)
        embed.add_field(name="Selling Channel", value=selling_channel.mention, inline=True)
        embed.add_field(name="Approvals Category", value=approvals_category.mention, inline=False)
        
        view_roles_text = ", ".join([view_role.mention])
        mod_roles_text = ", ".join([role.mention for role in mod_roles])
        
        embed.add_field(name="Approval Viewing Roles", value=view_roles_text, inline=False)
        embed.add_field(name="Approval Moderator Roles", value=mod_roles_text, inline=False)
        
        await interaction.followup.send(embed=embed, ephemeral=True)

class Marketplace(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Create references to MongoDB collections
        self.marketplace_settings = bot.db["marketplace_settings"]
        self.marketplace_posts = bot.db["marketplace_posts"]
        self.scheduled_deletions = bot.db["scheduled_deletions"]
        
        # Start the deletion task
        self.deletion_task = self.bot.loop.create_task(self.check_scheduled_deletions())
    
    def cog_unload(self):
        # Cancel the task when the cog is unloaded
        if self.deletion_task:
            self.deletion_task.cancel()
    
    async def check_scheduled_deletions(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                # Get channels scheduled for deletion
                current_time = datetime.datetime.now()
                query = {"deletion_time": {"$lte": current_time}}
                
                async for scheduled in self.scheduled_deletions.find(query):
                    channel_id = scheduled["channel_id"]
                    guild_id = scheduled["guild_id"]
                    
                    guild = self.bot.get_guild(guild_id)
                    if guild:
                        channel = guild.get_channel(channel_id)
                        if channel:
                            try:
                                await channel.delete(reason="Marketplace post processed")
                            except discord.Forbidden:
                                print(f"Could not delete channel {channel_id}: Missing permissions")
                            except discord.NotFound:
                                # Channel already deleted
                                pass
                            except Exception as e:
                                print(f"Error deleting channel {channel_id}: {str(e)}")
                    
                    # Remove from scheduled deletions
                    await self.scheduled_deletions.delete_one({"_id": scheduled["_id"]})
                
                # Check every hour
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                # Task was cancelled
                break
            except Exception as e:
                print(f"Error in deletion task: {str(e)}")
                await asyncio.sleep(3600)  # Still wait before retrying
    
    async def schedule_channel_deletion(self, channel_id, hours=24):
        """Schedule a channel for deletion after a specified number of hours"""
        channel = self.bot.get_channel(channel_id)
        if not channel:
            return False
        
        deletion_time = datetime.datetime.now() + datetime.timedelta(hours=hours)
        
        # Add to scheduled deletions
        await self.scheduled_deletions.insert_one({
            "channel_id": channel_id,
            "guild_id": channel.guild.id,
            "deletion_time": deletion_time
        })
        
        return True
    
    async def get_server_settings(self, guild_id):
        """Get marketplace settings for a server"""
        settings = await self.marketplace_settings.find_one({"guild_id": guild_id})
        return settings
    
    # Register slash commands properly with the bot's app_commands tree
    # This is the key part that was missing before
    async def cog_load(self):
        # Register commands to the bot tree
        self.bot.tree.add_command(self.post)
        self.bot.tree.add_command(self.setup_marketposts)
        self.bot.tree.add_command(self.marketstats)
        self.bot.tree.add_command(self.mymarketposts)
        self.bot.tree.add_command(self.clearmarketposts)
        self.bot.tree.add_command(self.reset_marketplace)
    
    # Define commands as standalone app_commands instead of using decorators on methods
    post = app_commands.Command(
        name="post", 
        description="Create a marketplace post",
        callback=lambda self, interaction, post_type: self._post_callback(interaction, post_type),
        extras={"cog": "Marketplace"}
    )
    post.add_check(app_commands.guild_only())
    post.add_choice(name="Hiring", value="Hiring")
    post.add_choice(name="For-Hire", value="For-Hire")
    post.add_choice(name="Selling", value="Selling")
    
    setup_marketposts = app_commands.Command(
        name="setup_marketposts",
        description="Set up the marketplace system",
        callback=lambda self, interaction: self._setup_marketposts_callback(interaction),
        default_permissions=discord.Permissions(administrator=True),
        extras={"cog": "Marketplace"}
    )
    setup_marketposts.add_check(app_commands.guild_only())
    
    marketstats = app_commands.Command(
        name="marketstats",
        description="View marketplace statistics",
        callback=lambda self, interaction: self._marketstats_callback(interaction),
        extras={"cog": "Marketplace"}
    )
    marketstats.add_check(app_commands.guild_only())
    
    mymarketposts = app_commands.Command(
        name="mymarketposts",
        description="View your marketplace posts",
        callback=lambda self, interaction: self._mymarketposts_callback(interaction),
        extras={"cog": "Marketplace"}
    )
    mymarketposts.add_check(app_commands.guild_only())
    
    clearmarketposts = app_commands.Command(
        name="clearmarketposts",
        description="Clear old marketplace posts",
        callback=lambda self, interaction, days: self._clearmarketposts_callback(interaction, days),
        default_permissions=discord.Permissions(administrator=True),
        extras={"cog": "Marketplace"}
    )
    clearmarketposts.add_check(app_commands.guild_only())
    
    reset_marketplace = app_commands.Command(
        name="reset_marketplace",
        description="Reset marketplace settings",
        callback=lambda self, interaction: self._reset_marketplace_callback(interaction),
        default_permissions=discord.Permissions(administrator=True),
        extras={"cog": "Marketplace"}
    )
    reset_marketplace.add_check(app_commands.guild_only())
    
    async def _post_callback(self, interaction: discord.Interaction, post_type: str):
        """Create a marketplace post"""
        # Check if marketplace is set up
        guild_id = interaction.guild.id
        server_settings = await self.get_server_settings(guild_id)
        
        if not server_settings:
            return await interaction.response.send_message("Marketplace hasn't been set up in this server. Please ask an admin to run `/setup_marketposts`.", ephemeral=True)
        
        # Open the post creation modal
        modal = MarketPostModal(post_type, self)
        await interaction.response.send_modal(modal)
    
    async def _setup_marketposts_callback(self, interaction: discord.Interaction):
        """Set up the marketplace system"""
        # Check for admin permissions
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("You need administrator permissions to set up the marketplace.", ephemeral=True)
        
        # Open the setup modal
        modal = SetupMarketModal(self)
        await interaction.response.send_modal(modal)
    
    async def _marketstats_callback(self, interaction: discord.Interaction):
        """View marketplace statistics"""
        await interaction.response.defer(ephemeral=True)
        
        guild_id = interaction.guild.id
        
        # Check if marketplace is set up
        server_settings = await self.get_server_settings(guild_id)
        if not server_settings:
            return await interaction.followup.send("Marketplace hasn't been set up in this server. Please ask an admin to run `/setup_marketposts`.", ephemeral=True)
        
        # Get post statistics
        hiring_count = await self.marketplace_posts.count_documents({"guild_id": guild_id, "post_type": "Hiring", "status": "approved"})
        forhire_count = await self.marketplace_posts.count_documents({"guild_id": guild_id, "post_type": "For-Hire", "status": "approved"})
        selling_count = await self.marketplace_posts.count_documents({"guild_id": guild_id, "post_type": "Selling", "status": "approved"})
        
        pending_count = await self.marketplace_posts.count_documents({"guild_id": guild_id, "status": "pending"})
        declined_count = await self.marketplace_posts.count_documents({"guild_id": guild_id, "status": "declined"})
        
        total_count = hiring_count + forhire_count + selling_count
        
        # Create statistics embed
        stats_embed = discord.Embed(
            title="Marketplace Statistics",
            description=f"Statistics for {interaction.guild.name}'s marketplace",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.now()
        )
        
        stats_embed.add_field(name="Total Approved Posts", value=str(total_count), inline=False)
        stats_embed.add_field(name="Hiring Posts", value=str(hiring_count), inline=True)
        stats_embed.add_field(name="For-Hire Posts", value=str(forhire_count), inline=True)
        stats_embed.add_field(name="Selling Posts", value=str(selling_count), inline=True)
        stats_embed.add_field(name="Pending Posts", value=str(pending_count), inline=True)
        stats_embed.add_field(name="Declined Posts", value=str(declined_count), inline=True)
        
        stats_embed.set_footer(text=f"Requested by {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
        
        await interaction.followup.send(embed=stats_embed, ephemeral=True)
    
    async def _mymarketposts_callback(self, interaction: discord.Interaction):
        """View your marketplace posts"""
        await interaction.response.defer(ephemeral=True)
        
        guild_id = interaction.guild.id
        user_id = interaction.user.id
        
        # Check if marketplace is set up
        server_settings = await self.get_server_settings(guild_id)
        if not server_settings:
            return await interaction.followup.send("Marketplace hasn't been set up in this server. Please ask an admin to run `/setup_marketposts`.", ephemeral=True)
        
        # Get user's posts
        user_posts = []
        async for post in self.marketplace_posts.find({"guild_id": guild_id, "user_id": user_id}).sort("created_at", -1).limit(10):
            user_posts.append(post)
        
        if not user_posts:
            return await interaction.followup.send("You haven't made any marketplace posts in this server.", ephemeral=True)
        
        # Create posts embed
        posts_embed = discord.Embed(
            title="Your Marketplace Posts",
            description=f"Your recent marketplace posts in {interaction.guild.name}",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.now()
        )
        
        for post in user_posts:
            status_emoji = "🟢" if post["status"] == "approved" else "🟠" if post["status"] == "pending" else "🔴"
            created_at = post["created_at"].strftime("%Y-%m-%d")
            posts_embed.add_field(
                name=f"{status_emoji} {post['post_type']}: {post['title']}",
                value=f"Status: {post['status'].capitalize()}\nCreated: {created_at}\nPrice: {post['price']}",
                inline=False
            )
        
        posts_embed.set_footer(text=f"Showing {len(user_posts)} most recent posts", icon_url=interaction.user.display_avatar.url)
        
        await interaction.followup.send(embed=posts_embed, ephemeral=True)
    
    async def _clearmarketposts_callback(self, interaction: discord.Interaction, days: int = 30):
        """Clear old marketplace posts"""
        await interaction.response.defer(ephemeral=True)
        
        # Check for admin permissions
        if not interaction.user.guild_permissions.administrator:
            return await interaction.followup.send("You need administrator permissions to clear marketplace posts.", ephemeral=True)
        
        guild_id = interaction.guild.id
        
        # Check if marketplace is set up
        server_settings = await self.get_server_settings(guild_id)
        if not server_settings:
            return await interaction.followup.send("Marketplace hasn't been set up in this server. Please run `/setup_marketposts`.", ephemeral=True)
        
        # Calculate cutoff date
        cutoff_date = datetime.datetime.now() - datetime.timedelta(days=days)
        
        # Delete old posts
        delete_result = await self.marketplace_posts.delete_many({
            "guild_id": guild_id,
            "created_at": {"$lt": cutoff_date}
        })
        
        deleted_count = delete_result.deleted_count
        
        await interaction.followup.send(f"Cleared {deleted_count} marketplace posts older than {days} days.", ephemeral=True)
    
    async def _reset_marketplace_callback(self, interaction: discord.Interaction):
        """Reset marketplace settings"""
        await interaction.response.defer(ephemeral=True)
        
        # Check for admin permissions
        if not interaction.user.guild_permissions.administrator:
            return await interaction.followup.send("You need administrator permissions to reset marketplace settings.", ephemeral=True)
        
        guild_id = interaction.guild.id
        
        # Confirm reset
        confirm_embed = discord.Embed(
            title="Confirm Marketplace Reset",
            description="Are you sure you want to reset all marketplace settings for this server? This action cannot be undone.",
            color=discord.Color.red(),
            timestamp=datetime.datetime.now()
        )
        
        # Create confirmation view
        class ConfirmResetView(discord.ui.View):
            def __init__(self, cog):
                super().__init__(timeout=60)
                self.cog = cog
                self.value = None
            
            @discord.ui.button(label="Confirm Reset", style=discord.ButtonStyle.danger)
            async def confirm(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                if button_interaction.user.id != interaction.user.id:
                    return await button_interaction.response.send_message("You can't use this button.", ephemeral=True)
                
                await button_interaction.response.defer(ephemeral=True)
                
                # Delete settings
                await self.cog.marketplace_settings.delete_one({"guild_id": guild_id})
                
                # Optional: Delete all posts from this guild
                await self.cog.marketplace_posts.delete_many({"guild_id": guild_id})
                
                self.value = True
                self.stop()
                
                await interaction.followup.send("Marketplace settings have been reset. You can set up the marketplace again using `/setup_marketposts`.", ephemeral=True)
            
            @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
            async def cancel(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                if button_interaction.user.id != interaction.user.id:
                    return await button_interaction.response.send_message("You can't use this button.", ephemeral=True)
                
                await button_interaction.response.defer(ephemeral=True)
                self.value = False
                self.stop()
                
                await interaction.followup.send("Marketplace reset canceled.", ephemeral=True)
        
        view = ConfirmResetView(self)
        await interaction.followup.send(embed=confirm_embed, view=view, ephemeral=True)
        
        # Wait for confirmation
        await view.wait()
        if view.value is None:
            await interaction.followup.send("Marketplace reset timed out.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Marketplace(bot))
