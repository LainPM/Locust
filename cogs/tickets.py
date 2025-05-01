import os
import discord
from discord.ext import commands
from discord import app_commands, ui
import sqlite3
import json
import io
from datetime import datetime
import asyncio
from pymongo import MongoClient

# MongoDB setup via environment variable
MONGO_URI = os.getenv('MONGO_URI')
mongo_client = MongoClient(MONGO_URI)
mongo_db = mongo_client['ticket_system']
cases_col = mongo_db['cases']

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
                case_number INTEGER,
                status TEXT,
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
            btn = ui.Button(label=t, style=discord.ButtonStyle.primary, custom_id=f"create_{t}")
            btn.callback = self._on_ticket_button
            self.add_item(btn)

    async def _on_ticket_button(self, interaction: discord.Interaction):
        ttype = interaction.data['custom_id'].split('_',1)[1]
        # Generate next case number
        case_number = cases_col.count_documents({}) + 1
        # Create channel
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT ticket_category_id, mod_roles FROM config WHERE guild_id=?', (interaction.guild.id,))
        cat_id, mod_roles = c.fetchone()
        mod_roles = json.loads(mod_roles)
        overwrites = {interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                      interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True)}
        for r in mod_roles:
            role = interaction.guild.get_role(int(r))
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True)
        channel = await interaction.guild.create_text_channel(name=f"ticket-{case_number}", category=interaction.guild.get_channel(cat_id), overwrites=overwrites)
        # Record in SQLite
        c.execute('INSERT INTO tickets VALUES (?,?,?,?,?)', (interaction.guild.id, channel.id, interaction.user.id, case_number, 'open'))
        conn.commit(); conn.close()
        # Post initial embed
        embed = discord.Embed(title=f"Ticket {case_number}: {ttype}", description="A staff member will be with you shortly.", color=discord.Color.green())
        view = OpenTicketView(self)
        msg = await channel.send(embed=embed, view=view)
        self.bot.add_view(view, message_id=msg.id)
        await interaction.response.send_message(f"Ticket created: {channel.mention}", ephemeral=True)

class OpenTicketView(ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog
        btn = ui.Button(label="Close Ticket", style=discord.ButtonStyle.danger, custom_id="close_ticket")
        btn.callback = self._on_close
        self.add_item(btn)

    async def _on_close(self, interaction: discord.Interaction):
        await interaction.response.send_modal(CloseModal(self.cog))

class CloseModal(ui.Modal, title="Close Ticket"):  # type: ignore
    def __init__(self, cog):
        super().__init__()
        self.cog = cog
    reason = ui.TextInput(label="Reason for closing", style=discord.TextStyle.long)

    async def on_submit(self, interaction: discord.Interaction):
        # Update status
        channel = interaction.channel
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute('UPDATE tickets SET status=? WHERE guild_id=? AND channel_id=?', ('closed', interaction.guild.id, channel.id))
        conn.commit(); conn.close()
        # Build closed view
        view = ClosedTicketView(self.cog)
        await interaction.response.send_message("Ticket closed. You can now generate transcript or reopen.", view=view, ephemeral=False)

class ClosedTicketView(ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog
        self.add_item(ui.Button(label="Generate Transcript", style=discord.ButtonStyle.primary, custom_id="gen_transcript"))
        self.add_item(ui.Button(label="Delete Ticket", style=discord.ButtonStyle.danger, custom_id="delete_ticket"))
        self.add_item(ui.Button(label="Reopen Ticket", style=discord.ButtonStyle.success, custom_id="reopen_ticket"))

    async def interaction_check(self, interaction: discord.Interaction):
        return True

    async def on_timeout(self):
        pass

    @ui.button(label="Generate Transcript", style=discord.ButtonStyle.primary, custom_id="gen_transcript")
    async def _gen_transcript(self, interaction: discord.Interaction, button: ui.Button):
        # Fetch ticket record
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute('SELECT case_number FROM tickets WHERE guild_id=? AND channel_id=?', (interaction.guild.id, interaction.channel.id))
        case_num = c.fetchone()[0]
        conn.close()
        # Gather history
        history = [msg async for msg in interaction.channel.history(limit=None, oldest_first=True)]
        # Build HTML
        html = f"<html><body><pre>Case: {case_num}\n"
        for m in history:
            t = m.created_at.strftime('%Y-%m-%d %H:%M')
            content = m.content.replace('<','&lt;').replace('>','&gt;')
            html += f"[{t}] {m.author}: {content}\n"
        html += "</pre></body></html>"
        # Save to Mongo
        transcript_url = f"transcript://{case_num}"  # placeholder
        cases_col.insert_one({
            'case_number': case_num,
            'guild_id': interaction.guild.id,
            'channel_id': interaction.channel.id,
            'transcript_html': html,
            'reason': self.view.children[0].custom_id,
            'timestamp': datetime.utcnow()
        })
        # Send to transcript channel
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute('SELECT transcript_channel_id FROM config WHERE guild_id=?', (interaction.guild.id,))
        tchan_id = c.fetchone()[0]
        conn.close()
        tchan = interaction.guild.get_channel(tchan_id)
        data = io.BytesIO(html.encode('utf-8'))
        sent = await tchan.send(file=discord.File(data, filename=f"transcript-{case_num}.html"))
        url = sent.attachments[0].url
        await interaction.response.send_message(f"Transcript generated: {url}", ephemeral=True)

    @ui.button(label="Delete Ticket", style=discord.ButtonStyle.danger, custom_id="delete_ticket")
    async def _delete(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("Deleting ticket channel...", ephemeral=True)
        await interaction.channel.delete()

    @ui.button(label="Reopen Ticket", style=discord.ButtonStyle.success, custom_id="reopen_ticket")
    async def _reopen(self, interaction: discord.Interaction, button: ui.Button):
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute('UPDATE tickets SET status=? WHERE guild_id=? AND channel_id=?', ('open', interaction.guild.id, interaction.channel.id))
        conn.commit(); conn.close()
        await interaction.response.send_message("Ticket reopened.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(TicketSystem(bot))
