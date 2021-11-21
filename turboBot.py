import discord
import os

client = discord.Client()

@client.event
async def on_ready():
    print('We have logged in as {0.user}'.format(client))

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if message.content.startswith('$hello'):
        await message.channel.send('Hello Jeyaprakash')
    if message.content.startswith('$git'):
        await message.channel.send('https://github.com/turbotrail')
client.run(os.getenv('DISCTOKEN'))
