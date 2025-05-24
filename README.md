# Axis Discord Bot (Rust)

A fast and efficient Discord bot written in Rust with AI capabilities powered by Google's Gemini Flash API. Optimized for Railway deployment.

## Features

- **Slash Commands:**
  - `/ping` - Check the bot's latency
  - `/serverinfo` - Display detailed server information
  - `/membercount` - Show the current member count

- **AI Integration:**
  - Responds to messages starting with "hey axis", "hi axis", "hello axis", or "yo axis"
  - Powered by Google's Gemini Flash API for natural conversations

## Railway Deployment

1. **Fork/Clone this repository**

2. **Connect to Railway:**
   - Visit [railway.app](https://railway.app)
   - Connect your GitHub repository
   - Railway will auto-detect the Rust project

3. **Set Environment Variables in Railway Dashboard:**
   ```
   DISCORD_TOKEN=your_discord_bot_token_here
   GEMINI_API_KEY=your_gemini_api_key_here
   BOT_NAME=axis
   ```

4. **Deploy:**
   - Railway will automatically build and deploy your bot
   - No additional configuration needed

## Local Development (Optional)

If you want to run locally:

```bash
git clone <repository-url>
cd axis-bot

# Set environment variables
export DISCORD_TOKEN="your_token"
export GEMINI_API_KEY="your_key"
export BOT_NAME="axis"

cargo run
```

## Usage

### Slash Commands
- Use `/ping` to check bot latency
- Use `/serverinfo` in a server to get detailed information
- Use `/membercount` to see how many members are in the server

### AI Chat
Simply start a message with "hey axis" or similar phrases and the bot will respond using AI.

Example:
```
hey axis, how are you today?
```

## Project Structure

```
src/
├── main.rs          # Entry point
├── config.rs        # Configuration handling
├── bot.rs           # Event handler and bot logic
├── commands/        # Slash commands implementation
│   └── mod.rs
└── ai/              # AI integration
    └── mod.rs
```

## Performance

This Rust implementation offers:
- Low memory footprint (~10MB RAM usage)
- Fast response times (<50ms for commands)
- Efficient async handling
- Robust error handling
- No database dependencies for core features

## License

MIT License
