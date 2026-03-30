# can-we-update-mc

A Discord bot that checks if your mods are ready for a Minecraft version update. It accepts the same mod format as `MODRINTH_PROJECTS` in itzg/docker-minecraft-server.

## Features

- Check if all your mods are compatible with a specific Minecraft version
- Rich Discord embed output with compatibility status per mod
- Supports Fabric, Forge, Quilt, NeoForge, and Paper loaders

## Prerequisites

- Python 3.12+
- A Discord bot token
- A Discord server where you can add bots

## Creating a Discord Bot

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Click **New Application** and give it a name
3. On the left sidebar, click **Bot**
4. Click **Reset Token** to generate a bot token
5. Copy and save the token securely (you'll need it later)
6. Scroll down to **Privileged Gateway Intents** and enable:
   - **Message Content Intent**
7. Click **Save Changes**
8. To add the bot to your server, go to the **OAuth2 > URL Generator** page
9. Select the following scopes:
   - `bot`
   - `applications.commands`
10. Under **Bot Permissions**, select:
   - **Send Messages**
   - **Embed Links**
11. Copy the generated URL and open it in your browser
12. Select your server and authorize the bot

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/deyloop/can-we-update-mc.git
cd can-we-update-mc
```

### 2. Install dependencies

```bash
uv sync
```

### 3. Configure the bot

Copy the example environment file:

```bash
cp .env.example .env
```

Edit `.env` and add your Discord bot token:

```env
DISCORD_TOKEN=your_bot_token_here
```

Edit `config.toml` to configure the bot:

```toml
[discord]
# Token is read from DISCORD_TOKEN env var or set here
guild_id = 123456789  # Optional: for guild-specific commands

[mods]
file = "mods.txt"
loader = "fabric"  # fabric, forge, quilt, neoforge, paper
```

### 4. Create your mods list

Create `mods.txt` in the project root with your mods (one per line):

```text
# Fabric API (required by most mods)
fabric-api

# Performance mods
sodium
indium
lithium

# You can specify a different loader per mod
forge:jei
```

Supported formats per line:
- `mod-slug` - Just the project slug
- `loader:mod-slug` - With a specific loader prefix
- `mod-slug:version` - With a version specifier (e.g., `beta` or version number)
- `loader:mod-slug:version` - All combined

## Running the Bot

```bash
uv run python -m bot.main
```

## Docker Deployment

### Prerequisites

- Docker installed locally
- SSH access to your remote server
- The remote server must have Docker running

### Configuration

Ensure your `.env` file contains:

```env
DISCORD_TOKEN=your_bot_token_here

# Remote deployment settings
REMOTE_HOST=your-server.com
REMOTE_USER=root
REMOTE_DIR=/opt/can-we-update-mc
```

### Deploy

Run the deploy script:

```bash
./deploy
```

This will:
1. Build the Docker image locally
2. Save it to a tar archive
3. Transfer the image, `.env`, `config.toml`, and `mods.txt` to the remote server
4. Load the image and start the container
5. Prompt to tail logs

### Remote Management

SSH into your server and use docker compose:

```bash
# View logs
docker compose -f /opt/can-we-update-mc/docker-compose.yml logs -f

# Restart the bot
docker compose -f /opt/can-we-update-mc/docker-compose.yml restart

# Stop the bot
docker compose -f /opt/can-we-update-mc/docker-compose.yml down
```

## Discord Commands

| Command | Description |
|---------|-------------|
| `/check <version>` | Check if your mods are compatible with a Minecraft version |
| `/checklatest` | Check mods against the latest Minecraft release |
| `/mods` | Show the list of mods being tracked |

### Examples

- `/check 1.21.5` - Check compatibility for Minecraft 1.21.5
- `/check 1.20.4` - Check compatibility for Minecraft 1.20.4
- `/checklatest` - Check against the latest Minecraft release

## Mod List Format

The mod list format is compatible with [itzg/docker-minecraft-server's MODRINTH_PROJECTS](https://github.com/itzg/docker-minecraft-server/blob/master/docs/mods-and-plugins/modrinth.md):

| Format | Example |
|--------|---------|
| Project slug | `sodium` |
| With loader prefix | `fabric:sodium` |
| Specific version | `fabric-api:beta` |
| Full format | `fabric:sodium:0.5.0` |

## Development

```bash
# Install dev dependencies
uv sync --all-extras

# Run linter
uv run ruff check bot/

# Run type checker
uv run mypy bot/

# Run tests
uv run pytest tests/
```

## License

Apache License 2.0. See LICENSE
