import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import re
import logging
from typing import Optional

logger = logging.getLogger('discord')

class JokeCompetition(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_competitions = {}
        self.submissions = {}
        self.punchline_messages = {}
        self.setup_references = {}
        self.check_competitions.start()

    def get_setup_reference(self, setup):
        words = setup.strip().split(' ')
        reference = ' '.join(words[:5])
        return reference
        
    def parse_time_of_day(self, time_str):
        """Parse time string for time of day only"""
        time_formats = [
            (r'^(\d{1,2})(?::(\d{2}))?\s*(am|pm)$', '%I:%M %p'),  # 5pm, 5:30pm
            (r'^(\d{1,2})(?::(\d{2}))?$', '%H:%M'),               # 17:00, 17
        ]
        
        now = datetime.now(ZoneInfo("America/New_York"))
        
        for pattern, fmt in time_formats:
            match = re.match(pattern, time_str.lower().strip())
            if match:
                try:
                    if fmt == '%I:%M %p':
                        hour = int(match.group(1))
                        minute = int(match.group(2)) if match.group(2) else 0
                        period = match.group(3).lower()
                        
                        if period == 'pm' and hour != 12:
                            hour += 12
                        elif period == 'am' and hour == 12:
                            hour = 0
                            
                        return now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    else:
                        hour = int(match.group(1))
                        minute = int(match.group(2)) if match.group(2) else 0
                        return now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    
                except ValueError:
                    continue
                    
        raise ValueError(
            "Invalid time format. Please use:\n"
            "- Time of day: '5pm', '5:30pm', '17:00', '17'\n"
            "- Or 'now' for immediate start"
        )

    def parse_end_time(self, time_str, start_time=None):
        """Parse either a specific time or a duration in hours"""
        duration_pattern = r'^(\d+(?:\.\d+)?)\s*(?:h(?:ours?)?)?$'
        duration_match = re.match(duration_pattern, time_str.lower().strip())
        if duration_match:
            hours = float(duration_match.group(1))
            return datetime.now(ZoneInfo("America/New_York")) + timedelta(hours=hours)

        target_time = self.parse_time_of_day(time_str)
        
        if start_time and target_time <= start_time:
            target_time += timedelta(days=1)
            
        return target_time

    @app_commands.command(name='startjoke', description='Start a new joke competition')
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.describe(
        start_time='When to start the competition (e.g., "now", "5pm", "17:30")',
        end_time='When to end the competition (e.g., "6pm", "18:30", "2h")',
        setup='The setup/question part of the joke',
        image='Optional image attachment for the joke'
    )
    async def startjoke(
        self, 
        interaction: discord.Interaction, 
        start_time: str, 
        end_time: str, 
        setup: str,
        image: discord.Attachment = None
    ):
        # Check permissions
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message(
                "❌ You need the Manage Messages permission to start competitions.", 
                ephemeral=True
            )
            return

        try:
            # Handle "now" as start time
            if start_time.lower() == "now":
                start_time_dt = datetime.now(ZoneInfo("America/New_York"))
                logger.info(f"Starting competition now: {start_time_dt.strftime('%Y-%m-%d %I:%M:%S %p %Z')}")
            else:
                start_time_dt = self.parse_time_of_day(start_time)
                if start_time_dt <= datetime.now(ZoneInfo("America/New_York")):
                    start_time_dt += timedelta(days=1)
                logger.info(f"Competition start time: {start_time_dt.strftime('%Y-%m-%d %I:%M:%S %p %Z')}")

            # Parse end time
            end_time_dt = self.parse_end_time(end_time, start_time_dt)
            logger.info(f"Competition end time: {end_time_dt.strftime('%Y-%m-%d %I:%M:%S %p %Z')}")
            
            if end_time_dt <= start_time_dt:
                await interaction.response.send_message(
                    "❌ End time must be after start time!", 
                    ephemeral=True
                )
                return

            # Handle image attachment
            files = []
            if image:
                try:
                    # Validate image type if needed
                    if not image.content_type.startswith('image/'):
                        await interaction.response.send_message(
                            "❌ The attached file must be an image!", 
                            ephemeral=True
                        )
                        return
                    
                    files = [await image.to_file()]
                    logger.info(f"Image attachment processed: {image.filename}")
                except Exception as e:
                    logger.error(f"Error processing image attachment: {e}")
                    await interaction.response.send_message(
                        "❌ There was an error processing the image. Please try again.", 
                        ephemeral=True
                    )
                    return

            # Create setup reference
            setup_reference = self.get_setup_reference(setup)
            if setup_reference in self.setup_references:
                await interaction.response.send_message(
                    "❌ A joke competition with a similar setup is already active!", 
                    ephemeral=True
                )
                return

            # Acknowledge the command
            await interaction.response.send_message(
                "✅ Setting up the competition...", 
                ephemeral=True
            )

            # For immediate start, create the competition now
            if start_time.lower() == "now":
                await self.create_competition(interaction, setup, start_time_dt, end_time_dt, files)
            else:
                # For scheduled start, store the data
                self.active_competitions[f"scheduled_{interaction.channel_id}_{start_time_dt.timestamp()}"] = {
                    'setup': setup,
                    'start_time': start_time_dt,
                    'end_time': end_time_dt,
                    'channel_id': interaction.channel_id,
                    'phase': 'scheduled',
                    'setup_reference': setup_reference,
                    'files': files
                }
                
                await interaction.followup.send(
                    f"✅ Competition scheduled successfully!\n"
                    f"Setup: {setup}\n"
                    f"Start: {start_time_dt.strftime('%I:%M %p')} ET\n"
                    f"End: {end_time_dt.strftime('%I:%M %p')} ET",
                    ephemeral=True
                )

        except ValueError as e:
            await interaction.response.send_message(
                f"❌ {str(e)}", 
                ephemeral=True
            )

    @app_commands.command(name='lookup', description='Look up who submitted a specific punchline number')
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.describe(number='The punchline number to look up')
    async def lookup(self, interaction: discord.Interaction, number: int):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message(
                "❌ You need the Manage Messages permission to use this command.", 
                ephemeral=True
            )
            return

        thread_id = interaction.channel_id
        
        # Check if this is a competition thread
        if thread_id not in self.submissions:
            await interaction.response.send_message(
                "❌ This command must be used in an active competition thread!", 
                ephemeral=True
            )
            return
            
        # Check if the submission number exists
        if number not in self.submissions[thread_id]:
            await interaction.response.send_message(
                f"❌ No submission found with number {number}", 
                ephemeral=True
            )
            return
            
        # Get submission data
        submission = self.submissions[thread_id][number]
        user = self.bot.get_user(submission['user_id'])
        
        await interaction.response.send_message(
            f"Punchline #{number} was submitted by {user.mention}\nContent: {submission['punchline']}", 
            ephemeral=True
        )

    @commands.Cog.listener()
    async def on_message(self, message):
        # Ignore messages from the bot itself
        if message.author == self.bot.user:
            return

        # Check if message is in a thread
        if not isinstance(message.channel, discord.Thread):
            return

        thread_id = message.channel.id
        
        # Check if this thread is an active competition
        if thread_id not in self.active_competitions:
            return
            
        if self.active_competitions[thread_id]['phase'] != 'submission':
            await message.delete()
            return

        # Process the submission
        submission_number = len(self.submissions[thread_id]) + 1
        
        # Image handling
        files = []
        if message.attachments:
            for attachment in message.attachments:
                if attachment.content_type.startswith('image/'):
                    files.append(await attachment.to_file())
                else:
                    await message.author.send("Only image attachments are allowed.")
                    return

        # Message and image storage                
        self.submissions[thread_id][submission_number] = {
            'punchline': message.content,
            'user_id': message.author.id,
            'has_image': bool(files),
            'files': files.copy() if files else None
        }

        # Delete the original message
        try:
            await message.delete()
        except discord.Forbidden:
            logger.warning("Bot doesn't have permission to delete messages")
            pass

        # Post the anonymous submission
        content = f"**Punchline #{submission_number}:**\n{message.content}"
        if files:
            punchline_msg = await message.channel.send(content=content, files=files)
        else:
            punchline_msg = await message.channel.send(content=content)
        
        self.punchline_messages[thread_id].append({
            'message_id': punchline_msg.id,
            'submission_number': submission_number,
            'punchline': message.content,
            'has_image': bool(files)
        })
        await punchline_msg.add_reaction("⭐")
        logger.info(f"Recieved submission from {message.author.name} for thread {thread_id}")
        logger.info(f"Stored message ID {punchline_msg.id}")

    async def create_competition(self, interaction, setup, start_time, end_time, files=None):
        """Create a new competition with the given parameters"""
        channel = interaction.channel
        
        # Send setup and image together
        setup_message = f"## **Setup:** {setup}"
        if files:
            message = await channel.send(content=setup_message, files=files)
        else:
            message = await channel.send(setup_message)

        # Create thread from the setup message
        thread_name = setup
        if len(thread_name) > 100:
            thread_name = setup[:97] + "..."
        thread = await message.create_thread(name=thread_name)
        
        # Create setup reference
        setup_reference = self.get_setup_reference(setup)
        
        # Store competition data
        self.active_competitions[thread.id] = {
            'setup': setup,
            'start_time': start_time,
            'end_time': end_time,
            'message_id': message.id,
            'channel_id': channel.id,
            'phase': 'submission',
            'setup_message': setup,
            'setup_reference': setup_reference,
            'initial_message': message,
            'has_image': bool(files)
        }
        self.submissions[thread.id] = {}
        self.punchline_messages[thread.id] = []
        self.setup_references[setup_reference] = thread.id
        
        # Post submission instructions in thread
        await thread.send(
            "💡 **How to submit your punchline:**\n"
            "Simply type your punchline in this thread!\n"
            f"Competition ends: **{end_time.strftime('%I:%M %p')} ET**\n"
            "Submit as many punchlines as you like! Vote for your favorites with ⭐"
        )
        
        return thread.id

    @tasks.loop(minutes=1)
    async def check_competitions(self):
        now = datetime.now(ZoneInfo("America/New_York"))
        
        # Check for scheduled competitions that need to start
        scheduled_competitions = {k: v for k, v in self.active_competitions.items() 
                                if isinstance(k, str) and k.startswith('scheduled_')}
        
        for comp_id, data in scheduled_competitions.items():
            if now >= data['start_time']:
                # Get the channel
                channel = self.bot.get_channel(data['channel_id'])
                if channel:
                    # Create mock interaction for create_competition
                    class MockInteraction:
                        def __init__(self, channel):
                            self.channel = channel
                    
                    mock_interaction = MockInteraction(channel)
                    
                    # Create the competition
                    thread_id = await self.create_competition(
                        mock_interaction,
                        data['setup'],
                        data['start_time'],
                        data['end_time'],
                        data['files']
                    )
                    logger.info(f"Started scheduled competition in thread {thread_id}")
                
                # Remove the scheduled competition data
                del self.active_competitions[comp_id]
        
        # Check for active competitions that need to end
        active_competitions = {k: v for k, v in self.active_competitions.items() 
                             if isinstance(k, int)}
        
        for thread_id, data in active_competitions.items():
            if data['phase'] == 'submission' and now >= data['end_time']:
                await self.end_competition(thread_id)

    async def end_competition(self, thread_id):
        thread = self.bot.get_channel(thread_id)
        if not thread:
            return

        original_channel = self.bot.get_channel(self.active_competitions[thread_id]['channel_id'])
        if not original_channel:
            return

        self.active_competitions[thread_id]['phase'] = 'voting'

        # Safely handle setup_reference cleanup
        setup_ref = self.active_competitions[thread_id].get('setup_reference')
        if setup_ref and setup_ref in self.setup_references:
            del self.setup_references[setup_ref]

        await thread.send("🎉 **Voting has ended!** Tallying results...")
        logger.info("Starting vote count...")

        setup = self.active_competitions[thread_id]['setup_message']

        vote_data = []
        for msg_data in self.punchline_messages[thread_id]:
            try:
                msg = await thread.fetch_message(msg_data['message_id'])
                logger.info(f"Checking message: {msg.content}")
                for reaction in msg.reactions:
                    logger.info(f"Found reaction: {reaction.emoji} with {reaction.count} votes")
                    if str(reaction.emoji) == "⭐":
                        vote_data.append({
                            'message': msg,
                            'votes': reaction.count,
                            'punchline': msg_data['punchline'],
                            'submission_number': msg_data['submission_number']
                        })
                        logger.info(f"Added to vote data with {reaction.count} votes")
            except discord.NotFound:
                logger.warning(f"Message {msg_data['message_id']} not found")
                continue

        logger.info(f"Total vote entries: {len(vote_data)}")
        
        vote_data.sort(key=lambda x: x['votes'], reverse=True)

        winner_text = "## 🏆 **WINNERS** 🏆\n\n"
        medals = ["🥇", "🥈", "🥉"]

        if vote_data:
            logger.info("Processing winners...")
            for i, entry in enumerate(vote_data[:3]):
                if i < len(medals):
                    submission_data = self.submissions[thread_id][entry['submission_number']]
                    author = self.bot.get_user(submission_data['user_id'])
                    
                    winner_text += (
                        f"### {medals[i]} **{entry['votes']} votes**\n"
                        f"{submission_data['punchline']}\n"
                        f"by {author.mention}\n\n"
                    )

                    # If the winning submission had an image, post it
                    if submission_data.get('has_image') and submission_data.get('files'):
                        try:
                            # Get the original message
                            original_msg = await thread.fetch_message(entry['message'].id)
                            if original_msg.attachments:
                                # Refetch the files
                                new_files = [await attachment.to_file() for attachment in original_msg.attachments]
                                await original_channel.send(
                                    f"### {medals[i]}",
                                    files=new_files
                                )
                        except Exception as e:
                            logger.error(f"Error sending winner image: {e}")
                    
                    logger.info(f"Added winner: {entry['votes']} votes")
        else:
            logger.info("No vote data found")
            winner_text += "### No votes were cast in this competition!\n\n"

        # If there's an image, we want to keep the original message but update it
        initial_message = self.active_competitions[thread_id]['initial_message']
        if not self.active_competitions[thread_id].get('has_image'):
            try:
                await initial_message.delete()
            except (discord.NotFound, discord.Forbidden) as e:
                logger.warning(f"Couldn't delete message: {e}")
                pass
        
        # Send thread message
        await thread.send(f"{winner_text}Thanks everyone for participating!")
        
        # Send channel messages - use the initial message if it has an image
        footer_text = f"\n\nSee all submissions in the [joke thread]({thread.jump_url})\n\nThanks everyone for participating!"
        
        if self.active_competitions[thread_id].get('has_image'):
            try:
                initial_content = initial_message.content
                initial_attachments = [await attachment.to_file() for attachment in initial_message.attachments]
                await initial_message.delete()
                await original_channel.send(
                    content=f"{initial_content}\n\n{winner_text}{footer_text}",
                    files=initial_attachments
                )
            except Exception as e:
                logger.error(f"Error reposting with image: {e}")
                await original_channel.send(winner_text + footer_text)
        else:
            await original_channel.send(f"**Setup:** {setup}\n\n{winner_text}{footer_text}")
        
        logger.info(f"Competition ended for thread {thread_id}")
        
        del self.active_competitions[thread_id]
        del self.submissions[thread_id]
        del self.punchline_messages[thread_id]
        pass

    @check_competitions.before_loop
    async def before_check_competitions(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(JokeCompetition(bot))