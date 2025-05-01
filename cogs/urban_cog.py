import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
import asyncio
import json
import datetime
import re

class UrbanCog(commands.Cog):
    """Urban Dictionary lookup commands"""
    
    def __init__(self, bot):
        self.bot = bot
        self.urban_api_url = "https://api.urbandictionary.com/v0/define?term="
        self.color = 0x134FE6  # Urban Dictionary blue color
    
    async def fetch_urban_definition(self, term):
        """Fetch definition from Urban Dictionary API"""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.urban_api_url}{term}") as response:
                if response.status == 200:
                    data = await response.json()
                    return data
                else:
                    return None
    
    def censor_offensive_words(self, text):
        """Censor offensive words by showing first and last letters with asterisks between"""
        # List of words to censor - you can extend this list as needed
        offensive_words = [
            'fuck', 'shit', 'ass', 'bitch', 'cock', 'dick', 'cunt', 'pussy', 'nigger', 
            'nigga', 'faggot', 'retard', 'whore', 'slut', 'nazi', 'rape', 'piss', 'tits',
            'cum', 'crap', 'damn', 'homo', 'dyke', 'kike', 'spic', 'twat', 'jizz', 'dildo'
        ]
        
        # Compile regex for case-insensitive word boundary matches
        patterns = [re.compile(r'\b' + re.escape(word) + r'\b', re.IGNORECASE) for word in offensive_words]
        
        # For each offensive word pattern, replace with censored version
        for pattern in patterns:
            text = pattern.sub(lambda match: self.create_censored_word(match.group(0)), text)
        
        return text

    def create_censored_word(self, word):
        """Create a censored version of a word (e.g., 'fuck' -> 'f**k')"""
        if len(word) <= 2:
            return word  # Don't censor very short words
        
        first_letter = word[0]
        last_letter = word[-1]
        middle_length = len(word) - 2
        censored = first_letter + '*' * middle_length + last_letter
        
        # Preserve original capitalization
        if word[0].isupper():
            censored = censored[0].upper() + censored[1:]
        
        return censored
    
    def clean_text(self, text):
        """Clean text by removing bracketed words, extra whitespace, and censoring offensive words"""
        # Replace [bracketed] words - these are links in Urban Dictionary
        cleaned = re.sub(r'\[([^\]]+)\]', r'\1', text)
        # Remove excessive newlines
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        
        # Apply censoring to offensive words
        cleaned = self.censor_offensive_words(cleaned)
        
        # Trim to Discord's limits (must be under 1024 chars for embed fields)
        if len(cleaned) > 1020:
            cleaned = cleaned[:1020] + "..."
        return cleaned

    @app_commands.command(
        name="urban",
        description="Look up a word or phrase on Urban Dictionary"
    )
    async def urban(self, interaction: discord.Interaction, term: str):
        """Search for a term on Urban Dictionary"""
        await interaction.response.defer()  # Defer the response since API call might take time

        try:
            data = await self.fetch_urban_definition(term)
            
            if not data or len(data['list']) == 0:
                await interaction.followup.send(f"No definitions found for **{term}**.")
                return
            
            # Sort definitions by thumbs up
            definitions = sorted(data['list'], key=lambda x: x['thumbs_up'], reverse=True)
            total_defs = len(definitions)
            
            # Use the top definition by default
            current_page = 0
            
            # Create the initial embed
            await self.send_definition_embed(interaction, definitions, current_page, total_defs)
        
        except Exception as e:
            await interaction.followup.send(f"An error occurred: {str(e)}")
    
    async def send_definition_embed(self, interaction, definitions, page_num, total_pages):
        """Create and send a nicely formatted embed for the definition"""
        definition = definitions[page_num]
        
        # Create a nice looking embed
        embed = discord.Embed(
            title=f"📚 {definition['word']}",
            url=definition['permalink'],
            color=self.color,
            timestamp=datetime.datetime.now()
        )
        
        # Add the definition
        embed.add_field(
            name="Definition",
            value=self.clean_text(definition['definition']),
            inline=False
        )
        
        # Add example if it exists
        if definition['example'] and definition['example'].strip():
            embed.add_field(
                name="Example",
                value=self.clean_text(definition['example']),
                inline=False
            )
        
        # Add the rating information
        upvotes = definition['thumbs_up']
        downvotes = definition['thumbs_down']
        embed.add_field(
            name="Rating",
            value=f"👍 {upvotes} | 👎 {downvotes}",
            inline=True
        )
        
        # Add when the definition was submitted
        submitted_date = datetime.datetime.strptime(
            definition['written_on'].split('T')[0], 
            '%Y-%m-%d'
        )
        formatted_date = submitted_date.strftime('%B %d, %Y')
        
        embed.add_field(
            name="Submitted",
            value=formatted_date,
            inline=True
        )
        
        # Add author if available
        if definition['author']:
            embed.add_field(
                name="Author",
                value=definition['author'],
                inline=True
            )
        
        # Add page information to footer
        if total_pages > 1:
            embed.set_footer(text=f"Definition {page_num + 1} of {total_pages} | Powered by Urban Dictionary")
        else:
            embed.set_footer(text="Powered by Urban Dictionary")
        
        # Create navigation buttons if there are multiple definitions
        if total_pages > 1:
            view = UrbanPaginationView(
                definitions=definitions,
                page=page_num,
                total_pages=total_pages,
                interaction=interaction,
                cog=self
            )
            await interaction.followup.send(embed=embed, view=view)
        else:
            await interaction.followup.send(embed=embed)

class UrbanPaginationView(discord.ui.View):
    """Pagination buttons for Urban Dictionary definitions"""
    
    def __init__(self, definitions, page, total_pages, interaction, cog):
        super().__init__(timeout=60)  # 60 second timeout
        self.definitions = definitions
        self.current_page = page
        self.total_pages = total_pages
        self.original_interaction = interaction
        self.cog = cog
    
    async def on_timeout(self):
        """When the view times out, remove the buttons"""
        for item in self.children:
            item.disabled = True
        
        try:
            await self.message.edit(view=self)
        except:
            pass
    
    @discord.ui.button(label="◀️ Previous", style=discord.ButtonStyle.secondary)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to the previous definition"""
        await interaction.response.defer()
        self.current_page = (self.current_page - 1) % self.total_pages
        
        embed = await self.update_embed()
        await interaction.message.edit(embed=embed, view=self)
    
    @discord.ui.button(label="Next ▶️", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to the next definition"""
        await interaction.response.defer()
        self.current_page = (self.current_page + 1) % self.total_pages
        
        embed = await self.update_embed()
        await interaction.message.edit(embed=embed, view=self)
    
    async def update_embed(self):
        """Update the embed with the new definition"""
        definition = self.definitions[self.current_page]
        
        # Create a nice looking embed
        embed = discord.Embed(
            title=f"📚 {definition['word']}",
            url=definition['permalink'],
            color=self.cog.color,
            timestamp=datetime.datetime.now()
        )
        
        # Add the definition
        embed.add_field(
            name="Definition",
            value=self.cog.clean_text(definition['definition']),
            inline=False
        )
        
        # Add example if it exists
        if definition['example'] and definition['example'].strip():
            embed.add_field(
                name="Example",
                value=self.cog.clean_text(definition['example']),
                inline=False
            )
        
        # Add the rating information
        upvotes = definition['thumbs_up']
        downvotes = definition['thumbs_down']
        embed.add_field(
            name="Rating",
            value=f"👍 {upvotes} | 👎 {downvotes}",
            inline=True
        )
        
        # Add when the definition was submitted
        submitted_date = datetime.datetime.strptime(
            definition['written_on'].split('T')[0], 
            '%Y-%m-%d'
        )
        formatted_date = submitted_date.strftime('%B %d, %Y')
        
        embed.add_field(
            name="Submitted",
            value=formatted_date,
            inline=True
        )
        
        # Add author if available
        if definition['author']:
            embed.add_field(
                name="Author",
                value=definition['author'],
                inline=True
            )
        
        # Add page information to footer
        embed.set_footer(text=f"Definition {self.current_page + 1} of {self.total_pages} | Powered by Urban Dictionary")
        
        return embed

async def setup(bot):
    await bot.add_cog(UrbanCog(bot))
