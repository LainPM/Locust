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
        # Init DB
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
        channel = interaction.channel
        messages = [msg async for msg in channel.history(limit=None, oldest_first=True)]
        html = "<html><body>"
        for m in messages:
            time = m.created_at.strftime('%Y-%m-%d %H:%M')
            html += f"<p><strong>{m.author} [{time}]</strong>: {m.content}</p>"
        html += f"<p><em>Closed by {interaction.user} for reason: {self.reason.value}</em></p>"
        html += "</body></html>"
        data = io.BytesIO(html.encode('utf-8'))

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT transcript_channel_id FROM config WHERE guild_id=?', (interaction.guild.id,))
        tchan_id = c.fetchone()[0]
        conn.close()

        tchan = interaction.guild.get_channel(tchan_id)
        msg = await tchan.send(file=discord.File(data, filename=f"transcript-{channel.id}.html"))
        url = msg.attachments[0].url

        view = ui.View()
        view.add_item(ui.Button(label="View Transcript", url=url))
        await channel.send("Transcript generated:", view=view)

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('DELETE FROM tickets WHERE guild_id=? AND channel_id=?', (interaction.guild.id, channel.id))
        conn.commit()
        conn.close()

        await asyncio.sleep(60)
        await channel.delete(reason="Ticket closed and cleaned up.")

async def setup(bot):
    await bot.add_cog(TicketSystem(bot))
