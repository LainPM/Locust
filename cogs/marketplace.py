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
            return await interaction.followup.send("Marketplace hasn't been set up in this server. Please ask an admin to run `/setup_marketposts`.", ephemeral=True)
        
        approvals_category_id = server_settings.get("approvals_category_id")
        approvals_category = interaction.guild.get_channel(approvals_category_id)
        
        if not approvals_category:
            return await interaction.followup.send("The approvals category could not be found. Please ask an admin to run `/setup_marketposts`.", ephemeral=True)
        
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
        
        post_result = await self.cog.marketplace_posts.insert_one(post_data)
        post_data["_id"] = post_result.inserted_id  # Add the ID to post_data
        
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
            return await interaction.followup.send("Marketplace hasn't been set up in this server. Please run `/setup_marketposts`.", ephemeral=True)
        
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
            return await interaction.followup.send(f"The {self.post_data['post_type']} channel could not be found. Please run `/setup_marketposts`.", ephemeral=True)
        
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
            
            # Save the message ID in the database for potential deletion later
            await self.cog.marketplace_posts.update_one(
                {"_id": self.post_data["_id"]},
                {"$set": {"message_id": marketplace_message.id}}
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
            
            # Schedule approval channel for deletion (in 1 minute)
            await self.cog.schedule_channel_deletion(interaction.channel.id, 0.016)  # 0.016 hours = 1 minute
            
        except Exception as e:
            await interaction.followup.send(f"An error occurred: {str(e)}", ephemeral=True)
    
    @discord.ui.button(label="Decline", style=discord.ButtonStyle.red, custom_id="decline_post")
    async def decline_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        # Get server settings
        guild_id = interaction.guild.id
        server_settings = await self.cog.get_server_settings(guild_id)
        
        if not server_settings:
            return await interaction.followup.send("Marketplace hasn't been set up in this server. Please run `/setup_marketposts`.", ephemeral=True)
        
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
        
        # Create decline reason prompt
        class DeclinePrompt(discord.ui.View):
            def __init__(self, cog, post_data):
                super().__init__(timeout=300)  # 5 minute timeout
                self.cog = cog
                self.post_data = post_data
                self.reason = None
                
                # Add a text input for the reason
                self.reason_input = discord.ui.TextInput(
                    label="Reason for declining",
                    placeholder="Please provide a reason for declining this post",
                    required=True,
                    style=discord.TextStyle.paragraph,
                    max_length=1000
                )
            
            @discord.ui.button(label="Submit Reason", style=discord.ButtonStyle.red)
            async def submit_button(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                # Show a modal for the reason input
                modal = DeclineReasonModal(self.cog, self.post_data)
                await button_interaction.response.send_modal(modal)
            
            @discord.ui.button(label="Cancel", style=discord.ButtonStyle.gray)
            async def cancel_button(self, cancel_interaction: discord.Interaction, button: discord.ui.Button):
                if cancel_interaction.user.id != interaction.user.id:
                    return await cancel_interaction.response.send_message("This is not your action to cancel.", ephemeral=True)
                
                await cancel_interaction.response.defer()
                await interaction.edit_original_response(
                    content="Post decline cancelled.",
                    view=None
                )
        
        # Send the decline reason prompt
        await interaction.followup.send(
            content=f"Please click **Submit Reason** to provide a reason for declining this post.",
            view=DeclinePrompt(self.cog, self.post_data),
            ephemeral=True
        )
    
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
        
        # Get the message to update
        try:
            channel = interaction.guild.get_channel(self.post_data["channel_id"])
            if channel:
                # Find the original message with the buttons (first message in the channel)
                async for message in channel.history(limit=5):
                    if message.author == interaction.guild.me and len(message.components) > 0:
                        # Found the message with buttons, update it
                        await message.edit(
                            content=f"**{self.post_data['post_type']} Post Declined**\nDeclined by: {interaction.user.mention}\nReason: {self.reason_input.value}",
                            view=None
                        )
                        break
        except Exception as e:
            print(f"Error finding approval message: {str(e)}")
        
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
        
        # Schedule approval channel for deletion (in 1 minute)
        await self.cog.schedule_channel_deletion(self.post_data["channel_id"], 0.016)  # 0.016 hours = 1 minute

class Marketplace(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Create references to MongoDB collections
        self.marketplace_settings = bot.db["marketplace_settings"]
        self.marketplace_posts = bot.db["marketplace_posts"]
        self.scheduled_deletions = bot.db["scheduled_deletions"]
        
        # Start the deletion task and make it check every 30 seconds instead of every hour
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
                                print(f"Deleted channel {channel_id} from guild {guild_id}")
                            except discord.Forbidden:
                                print(f"Could not delete channel {channel_id}: Missing permissions")
                            except discord.NotFound:
                                # Channel already deleted
                                print(f"Channel {channel_id} already deleted")
                            except Exception as e:
                                print(f"Error deleting channel {channel_id}: {str(e)}")
                    
                    # Remove from scheduled deletions
                    await self.scheduled_deletions.delete_one({"_id": scheduled["_id"]})
                
                # Check every 30 seconds instead of every hour
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                # Task was cancelled
                break
            except Exception as e:
                print(f"Error in deletion task: {str(e)}")
                # Still wait before retrying, but shorter period
                await asyncio.sleep(30)
    
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
        
        print(f"Scheduled channel {channel_id} for deletion at {deletion_time}")
        return True
    
    async def get_server_settings(self, guild_id):
        """Get marketplace settings for a server"""
        settings = await self.marketplace_settings.find_one({"guild_id": guild_id})
        return settings
    
    # Use the normal decorator approach instead of defining commands separately
    @app_commands.command(name="post", description="Create a marketplace post")
    @app_commands.guild_only()
    @app_commands.choices(post_type=[
        app_commands.Choice(name="Hiring", value="Hiring"),
        app_commands.Choice(name="For-Hire", value="For-Hire"),
        app_commands.Choice(name="Selling", value="Selling")
    ])
    async def post(self, interaction: discord.Interaction, post_type: str):
        """Create a marketplace post"""
        # Check if marketplace is set up
        guild_id = interaction.guild.id
        server_settings = await self.get_server_settings(guild_id)
        
        if not server_settings:
            return await interaction.response.send_message("Marketplace hasn't been set up in this server. Please ask an admin to run `/setup_marketposts`.", ephemeral=True)
        
        # Open the post creation modal
        modal = MarketPostModal(post_type, self)
        await interaction.response.send_modal(modal)
    
    @app_commands.command(name="setup_marketposts", description="Set up the marketplace system")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def setup_marketposts(
        self,
        interaction: discord.Interaction,
        hiring_channel: discord.TextChannel, 
        forhire_channel: discord.TextChannel,
        selling_channel: discord.TextChannel,
        approvals_category: discord.CategoryChannel,
        view_role: discord.Role,
        mod_role1: discord.Role,
        mod_role2: Optional[discord.Role] = None,
        mod_role3: Optional[discord.Role] = None,
        mod_role4: Optional[discord.Role] = None,
        mod_role5: Optional[discord.Role] = None
    ):
        """Set up the marketplace system with channel and role mentions"""
        await interaction.response.defer(ephemeral=True)
        
        # Check for admin permissions
        if not interaction.user.guild_permissions.administrator:
            return await interaction.followup.send("You need administrator permissions to set up the marketplace.", ephemeral=True)
        
        # Collect the channel IDs
        hiring_channel_id = hiring_channel.id
        forhire_channel_id = forhire_channel.id
        selling_channel_id = selling_channel.id
        approvals_category_id = approvals_category.id
        
        # Collect the role IDs
        view_role_id = view_role.id
        mod_role_ids = [mod_role1.id]
        
        # Add optional moderator roles if provided
        if mod_role2:
            mod_role_ids.append(mod_role2.id)
        if mod_role3:
            mod_role_ids.append(mod_role3.id)
        if mod_role4:
            mod_role_ids.append(mod_role4.id)
        if mod_role5:
            mod_role_ids.append(mod_role5.id)
        
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
        await self.marketplace_settings.update_one(
            {"guild_id": guild_id},
            {"$set": settings},
            upsert=True
        )
        
        # Collect the role mentions for the confirmation message
        mod_roles = [mod_role1]
        if mod_role2:
            mod_roles.append(mod_role2)
        if mod_role3:
            mod_roles.append(mod_role3)
        if mod_role4:
            mod_roles.append(mod_role4)
        if mod_role5:
            mod_roles.append(mod_role5)
        
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
        
        view_roles_text = view_role.mention
        mod_roles_text = " ".join([role.mention for role in mod_roles])
        
        embed.add_field(name="Approval Viewing Role", value=view_roles_text, inline=False)
        embed.add_field(name="Approval Moderator Roles", value=mod_roles_text, inline=False)
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    @app_commands.command(name="marketplace_stats", description="View marketplace statistics")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def marketplace_stats(self, interaction: discord.Interaction):
        """View marketplace statistics"""
        await interaction.response.defer(ephemeral=True)
        
        # Check for admin permissions
        if not interaction.user.guild_permissions.administrator:
            return await interaction.followup.send("You need administrator permissions to view marketplace statistics.", ephemeral=True)
        
        # Get statistics from the database
        guild_id = interaction.guild.id
        
        # Count posts by status and type
        pipeline = [
            {"$match": {"guild_id": guild_id}},
            {"$group": {
                "_id": {
                    "post_type": "$post_type",
                    "status": "$status"
                },
                "count": {"$sum": 1}
            }}
        ]
        
        stats = {}
        async for result in self.marketplace_posts.aggregate(pipeline):
            post_type = result["_id"]["post_type"]
            status = result["_id"]["status"]
            count = result["count"]
            
            if post_type not in stats:
                stats[post_type] = {}
            
            stats[post_type][status] = count
        
        # Create embed
        embed = discord.Embed(
            title="Marketplace Statistics",
            description="Statistics for marketplace posts in this server",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.now()
        )
        
        # Add stats for each post type
        for post_type in ["Hiring", "For-Hire", "Selling"]:
            if post_type in stats:
                post_stats = stats[post_type]
                approved = post_stats.get("approved", 0)
                pending = post_stats.get("pending", 0)
                declined = post_stats.get("declined", 0)
                total = approved + pending + declined
                
                embed.add_field(
                    name=f"{post_type} Posts",
                    value=f"Total: {total}\nApproved: {approved}\nPending: {pending}\nDeclined: {declined}",
                    inline=True
                )
            else:
                embed.add_field(
                    name=f"{post_type} Posts",
                    value="No posts yet",
                    inline=True
                )
        
        # Add overall stats
        total_approved = sum([stats.get(pt, {}).get("approved", 0) for pt in stats])
        total_pending = sum([stats.get(pt, {}).get("pending", 0) for pt in stats])
        total_declined = sum([stats.get(pt, {}).get("declined", 0) for pt in stats])
        total_posts = total_approved + total_pending + total_declined
        
        embed.add_field(
            name="Overall Statistics",
            value=f"Total Posts: {total_posts}\nApproved: {total_approved}\nPending: {total_pending}\nDeclined: {total_declined}",
            inline=False
        )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    @app_commands.command(name="my_posts", description="View your marketplace posts")
    @app_commands.guild_only()
    async def my_posts(self, interaction: discord.Interaction):
        """View your marketplace posts"""
        await interaction.response.defer(ephemeral=True)
        
        # Get user's posts from the database
        guild_id = interaction.guild.id
        user_id = interaction.user.id
        
        cursor = self.marketplace_posts.find({
            "guild_id": guild_id,
            "user_id": user_id
        }).sort("created_at", -1)  # Sort by creation date, newest first
        
        posts = []
        async for post in cursor:
            posts.append(post)
        
        if not posts:
            return await interaction.followup.send("You haven't created any marketplace posts yet.", ephemeral=True)
        
        # Create embed
        embed = discord.Embed(
            title="Your Marketplace Posts",
            description=f"You have created {len(posts)} marketplace posts",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.now()
        )
        
        # Add fields for each post (limit to most recent 10)
        for post in posts[:10]:
            status_emoji = "🟢" if post["status"] == "approved" else "🟠" if post["status"] == "pending" else "🔴"
            post_date = post["created_at"].strftime("%Y-%m-%d")
            
            embed.add_field(
                name=f"{status_emoji} {post['post_type']}: {post['title']}",
                value=f"**Status:** {post['status'].capitalize()}\n**Posted:** {post_date}\n**Price:** {post['price']}",
                inline=False
            )
        
        if len(posts) > 10:
            embed.set_footer(text=f"Showing 10 most recent posts out of {len(posts)}")
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    @app_commands.command(name="delete_post", description="Delete one of your marketplace posts")
    @app_commands.guild_only()
    async def delete_post(self, interaction: discord.Interaction, post_id: str):
        """Delete one of your marketplace posts"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Validate ObjectId format
            from bson.objectid import ObjectId
            post_object_id = ObjectId(post_id)
        except:
            return await interaction.followup.send("Invalid post ID format.", ephemeral=True)
        
        # Find the post
        post = await self.marketplace_posts.find_one({"_id": post_object_id})
        
        if not post:
            return await interaction.followup.send("Post not found.", ephemeral=True)
        
        # Check if the user is the owner of the post or an admin
        is_admin = interaction.user.guild_permissions.administrator
        is_owner = post["user_id"] == interaction.user.id
        
        if not (is_owner or is_admin):
            return await interaction.followup.send("You don't have permission to delete this post.", ephemeral=True)
        
        # Confirm deletion with a button view
        class ConfirmDeletionView(discord.ui.View):
            def __init__(self, cog, post):
                super().__init__(timeout=60)
                self.cog = cog
                self.post = post
            
            @discord.ui.button(label="Confirm Deletion", style=discord.ButtonStyle.red)
            async def confirm(self, confirm_interaction: discord.Interaction, button: discord.ui.Button):
                # Check if the user is the same
                if confirm_interaction.user.id != interaction.user.id:
                    return await confirm_interaction.response.send_message("This is not your confirmation dialog.", ephemeral=True)
                
                await confirm_interaction.response.defer(ephemeral=True)
                
                # Delete the post from the database
                await self.cog.marketplace_posts.delete_one({"_id": self.post["_id"]})
                
                # If the post is approved, try to delete it from the marketplace channel
                if self.post["status"] == "approved":
                    try:
                        # Get server settings
                        server_settings = await self.cog.get_server_settings(interaction.guild.id)
                        
                        # Get appropriate channel based on post type
                        channel_id = None
                        if self.post["post_type"] == "Hiring":
                            channel_id = server_settings.get("hiring_channel_id")
                        elif self.post["post_type"] == "For-Hire":
                            channel_id = server_settings.get("forhire_channel_id")
                        elif self.post["post_type"] == "Selling":
                            channel_id = server_settings.get("selling_channel_id")
                        
                        if channel_id:
                            channel = interaction.guild.get_channel(channel_id)
                            if channel and "message_id" in self.post:
                                try:
                                    message = await channel.fetch_message(self.post["message_id"])
                                    await message.delete()
                                except:
                                    pass  # Message may already be deleted
                    except Exception as e:
                        # Log error but continue
                        print(f"Error deleting message for post {self.post['_id']}: {str(e)}")
                
                await confirm_interaction.followup.send("Post has been deleted.", ephemeral=True)
                
                # Update the original message
                await interaction.edit_original_response(
                    content="The post has been deleted.",
                    view=None
                )
            
            @discord.ui.button(label="Cancel", style=discord.ButtonStyle.gray)
            async def cancel(self, cancel_interaction: discord.Interaction, button: discord.ui.Button):
                # Check if the user is the same
                if cancel_interaction.user.id != interaction.user.id:
                    return await cancel_interaction.response.send_message("This is not your confirmation dialog.", ephemeral=True)
                
                await cancel_interaction.response.defer(ephemeral=True)
                await interaction.edit_original_response(
                    content="Post deletion cancelled.",
                    view=None
                )
                
                await cancel_interaction.followup.send("Post deletion cancelled.", ephemeral=True)
        
        # Create confirmation view
        view = ConfirmDeletionView(self, post)
        
        # Send confirmation message
        await interaction.followup.send(
            f"Are you sure you want to delete the {post['post_type']} post titled **\"{post['title']}\"**?\n"
            f"Status: {post['status'].capitalize()}\n"
            f"This action cannot be undone.",
            view=view,
            ephemeral=True
        )
    
    @app_commands.command(name="marketplace_help", description="Get help with the marketplace commands")
    async def marketplace_help(self, interaction: discord.Interaction):
        """Get help with the marketplace commands"""
        embed = discord.Embed(
            title="Marketplace Help",
            description="Here are the commands available for the marketplace system:",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="`/post [type]`",
            value="Create a new marketplace post. Types: Hiring, For-Hire, Selling",
            inline=False
        )
        
        embed.add_field(
            name="`/my_posts`",
            value="View all your marketplace posts",
            inline=False
        )
        
        embed.add_field(
            name="`/delete_post [post_id]`",
            value="Delete one of your marketplace posts",
            inline=False
        )
        
        embed.add_field(
            name="`/marketplace_stats` (Admin)",
            value="View statistics for all marketplace posts",
            inline=False
        )
        
        embed.add_field(
            name="`/setup_marketposts` (Admin)",
            value="Set up or update the marketplace system",
            inline=False
        )
        
        embed.add_field(
            name="How It Works",
            value=(
                "1. Create a post with `/post`\n"
                "2. Your post will be reviewed by moderators\n"
                "3. If approved, it will be posted in the appropriate channel\n"
                "4. You'll receive a DM notification about the approval/decline"
            ),
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @delete_post.autocomplete('post_id')
    async def post_id_autocomplete(self, interaction: discord.Interaction, current: str):
        """Autocomplete for post IDs"""
        guild_id = interaction.guild.id
        user_id = interaction.user.id
        
        # Get user's posts from the database
        cursor = self.marketplace_posts.find({
            "guild_id": guild_id,
            "user_id": user_id
        }).sort("created_at", -1).limit(25)  # Sort by creation date, newest first, limit to 25
        
        choices = []
        async for post in cursor:
            post_id = str(post["_id"])
            post_title = post["title"]
            post_type = post["post_type"]
            post_status = post["status"]
            
            # Create a display name with type, status and title
            display_name = f"{post_type} ({post_status}): {post_title[:20]}"
            
            # Filter based on current input (if any)
            if not current or current.lower() in post_id.lower() or current.lower() in post_title.lower():
                choices.append(app_commands.Choice(name=display_name, value=post_id))
        
        return choices[:25]  # Discord limits to 25 choices
    
    @app_commands.command(name="pending_approvals", description="View pending marketplace posts")
    @app_commands.guild_only()
    async def pending_approvals(self, interaction: discord.Interaction):
        """View pending marketplace posts for moderators"""
        await interaction.response.defer(ephemeral=True)
        
        # Get server settings
        guild_id = interaction.guild.id
        server_settings = await self.get_server_settings(guild_id)
        
        if not server_settings:
            return await interaction.followup.send("Marketplace hasn't been set up in this server.", ephemeral=True)
        
        # Check if user has appropriate role
        approval_mod_roles_ids = server_settings.get("approval_mod_roles", [])
        has_permission = False
        
        for role_id in approval_mod_roles_ids:
            role = interaction.guild.get_role(role_id)
            if role and role in interaction.user.roles:
                has_permission = True
                break
        
        if not has_permission:
            return await interaction.followup.send("You don't have permission to view pending approvals.", ephemeral=True)
        
        # Get pending posts
        cursor = self.marketplace_posts.find({
            "guild_id": guild_id,
            "status": "pending"
        }).sort("created_at", 1)  # Sort by creation date, oldest first
        
        pending_posts = []
        async for post in cursor:
            pending_posts.append(post)
        
        if not pending_posts:
            return await interaction.followup.send("There are no pending marketplace posts.", ephemeral=True)
        
        # Create embed
        embed = discord.Embed(
            title="Pending Marketplace Posts",
            description=f"There are {len(pending_posts)} posts waiting for approval",
            color=discord.Color.orange(),
            timestamp=datetime.datetime.now()
        )
        
        # Add fields for each post (limit to 10)
        for post in pending_posts[:10]:
            post_date = post["created_at"].strftime("%Y-%m-%d %H:%M")
            user = interaction.guild.get_member(post["user_id"])
            user_mention = user.mention if user else f"Unknown User ({post['user_id']})"
            
            # Get approval channel
            channel = interaction.guild.get_channel(post["channel_id"])
            channel_link = f"[View Channel]({channel.jump_url})" if channel else "Channel Not Found"
            
            embed.add_field(
                name=f"{post['post_type']}: {post['title']}",
                value=f"**Submitted by:** {user_mention}\n**Posted:** {post_date}\n**Approval Channel:** {channel_link}",
                inline=False
            )
        
        if len(pending_posts) > 10:
            embed.set_footer(text=f"Showing 10 oldest posts out of {len(pending_posts)}")
        
        await interaction.followup.send(embed=embed, ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message):
        # Ignore bot messages
        if message.author.bot:
            return
        
        # Only process messages in marketplace channels
        if not message.guild:
            return
        
        # Get server settings
        server_settings = await self.get_server_settings(message.guild.id)
        if not server_settings:
            return
        
        # Check if the message is in a marketplace channel
        channel_id = message.channel.id
        marketplace_channels = [
            server_settings.get("hiring_channel_id"),
            server_settings.get("forhire_channel_id"),
            server_settings.get("selling_channel_id")
        ]
        
        if channel_id not in marketplace_channels:
            return
        
        # Check if user has moderator role
        has_mod_role = False
        mod_role_ids = server_settings.get("approval_mod_roles", [])
        for role in message.author.roles:
            if role.id in mod_role_ids:
                has_mod_role = True
                break
        
        # If not a moderator, delete the message and send a DM
        if not has_mod_role:
            try:
                await message.delete()
                
                # Get channel type
                channel_type = None
                if channel_id == server_settings.get("hiring_channel_id"):
                    channel_type = "Hiring"
                elif channel_id == server_settings.get("forhire_channel_id"):
                    channel_type = "For-Hire"
                elif channel_id == server_settings.get("selling_channel_id"):
                    channel_type = "Selling"
                
                # Send DM to the user
                try:
                    embed = discord.Embed(
                        title="Message Removed",
                        description="Your message in the marketplace channel was automatically removed.",
                        color=discord.Color.orange()
                    )
                    
                    embed.add_field(
                        name="Why was my message removed?",
                        value=f"The {channel_type} channel is only for approved marketplace posts. To create a post, use the `/post` command and select the appropriate type.",
                        inline=False
                    )
                    
                    await message.author.send(embed=embed)
                except:
                    # Unable to DM the user, just continue
                    pass
            except:
                # Unable to delete the message, just continue
                pass

async def setup(bot):
    await bot.add_cog(Marketplace(bot))
