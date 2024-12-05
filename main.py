import discord
from discord.ext import commands
import asyncio
import logging
from cogs.joke_competition import JokeCompetition
from cogs.timer import TimerCog
from cogs.basic import BasicCog
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('discord')

class ResilientBot(commands.Bot):
    async def setup_hook(self):
        # Add the cogs 
        await self.add_cog(JokeCompetition(self))
        await self.add_cog(TimerCog(self))
        await self.add_cog(BasicCog(self))

        # Force sync the commands with Discord
        logger.info("Syncing commands with Discord...")
        try:
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} commands")
        except Exception as e:
            logger.error(f"Error syncing commands: {e}")
        
    async def start(self, *args, **kwargs):
        while True:
            try:
                await super().start(*args, **kwargs)
            except discord.ConnectionClosed:
                logger.warning("Discord connection closed. Reconnecting...")
                await asyncio.sleep(5)
            except discord.GatewayNotFound:
                logger.warning("Discord gateway not found. Reconnecting...")
                await asyncio.sleep(5)
            except discord.HTTPException as e:
                logger.warning(f"HTTP Exception: {e}. Reconnecting...")
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Unexpected error: {e}. Reconnecting...")
                await asyncio.sleep(5)

# Set up intents
intents = discord.Intents.all()

# Initialize bot with application ID
bot = ResilientBot(
    command_prefix='!',  # Keeping prefix for backwards compatibility
    intents=intents,
)

@bot.event
async def on_ready():
    logger.info(f'{bot.user} has connected to Discord!')
    # Set up a custom status showing slash command usage
    activity = discord.Activity(
        type=discord.ActivityType.listening,
        name="for laughter | /startjoke"
    )
    await bot.change_presence(activity=activity)

@bot.command()
@commands.is_owner()
async def sync(ctx):
    logger.info("Manual sync initiated...")
    try:
        synced = await bot.tree.sync()
        await ctx.send(f"Synced {len(synced)} commands")
        logger.info(f"Manually synced {len(synced)} commands")
        # Print out all registered commands
        commands = [command.name for command in bot.tree.get_commands()]
        logger.info(f"Currently registered commands: {commands}")
    except Exception as e:
        logger.error(f"Error syncing commands: {e}")
        await ctx.send(f"Error syncing commands: {e}")

@bot.event
async def on_disconnect():
    logger.warning('Bot disconnected from Discord')

@bot.event
async def on_connect():
    logger.info('Bot reconnected to Discord')

try:
    bot.run(os.getenv('DISCORD_TOKEN'))
except KeyboardInterrupt:
    logger.info("Bot shutdown by user")
except Exception as e:
    logger.error(f"Fatal error: {e}")