import discord
from discord.ext import commands
from discord import app_commands
import logging
import asyncio
from typing import Dict, Tuple
from datetime import datetime

logger = logging.getLogger('discord')

class TimerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_timers: Dict[int, Tuple[float, asyncio.Task, str]] = {}
        logger.info("TimerCog initialized")

    def get_time_remaining(self, channel_id: int) -> int:
        if channel_id in self.active_timers:
            end_time, _, _ = self.active_timers[channel_id]
            remaining = end_time - asyncio.get_event_loop().time()
            return max(0, int(remaining / 60))
        return 0

    def find_discussion_channel(self, guild: discord.Guild) -> discord.TextChannel:
        """Find the script-discussions channel in the guild."""
        for channel in guild.text_channels:
            if channel.name.lower() in ['script-discussions', 'script-discussion', 'scripts']:
                return channel
        return None

    async def run_timer(self, channel_id: int, channel: discord.TextChannel, minutes: int, name: str):
        try:
            await asyncio.sleep(minutes * 60)
            try:
                discussion_channel = self.find_discussion_channel(channel.guild)
                if not discussion_channel:
                    await channel.send(content="Time is up, great job!", tts=True)
                    await channel.send("Note: Couldn't find a #script-discussions channel to create the thread in. Please create one!")
                    return

                # Create message and thread in discussion channel
                msg = await discussion_channel.send(f"Script reading session completed for {name}")
                thread_name = f"{name}'s Script Discussion"
                
                if discussion_channel.permissions_for(channel.guild.me).create_public_threads:
                    thread = await msg.create_thread(
                        name=thread_name,
                        reason=f"Automatic thread for {name}'s script discussion"
                    )
                    original_channel_name = getattr(channel, 'name', 'voice channel')
                    await thread.send(
                        f"This thread has been created for additional notes, joke pitches, or continued discussion "
                        f"about {name}'s script from today's writer's room. Feel free to share your thoughts!"
                    )
                    
                    # Send time's up message with thread link
                    await channel.send(content="Time is up, great job!", tts=True)
                    await channel.send(
                        f"💡 Continue the discussion in the new thread: {thread.jump_url}\n"
                        f"Share any additional notes, joke pitches, and feedback there!"
                    )
                else:
                    await channel.send(content="Time is up, great job!", tts=True)
                    logger.warning(f"Missing thread creation permission in channel {discussion_channel.id}")
                    await channel.send("Note: I couldn't create a discussion thread because I don't have the 'Create Public Threads' permission.")
                    
            except discord.Forbidden:
                logger.error(f"Missing permissions in channel {channel_id}")
            except discord.NotFound:
                logger.error(f"Channel {channel_id} not found")
            except Exception as e:
                logger.error(f"Error in timer completion: {e}")
                
        except asyncio.CancelledError:
            try:
                await channel.send("Timer has been cancelled.")
            except (discord.Forbidden, discord.NotFound):
                logger.info(f"Timer cancelled in channel {channel_id} but couldn't send notification")
            except Exception as e:
                logger.error(f"Error sending timer cancellation message: {e}")
                
        finally:
            if channel_id in self.active_timers:
                del self.active_timers[channel_id]
                logger.info(f"Timer cleaned up for channel {channel_id}")

    @app_commands.command(
        name="timer", description="Start a timer for script reading")
    @app_commands.default_permissions(send_messages=True)
    @app_commands.describe(
        minutes="Number of minutes to set the timer for",
        name="Name of the person whose script is being read"
    )
    async def timer(self, interaction: discord.Interaction, minutes: int, name: str):
        channel_id = interaction.channel_id
        
        # Find the discussion channel first
        discussion_channel = self.find_discussion_channel(interaction.guild)
        if not discussion_channel:
            await interaction.response.send_message(
                "Please create a text channel named 'script-discussions' first!", 
                ephemeral=True
            )
            return
            
        # Check permissions in both channels
        channel_perms = interaction.channel.permissions_for(interaction.guild.me)
        discussion_perms = discussion_channel.permissions_for(interaction.guild.me)
        missing_perms = []
        
        if not channel_perms.send_messages:
            missing_perms.append("Send Messages (in current channel)")
        if not channel_perms.send_tts_messages:
            missing_perms.append("Send TTS Messages (in current channel)")
        if not discussion_perms.send_messages:
            missing_perms.append("Send Messages (in #script-discussions)")
        if not discussion_perms.create_public_threads:
            missing_perms.append("Create Public Threads (in #script-discussions)")
            
        if missing_perms:
            await interaction.response.send_message(
                f"I'm missing the following required permissions: {', '.join(missing_perms)}", 
                ephemeral=True
            )
            return
            
        if channel_id in self.active_timers:
            remaining = self.get_time_remaining(channel_id)
            await interaction.response.send_message(
                f"There's already an active timer in this channel with {remaining} minutes remaining! "
                f"Use `/cancel_timer` to cancel it first.",
                ephemeral=True
            )
            return

        if minutes <= 0:
            await interaction.response.send_message("Please set a time greater than 0 minutes!", ephemeral=True)
            return
            
        if minutes > 60:
            await interaction.response.send_message("Please set a time of 60 minutes or less!", ephemeral=True)
            return
            
        end_time = asyncio.get_event_loop().time() + (minutes * 60)
        timer_task = asyncio.create_task(self.run_timer(channel_id, interaction.channel, minutes, name))
        self.active_timers[channel_id] = (end_time, timer_task, name)
            
        await interaction.response.send_message(f"Timer started for {minutes} minutes to read {name}'s script!")

    @app_commands.command(
        name="cancel_timer",
        description="Cancel the current timer in this channel"
    )
    async def cancel_timer(self, interaction: discord.Interaction):
        channel_id = interaction.channel_id
        
        if channel_id not in self.active_timers:
            await interaction.response.send_message("There's no active timer in this channel!", ephemeral=True)
            return
            
        _, task, name = self.active_timers[channel_id]
        task.cancel()
        
        await interaction.response.send_message(f"Timer for {name}'s script has been cancelled!")

    @app_commands.command(
        name="check_timer",
        description="Check how much time is left on the current timer"
    )
    async def check_timer(self, interaction: discord.Interaction):
        channel_id = interaction.channel_id
        
        if channel_id not in self.active_timers:
            await interaction.response.send_message("There's no active timer in this channel!", ephemeral=True)
            return
            
        remaining = self.get_time_remaining(channel_id)
        _, _, name = self.active_timers[channel_id]
        await interaction.response.send_message(f"There are {remaining} minutes remaining on the timer for {name}'s script.")

async def setup(bot):
    await bot.add_cog(TimerCog(bot))