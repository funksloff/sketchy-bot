import discord
from discord.ext import commands
from discord import app_commands
import logging

logger = logging.getLogger('discord')

class BasicCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        logger.info("BasicCog initialized")

    @app_commands.command(name="ping", description="Replies with pong!")
    async def ping(self, interaction: discord.Interaction):
        await interaction.response.send_message("Pong!")

async def setup(bot):
    await bot.add_cog(BasicCog(bot))