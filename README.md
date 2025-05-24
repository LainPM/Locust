# Axis Bot

A modern Discord bot built with Rust, featuring slash commands and AI-powered conversations using Google's Gemini API.

## Features

- **Slash Commands:**
  - `/ping` - Check bot latency
  - `/serverinfo` - Display detailed server information
  - `/membercount` - Show current member count
  
- **AI Chat Integration:**
  - Responds to messages starting with "hey axis", "hi axis", etc.
  - Powered by Google Gemini 1.5 Flash API
  - Natural, conversational responses

## Setup

1. **Prerequisites:**
   - Rust 1.70+ installed
   - Discord bot token
   - Google Gemini API key

2. **Clone and Configure:**
   ```bash
   git clone <repository>
   cd axis-bot
   cp .env.example .env
   ```

3. **Edit `.env`:**
   ```
   DISCORD_TOKEN=your_discord_bot_token
   GEMINI_API_KEY=your_gemini_api_key
   ```

4. **Build and Run:**
   ```bash
   cargo build --release
   cargo run --release
   ```

## Architecture

- **Framework:** Poise (command framework built on Serenity)
- **Async Runtime:** Tokio
- **HTTP Client:** Reqwest
- **Logging:** Tracing

## Project Structure

```
src/
├── main.rs       # Entry point and event handling
├── commands.rs   # Slash command implementations
├── config.rs     # Configuration management
└── gemini.rs     # Gemini API client
```

## Improvements Over Python Version

- **Performance:** Compiled language with zero-cost abstractions
- **Memory Safety:** Rust's ownership system prevents memory leaks
- **Type Safety:** Strong static typing catches errors at compile time
- **Concurrency:** Efficient async/await with Tokio runtime
- **Binary Size:** Single deployable binary with no runtime dependencies

## Discord Permissions Required

- Send Messages
- Read Message Content
- Use Slash Commands
- Embed Links
- Read Message History

## Deployment

Build for production:
```bash
cargo build --release
```

The optimized binary will be in `target/release/axis-bot`
