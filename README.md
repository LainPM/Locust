# Advanced Discord Bot - Refactored

## Description
This is a refactored and improved Discord bot built with Python using the `discord.py` library. It features a modular cog-based architecture, MongoDB integration for data persistence, and a set of useful commands for server information and moderation.

## Features
-   **Modular Cog-based Architecture:** Commands and features are organized into cogs for better maintainability.
-   **MongoDB Integration:** User warnings, mutes, kicks, and bans are stored in a MongoDB database.
-   **Basic Commands:**
    -   `/ping`: Checks the bot's latency.
    -   `/info`: Displays information about the bot (version, uptime, creator, etc.).
    -   `/serverinfo`: Shows detailed information about the current server.
    -   `/membercount`: Displays the current member count of the server.
-   **Moderation Commands:**
    -   `/warn <user> <reason>`: Warns a user and records the infraction.
    -   `/mute <user> <duration> <reason>`: Mutes a user for a specified duration (e.g., "1h30m", "2d"). Uses Discord's `timeout` feature for mutes up to 28 days.
    -   `/kick <user> <reason>`: Kicks a user from the server and records it.
    -   `/ban <user> <reason>`: Bans a user from the server and records it.
-   **Modlog Commands:**
    -   `/modlogs <user>`: Retrieves and displays a user's moderation history (warnings, mutes, kicks, bans).

## Setup Instructions

1.  **Clone the Repository:**
    ```bash
    git clone <your_repository_url>
    cd <repository_directory>
    ```

2.  **Create a `.env` File:**
    Create a file named `.env` in the root directory of the project and add your bot token and MongoDB URI:
    ```env
    DISCORD_TOKEN=your_actual_discord_bot_token_here
    MONGO_URI=your_mongodb_connection_string_here

    # Optional: Your Discord User ID(s) for owner-specific commands
    OWNER_IDS=your_discord_id,another_discord_id 
    COMMAND_PREFIX=! # Default prefix for any traditional commands (mostly for owners)
    BOT_STATUS=over the server # Custom status message for the bot
    ```

3.  **Install Dependencies:**
    Make sure you have Python 3.8 or higher installed. Then, install the required libraries:
    ```bash
    pip install -r requirements.txt
    ```

4.  **Run the Bot:**
    ```bash
    python main.py
    ```

## Configuration
-   **Environment Variables (`.env`):** Essential for `DISCORD_TOKEN` and `MONGO_URI`.
-   **`config.py`:** Contains logic to load variables from `.env` and defines other bot settings like `OWNER_IDS`, default `PREFIX`, and `BOT_STATUS`.

## Project Structure
-   `main.py`: The main entry point for the bot.
-   `core/`: Contains core classes:
    -   `bot.py` (`AxisBot`): The main bot class.
    -   `database.py` (`DatabaseManager`): Handles MongoDB interactions.
    -   `events.py`: Core event listeners (like `on_ready`).
-   `cogs/`: Houses the command modules (cogs):
    -   `basic.py`: Basic informational commands.
    -   `moderation.py`: Moderation commands.
    -   `modlogs.py`: Modlog viewing command.
    -   `utils/`: Utility functions for cogs (e.g., `duration_parser.py`).
-   `config.py`: Loads and provides access to bot configuration settings.
-   `.env`: Stores sensitive credentials and environment-specific settings (should NOT be committed to Git).
-   `requirements.txt`: Lists project dependencies.
-   `Procfile`, `.gitignore`: Standard deployment and Git files.

## Contributing
Contributions are welcome! If you find any issues or have suggestions for improvements, please open an issue or submit a pull request.
```
