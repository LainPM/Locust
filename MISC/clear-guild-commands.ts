import { REST, Routes } from 'discord.js';
import 'dotenv/config';

const rest = new REST({ version: '10' }).setToken(process.env.DISCORD_TOKEN!);

(async () => {
  try {
    console.log('⏳ Clearing all guild-specific (/) commands…');

    await rest.put(
      Routes.applicationGuildCommands(process.env.CLIENT_ID!, process.env.GUILD_ID!), // Clears guild commands
      { body: [] }
    );

    console.log('✅ Successfully cleared guild-specific (/) commands.');
  } catch (error) {
    console.error('❌ Failed to clear guild commands:', error);
  }
})();
