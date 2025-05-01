import discord
from discord.ext import commands
from discord import app_commands, ui
import sqlite3
import json
import io
from datetime import datetime
import asyncio

DB_PATH = 'tickets.db'

class TicketSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.conn = sqlite3.connect(DB_PATH)
        self._init_db()

    def _init_db(self):
        c = self.conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS config (
                guild_id INTEGER PRIMARY KEY,
                ticket_panel_id INTEGER,
                transcript_channel_id INTEGER,
                ticket_category_id INTEGER,
                ticket_types TEXT,
                mod_roles TEXT
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS tickets (
                guild_id INTEGER,
                channel_id INTEGER,
                user_id INTEGER,
                PRIMARY KEY (guild_id, channel_id)
            )
        ''')
        self.conn.commit()

    @app_commands.command(name="setup_ticket_system", description="Setup the ticketing system")
    @app_commands.describe(
        ticket_panel='Channel to post the ticket panel',
        transcript_channel='Channel to send transcripts',
        ticket_category='Category to create tickets under',
        ticket_types='Comma-separated ticket types (e.g. Support,Bug)',
        moderator_roles='Comma-separated role IDs or @roles'
    )
    async def setup_ticket_system(
        self, interaction: discord.Interaction,
        ticket_panel: discord.TextChannel,
        transcript_channel: discord.TextChannel,
        ticket_category: discord.CategoryChannel,
        ticket_types: str,
        moderator_roles: str
    ):
        guild_id = interaction.guild.id
        c = self.conn.cursor()
        c.execute('REPLACE INTO config VALUES (?,?,?,?,?,?)', (
            guild_id,
            ticket_panel.id,
            transcript_channel.id,
            ticket_category.id,
            json.dumps([t.strip() for t in ticket_types.split(',')]),
            json.dumps([r.strip('<@&> ') for r in moderator_roles.split(',')])
        ))
        self.conn.commit()

        embed = discord.Embed(
            title="Ticket Panel",
            description="Click a button to create a ticket",
            color=discord.Color.blurple()
        )
        types = [t.strip() for t in ticket_types.split(',')]
        view = TicketPanelView(types)
        message = await ticket_panel.send(embed=embed, view=view)
        self.bot.add_view(view, message_id=message.id)
        await interaction.response.send_message("Ticket system set up successfully!", ephemeral=True)

class TicketPanelView(ui.View):
    def __init__(self, types):
        super().__init__(timeout=None)
        for t in types:
            button = ui.Button(label=t, style=discord.ButtonStyle.primary, custom_id=f"create_{t}")
            button.callback = self._on_ticket_button
            self.add_item(button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT ticket_panel_id FROM config WHERE guild_id=?', (interaction.guild.id,))
        exists = c.fetchone() is not None
        conn.close()
        if not exists:
            await interaction.response.send_message("Ticket system not configured.", ephemeral=True)
            return False
        return True

    async def _on_ticket_button(self, interaction: discord.Interaction):
        ttype = interaction.data['custom_id'].replace('create_', '')
        await self.create_ticket(interaction, ttype)

    async def create_ticket(self, interaction: discord.Interaction, ttype: str):
        guild = interaction.guild
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT ticket_category_id, mod_roles FROM config WHERE guild_id=?', (guild.id,))
        cat_id, mod_roles = c.fetchone()
        mod_roles = json.loads(mod_roles)
        conn.close()

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }
        for r in mod_roles:
            role = guild.get_role(int(r))
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True)

        channel = await guild.create_text_channel(
            name=f"{ttype.lower()}-{interaction.user.name}",
            category=guild.get_channel(cat_id),
            overwrites=overwrites
        )
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('INSERT INTO tickets VALUES (?,?,?)', (guild.id, channel.id, interaction.user.id))
        conn.commit()
        conn.close()

        embed = discord.Embed(
            title=f"Ticket: {ttype}",
            description="A staff member will be with you shortly.",
            color=discord.Color.green()
        )
        view = TicketActionView(self.bot)
        ticket_msg = await channel.send(f"{interaction.user.mention}", embed=embed, view=view)
        self.bot.add_view(view, message_id=ticket_msg.id)

        await interaction.response.send_message(f"Ticket created: {channel.mention}", ephemeral=True)

class TicketActionView(ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        button = ui.Button(label="Close Ticket", style=discord.ButtonStyle.danger, custom_id="close_ticket")
        button.callback = self._on_close
        self.add_item(button)

    async def _on_close(self, interaction: discord.Interaction):
        await interaction.response.send_modal(CloseModal(self.bot))

class CloseModal(ui.Modal, title="Close Ticket"):  # type: ignore
    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    reason = ui.TextInput(label="Reason for closing", style=discord.TextStyle.long)

    async def on_submit(self, interaction: discord.Interaction):
        # Acknowledge modal without leaving a public error
        await interaction.response.defer()
        channel = interaction.channel
        # Notify in-channel
        await channel.send("Ticket is closing and transcript will be generated shortly.")

        # Fetch config
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT transcript_channel_id FROM config WHERE guild_id=?', (interaction.guild.id,))
        tchan_id = c.fetchone()[0]
        conn.close()
        transcript_chan = interaction.guild.get_channel(tchan_id)

        # Gather history, exclude this closing notice
        history = [msg async for msg in channel.history(limit=None, oldest_first=True)]
        # Filter out the bot's just-sent closing notice
        history = [m for m in history if not (m.author == interaction.guild.me and m.content.startswith("Ticket is closing"))]

        msg_count = len(history)
        att_saved = sum(1 for m in history for att in m.attachments if att.size <= 8*1024*1024)
        att_skipped = sum(1 for m in history for att in m.attachments if att.size > 8*1024*1024)

        # Count messages per user
        user_counts = {}
        for m in history:
            uid = m.author.id
            if uid not in user_counts:
                user_counts[uid] = {'user': m.author, 'count': 0}
            user_counts[uid]['count'] += 1

        # Build HTML transcript
        html = "<html><body><pre>"
        html += f"<Server-Info>\n    Server: {interaction.guild.name} ({interaction.guild.id})\n    Channel: {channel.name} ({channel.id})\n    Messages: {msg_count}\n    Attachments Saved: {att_saved}\n    Attachments Skipped: {att_skipped}\n\n"
        html += "<User-Info>\n"
        for i, data in enumerate(user_counts.values(), 1):
            user = data['user']
            html += f"    {i} - {user} ({user.id}): {data['count']}\n"
        html += "\n<Base-Transcript>\n"
        for m in history:
            t = m.created_at.strftime('%Y-%m-%d %H:%M')
            content = m.content.replace('<', '&lt;').replace('>', '&gt;')
            html += f"[{t}] {m.author}: {content}\n"
        html += f"\nClosed by {interaction.user} for reason: {self.reason.value}\n"
        html += "</pre></body></html>"

        data = io.BytesIO(html.encode('utf-8'))
        sent = await transcript_chan.send(file=discord.File(data, filename=f"transcript-{channel.id}.html"))
        url = sent.attachments[0].url

        # Provide link button
        view = ui.View()
        view.add_item(ui.Button(label="View Transcript", url=url))
        await channel.send("Here is your transcript:", view=view)

        # Cleanup DB and channel
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('DELETE FROM tickets WHERE guild_id=? AND channel_id=?', (interaction.guild.id, channel.id))
        conn.commit()
        conn.close()

        await asyncio.sleep(60)
        await channel.delete(reason="Ticket closed and cleaned up.")

async def setup(bot):
    await bot.add_cog(TicketSystem(bot))
