import discord
from discord.ext import commands, tasks
import asyncio
import os
import yt_dlp as youtube_dl
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN")  # Secure token handling
PREFIX = "!"
intents = discord.Intents.all()
bot = commands.Bot(command_prefix=commands.when_mentioned_or(PREFIX), intents=intents)

# Global variable to store the rules message ID
rules_message_id = None

# Audio quality settings per guild
audio_quality_settings = {}
# Default quality is medium
DEFAULT_QUALITY = "medium"

# Function to get FFmpeg options based on quality setting
def get_ffmpeg_options(guild_id):
    quality = audio_quality_settings.get(guild_id, DEFAULT_QUALITY)
    
    base_options = {
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    }
    
    if quality == "low":
        base_options['options'] = '-vn -af "volume=0.7"'
    elif quality == "high":
        base_options['options'] = '-vn -af "volume=0.9"'
    else:  # medium (default)
        base_options['options'] = '-vn -af "volume=0.8"'
        
    return base_options

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
        await ctx.guild.voice_client.disconnect()
        await ctx.send("Disconnected from voice channel.")
    else:
        await ctx.send("I'm not in a voice channel.")

@bot.command()
async def play(ctx, url: str):
    guild_id = ctx.guild.id
    if guild_id not in music_queues:
        music_queues[guild_id] = []
    
    music_queues[guild_id].append(url)
    if not ctx.voice_client.is_playing():
        await play_next(ctx, guild_id)
    else:
        await ctx.send("Added to queue.")

async def play_next(ctx, guild_id):
    if guild_id in music_queues and len(music_queues[guild_id]) > 0:
        url = music_queues[guild_id].pop(0)
        FFMPEG_OPTIONS = get_ffmpeg_options(guild_id)
        ydl_opts = {
            'format': 'bestaudio/best',
            'noplaylist': True,
            'nocheckcertificate': True,
            'ignoreerrors': False,
            'logtostderr': False,
            'quiet': True,
            'no_warnings': True,
            'default_search': 'auto',
            'source_address': '0.0.0.0'
        }
        
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            url2 = info['url']
        
        source = await discord.FFmpegOpusAudio.from_probe(url2, **FFMPEG_OPTIONS)
        ctx.voice_client.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx, guild_id), bot.loop))
        await ctx.send(f"Now playing: {info['title']}")

@bot.command()
async def stop(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("Music stopped.")
    else:
        await ctx.send("No music is playing.")

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
    embed.add_field(name="🔹 Admin Commands", value="!kick, !ban, !clear", inline=False)
    embed.add_field(name="🎵 Music Commands", value="!join, !leave, !play [URL], !quality [low/medium/high]", inline=False)
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
