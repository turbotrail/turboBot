import discord
from discord.ext import commands, tasks
import asyncio
import os
import yt_dlp as youtube_dl
from datetime import datetime, timedelta
import shutil
import time
from dotenv import load_dotenv
load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN")  # Secure token handling
PREFIX = "!"
intents = discord.Intents.all()
bot = commands.Bot(command_prefix=commands.when_mentioned_or(PREFIX), intents=intents)

# Create a downloads directory if it doesn't exist
DOWNLOAD_DIR = "music_downloads"
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# File cleanup settings
MAX_CACHE_SIZE_MB = 500  # Maximum size for the downloads folder (500 MB)
MAX_FILE_AGE_DAYS = 7    # Files older than this will be deleted
CLEANUP_INTERVAL = 60    # Check for cleanup every 60 minutes

# Global variable to store the rules message ID
rules_message_id = None

# Audio quality settings per guild
audio_quality_settings = {}
# Default quality is medium
DEFAULT_QUALITY = "medium"

# Store information about currently playing songs
current_songs = {}

# Function to clean up old downloaded files
def cleanup_old_files():
    """Delete old downloaded files to save disk space"""
    # Skip if directory doesn't exist
    if not os.path.exists(DOWNLOAD_DIR):
        return
        
    try:
        # Get all files with their last modified time
        files = []
        total_size = 0
        
        for filename in os.listdir(DOWNLOAD_DIR):
            file_path = os.path.join(DOWNLOAD_DIR, filename)
            if os.path.isfile(file_path):
                # Get file stats
                file_size = os.path.getsize(file_path)
                mod_time = os.path.getmtime(file_path)
                
                # Skip files that are currently being played
                if any(song.get('file') == file_path for song in current_songs.values()):
                    continue
                    
                files.append((file_path, mod_time, file_size))
                total_size += file_size
        
        # Sort files by modification time (oldest first)
        files.sort(key=lambda x: x[1])
        
        # Remove files older than MAX_FILE_AGE_DAYS
        cutoff_time = time.time() - (MAX_FILE_AGE_DAYS * 86400)
        for file_path, mod_time, _ in files[:]:
            if mod_time < cutoff_time:
                try:
                    os.remove(file_path)
                    files.remove((file_path, mod_time, _))
                    print(f"Deleted old file: {file_path}")
                except:
                    pass
        
        # If we're still over the size limit, delete oldest files until we're under the limit
        max_size_bytes = MAX_CACHE_SIZE_MB * 1024 * 1024
        if total_size > max_size_bytes:
            for file_path, _, file_size in files:
                if total_size <= max_size_bytes:
                    break
                try:
                    os.remove(file_path)
                    total_size -= file_size
                    print(f"Deleted file due to cache size limit: {file_path}")
                except:
                    pass
    except Exception as e:
        print(f"Error during cleanup: {e}")

@tasks.loop(minutes=CLEANUP_INTERVAL)
async def cleanup_task():
    """Background task to clean up old files"""
    cleanup_old_files()

@bot.event
async def on_ready():
    print(f"{bot.user} is online and ready!")
    cleanup_task.start()

@bot.command()
@commands.has_permissions(administrator=True)
async def cleanup(ctx):
    """Manually trigger audio cache cleanup"""
    await ctx.send("🧹 Cleaning up audio cache...")
    cleanup_old_files()
    
    # Calculate current cache size
    total_size = sum(os.path.getsize(os.path.join(DOWNLOAD_DIR, f)) 
                     for f in os.listdir(DOWNLOAD_DIR) 
                     if os.path.isfile(os.path.join(DOWNLOAD_DIR, f)))
    
    total_size_mb = total_size / (1024 * 1024)
    await ctx.send(f"✅ Cleanup complete! Current cache size: {total_size_mb:.2f} MB")

# Function to get FFmpeg options based on quality setting
def get_ffmpeg_options(guild_id):
    quality = audio_quality_settings.get(guild_id, DEFAULT_QUALITY)
    
    # Simple options that prioritize stability over quality
    return {
        'options': '-vn -af "volume=0.8"'
    }

@bot.command()
async def quality(ctx, setting=None):
    """Set audio quality (low, medium, high) or show current setting"""
    guild_id = ctx.guild.id
    
    if setting is None:
        current = audio_quality_settings.get(guild_id, DEFAULT_QUALITY)
        await ctx.send(f"Current audio quality: **{current}**\nAvailable options: low, medium, high")
        return
        
    setting = setting.lower()
    if setting not in ["low", "medium", "high"]:
        await ctx.send("Invalid quality setting. Use 'low', 'medium', or 'high'")
        return
        
    audio_quality_settings[guild_id] = setting
    await ctx.send(f"Audio quality set to: **{setting}**")
    
    if ctx.voice_client and ctx.voice_client.is_playing():
        await ctx.send("This will take effect on the next song.")

# Admin Commands
@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason=None):
    await member.kick(reason=reason)
    await ctx.send(f"{member.name} has been kicked.")

@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason=None):
    await member.ban(reason=reason)
    await ctx.send(f"{member.name} has been banned.")

@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int):
    await ctx.channel.purge(limit=amount + 1)
    await ctx.send(f"Deleted {amount} messages.", delete_after=3)

# Music Queue System (Multi-Guild Support)
music_queues = {}

@bot.command()
async def join(ctx):
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        await channel.connect()
        await ctx.send(f"Joined {channel}.")
    else:
        await ctx.send("You must be in a voice channel.")

@bot.command()
async def leave(ctx):
    if ctx.voice_client:
        guild_id = ctx.guild.id
        # Clear the queue when leaving
        if guild_id in music_queues:
            music_queues[guild_id] = []
        
        # Stop any playing audio
        if ctx.voice_client.is_playing():
            ctx.voice_client.stop()
        
        await ctx.guild.voice_client.disconnect()
        await ctx.send("Disconnected from voice channel.")
    else:
        await ctx.send("I'm not in a voice channel.")

@bot.command()
async def play(ctx, url: str):
    guild_id = ctx.guild.id
    if guild_id not in music_queues:
        music_queues[guild_id] = []
    
    # Join voice channel if not already in one
    if not ctx.voice_client:
        if ctx.author.voice:
            await ctx.author.voice.channel.connect()
        else:
            await ctx.send("You must be in a voice channel.")
            return
    
    async with ctx.typing():
        try:
            message = await ctx.send("⏳ Processing song...")
            music_queues[guild_id].append(url)
            
            if not ctx.voice_client.is_playing():
                await play_next(ctx, guild_id)
            else:
                await message.edit(content="✅ Added to queue!")
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)}")

async def download_audio(url, guild_id):
    """Download the audio file and return the path"""
    try:
        # Clean filename to avoid issues
        clean_id = ''.join(c for c in url if c.isalnum())[-10:]
        file_path = f"{DOWNLOAD_DIR}/{guild_id}_{clean_id}.mp3"
        temp_path = f"{DOWNLOAD_DIR}/temp_{guild_id}_{clean_id}.%(ext)s"
        
        # Check if we've already downloaded this file
        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            return file_path, None
        
        # Download options with better error handling
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': temp_path,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'noplaylist': True,
            'no_warnings': False,
            'ignoreerrors': False,
            'quiet': False,
            'verbose': True,
            'extract_flat': False,
            'force_generic_extractor': False,
            'cachedir': False,
            'nocheckcertificate': True
        }
        
        # Download the file
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'Unknown Title')
            
            # Verify the file was created (could be with a different extension)
            downloaded_file = None
            for filename in os.listdir(DOWNLOAD_DIR):
                if filename.startswith(f"temp_{guild_id}_{clean_id}") and os.path.isfile(os.path.join(DOWNLOAD_DIR, filename)):
                    downloaded_file = os.path.join(DOWNLOAD_DIR, filename)
                    break
            
            if downloaded_file and os.path.exists(downloaded_file):
                # Rename/move to our expected mp3 path
                shutil.move(downloaded_file, file_path)
                return file_path, title
            else:
                # If downloaded file not found, try to use direct URL for streaming
                return None, title
                
    except Exception as e:
        print(f"Download error: {str(e)}")
        # Return None to indicate failure
        return None, None

async def play_next(ctx, guild_id):
    if guild_id in music_queues and len(music_queues[guild_id]) > 0:
        url = music_queues[guild_id].pop(0)
        
        try:
            # Send a "processing" message
            processing_msg = await ctx.send("⏳ Downloading audio for better playback quality...")
            
            # Download the file instead of streaming
            file_path, title = await asyncio.get_event_loop().run_in_executor(
                None, lambda: asyncio.run(download_audio(url, guild_id))
            )
            
            if not title:
                # If download failed, try to get title at least
                with youtube_dl.YoutubeDL({'quiet': True}) as ydl:
                    try:
                        info = ydl.extract_info(url, download=False)
                        title = info.get('title', 'Unknown Title')
                    except:
                        title = "Unknown Track"
            
            # Store current song info
            current_songs[guild_id] = {'title': title, 'url': url, 'file': file_path}
            
            # If we have a file path, play from file, otherwise try direct URL streaming
            if file_path and os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                # Play from file
                source = discord.PCMVolumeTransformer(
                    discord.FFmpegPCMAudio(file_path, **get_ffmpeg_options(guild_id))
                )
            else:
                # Fallback to streaming
                await processing_msg.edit(content="⚠️ Download failed, falling back to streaming mode...")
                
                ydl_opts = {
                    'format': 'bestaudio/best',
                    'noplaylist': True,
                    'quiet': True
                }
                
                with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    stream_url = info['url']
                
                source = discord.PCMVolumeTransformer(
                    discord.FFmpegPCMAudio(
                        stream_url, 
                        **{'before_options': '-reconnect 1 -reconnect_streamed 1', 'options': '-vn'}
                    )
                )
            
            source.volume = 0.5  # Set a safe default volume
            
            # Play the audio
            ctx.voice_client.play(
                source,
                after=lambda e: asyncio.run_coroutine_threadsafe(
                    handle_song_complete(ctx, guild_id, e), bot.loop
                )
            )
            
            await processing_msg.edit(content=f"🎵 Now playing: **{title}**")
            
        except Exception as e:
            await ctx.send(f"❌ Error playing track: {str(e)}")
            # Try to play next song
            await play_next(ctx, guild_id)

async def handle_song_complete(ctx, guild_id, error):
    """Handle when a song completes playing"""
    if error:
        print(f"Player error: {error}")
    
    # Mark the song as no longer being played
    if guild_id in current_songs:
        del current_songs[guild_id]
    
    # Play the next song if available
    if guild_id in music_queues and len(music_queues[guild_id]) > 0:
        await play_next(ctx, guild_id)

@bot.command()
async def stop(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        guild_id = ctx.guild.id
        if guild_id in music_queues:
            music_queues[guild_id] = []
        await ctx.send("🛑 Music stopped and queue cleared.")
    else:
        await ctx.send("No music is playing.")

@bot.command()
async def skip(ctx):
    """Skip the currently playing song"""
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("⏭️ Skipped to next song")
    else:
        await ctx.send("No music is playing.")

@bot.command()
async def queue(ctx):
    """Show the current queue"""
    guild_id = ctx.guild.id
    if guild_id not in music_queues or len(music_queues[guild_id]) == 0:
        if guild_id in current_songs:
            await ctx.send(f"🎵 Currently playing: **{current_songs[guild_id]['title']}**\n📋 Queue is empty.")
        else:
            await ctx.send("📋 Queue is empty.")
        return
    
    # Format the queue
    queue_list = "📋 **Queue:**\n"
    if guild_id in current_songs:
        queue_list += f"▶️ Now playing: **{current_songs[guild_id]['title']}**\n\n"
    
    for i, url in enumerate(music_queues[guild_id]):
        with youtube_dl.YoutubeDL({'quiet': True}) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
                title = info.get('title', 'Unknown Title')
                queue_list += f"{i+1}. {title}\n"
            except:
                queue_list += f"{i+1}. {url}\n"
    
    await ctx.send(queue_list)

@bot.command()
async def volume(ctx, volume: int = None):
    """Set the player volume (0-100)"""
    if not ctx.voice_client or not ctx.voice_client.source:
        await ctx.send("Nothing is playing right now.")
        return
    
    if volume is None:
        current_vol = int(ctx.voice_client.source.volume * 100)
        await ctx.send(f"🔊 Current volume: **{current_vol}%**")
        return
    
    if not 0 <= volume <= 100:
        await ctx.send("⚠️ Volume must be between 0 and 100")
        return
    
    ctx.voice_client.source.volume = volume / 100
    await ctx.send(f"🔊 Volume set to **{volume}%**")

@bot.event
async def on_voice_state_update(member, before, after):
    """Clean up when the bot is disconnected from a voice channel"""
    if member.id == bot.user.id and before.channel and not after.channel:
        # Bot was disconnected
        guild_id = before.channel.guild.id
        if guild_id in music_queues:
            music_queues[guild_id] = []
        if guild_id in current_songs:
            del current_songs[guild_id]

# Announcement System with Embed Support
@bot.command()
@commands.has_permissions(manage_channels=True)
async def announce(ctx, channel: discord.TextChannel, *, message):
    embed = discord.Embed(title="📢 Announcement", description=message, color=discord.Color.blue())
    await channel.send(embed=embed)
    await ctx.send("Announcement sent!")

# Configurable Reaction Role System (Multi-Guild Support)
reaction_roles = {}

@bot.command()
async def add_reaction_role(ctx, message_id: int, emoji: str, role: discord.Role):
    if ctx.guild.id not in reaction_roles:
        reaction_roles[ctx.guild.id] = {}
    reaction_roles[ctx.guild.id][(message_id, emoji)] = role.id
    await ctx.send("Reaction role added.")

@bot.event
async def on_raw_reaction_add(payload):
    if payload.guild_id is None:
        return  # Skip DMs

    guild = bot.get_guild(payload.guild_id)

    # Check if this reaction is for the rules message in the #rules channel
    if rules_message_id and payload.message_id == rules_message_id:
        if str(payload.emoji) == "✅":  # Only verify if the reaction is a checkmark
            role = discord.utils.get(guild.roles, name="Verified")
            if not role:
                # Create the Verified role if it doesn't exist
                role = await guild.create_role(name="Verified", reason="Auto-created Verified role for rules reaction.")
            member = guild.get_member(payload.user_id)
            if member:
                await member.add_roles(role)
                try:
                    await member.send(f"You've been verified with the **{role.name}** role!")
                except discord.Forbidden:
                    pass
            return

    # Existing reaction role handling
    if guild.id in reaction_roles:
        role_id = reaction_roles[guild.id].get((payload.message_id, str(payload.emoji)))
        if role_id:
            role = guild.get_role(role_id)
            member = guild.get_member(payload.user_id)
            if role and member:
                await member.add_roles(role)
                try:
                    await member.send(f"You've been given the **{role.name}** role!")
                except discord.Forbidden:
                    pass

# Verification System (Multi-Guild Support)
@bot.event
async def on_member_join(member):
    verification_channel = discord.utils.get(member.guild.channels, name="verification")
    if verification_channel:
        await verification_channel.send(f"Welcome {member.mention}, please type !verify to gain access.")

@bot.command()
async def verify(ctx):
    role = discord.utils.get(ctx.guild.roles, name="Founder")
    if role:
        await ctx.author.add_roles(role)
        await ctx.send(f"{ctx.author.mention} has been verified!")

# Command to post the rules message in the #rules channel
@bot.command()
@commands.has_permissions(manage_channels=True)
async def post_rules(ctx):
    global rules_message_id
    # Ensure this command is run in the rules channel
    if ctx.channel.name != "rules":
        await ctx.send("Please run this command in the #rules channel.")
        return
    embed = discord.Embed(
        title="Server Rules",
        description="Please read and react with ✅ to verify that you accept the rules \n"+
        "Be Respectful: Treat every member with professionalism and courtesy.\n"+
        "Maintain Confidentiality: Keep discussions and shared ideas within the community.\n"+
        "Stay On Topic: Focus conversations on entrepreneurship, startups, and innovation.\n"+
        "No Spam or Self-Promotion: Avoid excessive self-promotion and unsolicited advertising.\n"+
        "Follow Discord Guidelines: Adhere to Discord's community standards at all times.\n"+
        "Constructive Collaboration: Share insights, provide helpful feedback, and foster a positive environment\n",
        color=discord.Color.green()
    )
    message = await ctx.send(embed=embed)
    await message.add_reaction("✅")
    rules_message_id = message.id
    await ctx.send("Rules message posted and verification setup complete.")

# Help Command
@bot.command()
async def info(ctx):
    embed = discord.Embed(title="🛠 Proton Bot Commands", description="Here is a list of available commands:", color=discord.Color.green())
    embed.add_field(name="🔹 Admin Commands", value="!kick, !ban, !clear, !cleanup", inline=False)
    embed.add_field(name="🎵 Music Commands", value="!join, !leave, !play [URL], !skip, !stop, !queue, !volume [0-100]", inline=False)
    embed.add_field(name="📢 Announcement", value="!announce #channel [message]", inline=False)
    embed.add_field(name="🔘 Reaction Roles", value="!add_reaction_role [message_id] [emoji] @role", inline=False)
    embed.add_field(name="✅ Verification", value="!verify or react to the rules message", inline=False)
    embed.add_field(name="ℹ️ User Info", value="!userinfo @user", inline=False)
    await ctx.send(embed=embed)

# General Utilities
@bot.command()
async def userinfo(ctx, member: discord.Member = None):
    member = member or ctx.author
    embed = discord.Embed(title=f"User Info - {member.name}", timestamp=datetime.utcnow())
    embed.add_field(name="ID", value=member.id)
    embed.add_field(name="Joined", value=member.joined_at.strftime("%Y-%m-%d %H:%M:%S"))
    embed.add_field(name="Roles", value=", ".join([r.name for r in member.roles if r.name != "@everyone"]))
    embed.set_thumbnail(url=member.avatar.url)
    await ctx.send(embed=embed)

bot.run(TOKEN)
