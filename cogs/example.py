import discord
from discord.ext import commands
from discord import app_commands
import logging

logger = logging.getLogger('discord')

class ExampleCog(commands.Cog, name="Example"):  # Added name parameter
    def __init__(self, bot):
        self.bot = bot
        logger.info("ExampleCog initialized")
        
    group = app_commands.Group(name="example", description="Example commands")
        
    @app_commands.command(
        name="hello",
        description="Says hello to the user"
    )
    async def hello(self, interaction: discord.Interaction):
        logger.info(f"Hello command triggered by {interaction.user.name}")
        await interaction.response.send_message(f"Hello {interaction.user.name}!")
        
    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("ExampleCog is ready!")
        logger.info(f"Registered commands: {[command.name for command in self.bot.tree.get_commands()]}")

async def setup(bot):
    logger.info("Setting up ExampleCog...")
    await bot.add_cog(ExampleCog(bot))
    logger.info("ExampleCog setup complete")