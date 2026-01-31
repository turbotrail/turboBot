[![Deploy Discord Bot](https://github.com/turbotrail/turboBot/actions/workflows/deploy.yml/badge.svg)](https://github.com/turbotrail/turboBot/actions/workflows/deploy.yml)

# TurboBot (Proton)

TurboBot (also known as Proton) is a feature-rich, self-hosted Discord bot designed to run on a Raspberry Pi 5. It combines high-quality music playback, AI capabilities powered by Ollama, and essential community management tools into a single, efficient package.

## Features

### 🎵 Level-Up Music System
- **High Quality Audio**: Downloads tracks for stable, high-quality playback (avoids buffering issues).
- **Format Support**: Plays music from YouTube URLs and search terms.
- **Queue Management**: Add songs, skip, stop, and view the current queue.
- **Volume Control**: Adjust playback volume on the fly.
- **Smart Caching**: Automatically manages disk space by cleaning up old downloaded files.

### 🤖 AI Assistant
- **Context-Aware Chat**: Powered by **Ollama** and **LangChain**.
- **Specialized Channels**: engaged in conversation in designated channels (e.g., `ai-lounge`).
- **Web Access**: Can search the web for real-time information (via `!askollama` / LangChain agent).
- **Persona**: Friendly "Proton" personality, confident and helpful.

### 🛡️ Moderation & Admin
- **User Management**: `!kick` and `!ban` commands.
- **Chat Management**: `!clear` messages.
- **Cache Control**: Manual and automatic cleanup of the music download cache.
- **Announcement System**: distinct embed-based announcements.

### 👥 Community Tools
- **Reaction Roles**: Self-assignable roles via reactions.
- **Verification System**: Rules acceptance flow with a "Verified" role.
- **User Info**: Get details about server members.
- **Reminders**: Set personal reminders.

## Prerequisites

- **Python 3.8+**
- **FFmpeg**: Required for audio processing.
  - Linux (Debian/Ubuntu): `sudo apt install ffmpeg`
  - macOS: `brew install ffmpeg`
  - Windows: Download and add to PATH.
- **Ollama**: Required for AI features.
  - Install from [ollama.com](https://ollama.com).
  - Pull the model specified in your config (default: `gemma3:4b`).

## Installation

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/turbotrail/turboBot.git
    cd turboBot
    ```

2.  **Install Python dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

## Configuration

Create a `.env` file in the root directory with the following variables:

```ini
# Discord Configuration
DISCORD_BOT_TOKEN=your_discord_bot_token_here

# Ollama AI Configuration
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gemma3:4b
OLLAMA_ALLOWED_ROLE=AI  # Role required to use AI commands (optional)
OLLAMA_REQUIRE_MANAGE_MESSAGES=true
OLLAMA_MAX_PROMPT_LENGTH=3500
OLLAMA_MAX_RESPONSE_LENGTH=3500

# Agent Configuration
AGENT_DEBUG=false
AGENT_CACHE_DB=agent_cache.db
```

## Usage

Start the bot using Python:

```bash
python turboBot.py
```

Or use the startup script:

```bash
./startBot.sh
```

### Command Reference

#### Music
- `!play <url|search>`: Play a song from YouTube.
- `!search <query>`: Search YouTube and get top 5 results.
- `!skip`: Skip the current song.
- `!stop`: Stop music and clear the queue.
- `!queue`: Show the current music queue.
- `!volume <0-100>`: Set the playback volume.
- `!join` / `!leave`: Join or leave the voice channel.
- `!quality <low|medium|high>`: Set audio download quality preference.

#### AI & Utilities
- `!askollama <prompt>`: Ask the AI a question (uses web search tools if needed).
- `!remindme <interval> <duration> <message>`: Set a repeating reminder (e.g., `!remindme 30 2h Drink water` - every 30m for 2h).
- `!userinfo @user`: Display information about a user.

#### Admin & Moderation
- `!kick @user [reason]`: Kick a member.
- `!ban @user [reason]`: Ban a member.
- `!clear <amount>`: Delete the last N messages.
- `!cleanup`: Manually trigger the file cleanup task.
- `!announce <#channel> <message>`: Send an announcement embed.
- `!add_reaction_role <msg_id> <emoji> @role`: Add a reaction role to a message.
- `!post_rules`: Post the standard rules message in the current channel (sets up verification).

## License

This project is licensed under the [MIT License](LICENSE).
