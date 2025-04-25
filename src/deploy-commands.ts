import { SlashCommandBuilder } from 'discord.js';
import { REST, Routes } from 'discord.js';
import 'dotenv/config';
import fs from 'fs';
import path from 'path';

// Define the paths for each folder of commands
const commandFolders = ['members', 'staff', 'management'];

const commands = [];

// Loop through each folder and load the commands
for (const folder of commandFolders) {
  const folderPath = path.join(__dirname, 'commands', folder);
  
  // Ensure folder exists
  if (fs.existsSync(folderPath)) {
    const files = fs.readdirSync(folderPath).filter(file => file.endsWith('.ts'));

    for (const file of files) {
      const command = require(path.join(folderPath, file)).data;
      if (command) {
        commands.push(command);
      }
    }
  }
}

const rest = new REST({ version: '10' }).setToken(process.env.DISCORD_TOKEN!);

(async () => {
  try {
    console.log('⏳ Deploying commands globally...');

    // Global commands deployment to all servers
    await rest.put(
      Routes.applicationCommands(process.env.CLIENT_ID!), // Global deployment
      { body: commands }
    );

    console.log('✅ Successfully deployed commands globally.');
  } catch (error) {
    console.error('❌ Failed to deploy commands:', error);
  }
})();
