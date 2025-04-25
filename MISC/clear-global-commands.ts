import { REST, Routes } from 'discord.js';
import 'dotenv/config';

const rest = new REST({ version: '10' }).setToken(process.env.DISCORD_TOKEN!);

(async () => {
  try {
    console.log('⏳ Clearing global (/) commands…');

    await rest.put(
      Routes.applicationCommands(process.env.CLIENT_ID!),  // Clears global commands
      { body: [] }
    );

    console.log('✅ Successfully cleared global (/) commands.');
  } catch (error) {
    console.error('❌ Failed to clear global commands:', error);
  }
})();
