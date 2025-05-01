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
        await ticket_panel.send(embed=embed, view=view)
        await interaction.response.send_message("Ticket system set up successfully!", ephemeral=True)

class TicketPanelView(ui.View):
    def __init__(self, types):
        super().__init__(timeout=None)
        for t in types:
            self.add_item(ui.Button(label=t, style=discord.ButtonStyle.primary, custom_id=f"create_{t}"))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        gid = interaction.guild.id
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT ticket_panel_id, ticket_category_id, mod_roles FROM config WHERE guild_id=?', (gid,))
        row = c.fetchone()
        conn.close()
        if not row:
            await interaction.response.send_message("Ticket system not configured.", ephemeral=True)
            return False
        custom = interaction.data['custom_id']
        if custom.startswith('create_'):
            await self.create_ticket(interaction, custom.replace('create_', ''))
            return False
        return True

    async def create_ticket(self, interaction: discord.Interaction, ttype: str):
        guild = interaction.guild
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT ticket_category_id, mod_roles FROM config WHERE guild_id=?', (guild.id,))
        cat_id, mod_roles = c.fetchone()
        mod_roles = json.loads(mod_roles)
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
        c.execute('INSERT INTO tickets VALUES (?,?,?)', (guild.id, channel.id, interaction.user.id))
        conn.commit()
        conn.close()

        embed = discord.Embed(
            title=f"Ticket: {ttype}",
            description="A staff member will be with you shortly.",
            color=discord.Color.green()
        )
        view = TicketActionView()
        await channel.send(f"{interaction.user.mention}", embed=embed, view=view)
        await interaction.response.send_message(f"Ticket created: {channel.mention}", ephemeral=True)

class TicketActionView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ui.Button(label="Close Ticket", style=discord.ButtonStyle.danger, custom_id="close_ticket"))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.data['custom_id'] == 'close_ticket':
            await interaction.response.send_modal(CloseModal())
            return False
        return True

class CloseModal(ui.Modal, title="Close Ticket"):  # type: ignore
    reason = ui.TextInput(label="Reason for closing", style=discord.TextStyle.long)

    async def on_submit(self, interaction: discord.Interaction):
        # Acknowledge closing
        await interaction.response.send_message("Ticket is closing and transcript will be generated shortly.", ephemeral=False)

        channel = interaction.channel
        # Gather config
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT transcript_channel_id FROM config WHERE guild_id=?', (interaction.guild.id,))
        tchan_id = c.fetchone()[0]
        conn.close()
        transcript_chan = interaction.guild.get_channel(tchan_id)

        # Fetch messages
        messages = [msg async for msg in channel.history(limit=None, oldest_first=True)]
        msg_count = len(messages)

        # Count attachments
        att_saved = 0
        att_skipped = 0
        for m in messages:
            for att in m.attachments:
                if att.size <= 8 * 1024 * 1024:  # 8MB limit
                    att_saved += 1
                else:
                    att_skipped += 1

        # User info counts
        user_counts = {}
        for m in messages:
            uid = m.author.id
            user_counts.setdefault(uid, {'user': m.author, 'count': 0})
            user_counts[uid]['count'] += 1

        # Build HTML
        html = "<html><body><pre>"
        html += "<Server-Info>\n"
        html += f"    Server: {interaction.guild.name} ({interaction.guild.id})\n"
        html += f"    Channel: {channel.name} ({channel.id})\n"
        html += f"    Messages: {msg_count}\n"
        html += f"    Attachments Saved: {att_saved}\n"
        html += f"    Attachments Skipped: {att_skipped}\n\n"
        html += "<User-Info>\n"
        for i, data in enumerate(user_counts.values(), 1):
            user = data['user']
            html += f"    {i} - {user} ({user.id}): {data['count']}\n"
        html += "\n<Base-Transcript>\n"
        for m in messages:
            t = m.created_at.strftime('%Y-%m-%d %H:%M')
            content = m.content.replace('<', '&lt;').replace('>', '&gt;')
            html += f"[{t}] {m.author}: {content}\n"
        html += f"\nClosed by {interaction.user} for reason: {self.reason.value}\n"
        html += "</pre></body></html>"

        data = io.BytesIO(html.encode('utf-8'))

        # Send transcript file
        sent = await transcript_chan.send(file=discord.File(data, filename=f"transcript-{channel.id}.html"))
        url = sent.attachments[0].url

        # Send link button
        view = ui.View()
        view.add_item(ui.Button(label="View Transcript", url=url))
        await channel.send("Here is your transcript:", view=view)

        # Clean DB and delete channel
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('DELETE FROM tickets WHERE guild_id=? AND channel_id=?', (interaction.guild.id, channel.id))
        conn.commit()
        conn.close()

        await asyncio.sleep(60)
        await channel.delete(reason="Ticket closed and cleaned up.")

async def setup(bot):
    await bot.add_cog(TicketSystem(bot))
