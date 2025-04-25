// ── Extend Client Type ──
// lets us attach .commands to the client
declare module 'discord.js' {
  interface Client {
    commands: Collection<string, {
      data: { name: string; toJSON(): any };
      execute(interaction: any): Promise<any>;
    }>;
    postedToHallOfFame?: Set<string>;
  }
}

// ── Imports ──
import {
  Client,
  GatewayIntentBits,
  Collection,
  Events,
  Interaction,
  Message,
  TextChannel,
  PartialMessageReaction,
  PartialUser,
  MessageReaction,
  User,
  EmbedBuilder,
  Partials,
  PartialMessage
} from 'discord.js';
import 'dotenv/config';
import fs from 'fs';
import path from 'path';

interface StarboardConfig {
  guildId: string;
  channelIds: string[];
  emoji: string;
  onlyAttachments: boolean;
  autoThread: boolean;
  hallOfFameChannelId?: string;
  threshold?: number;
}

// ── Setup Client ──
const client = new Client({
  intents: [
    GatewayIntentBits.Guilds,
    GatewayIntentBits.GuildMessages,
    GatewayIntentBits.MessageContent,
    GatewayIntentBits.GuildMessageReactions // Added for reaction events
  ],
  partials: [Partials.Message, Partials.Channel, Partials.Reaction] // Fixed partials syntax
});

client.commands = new Collection();
client.postedToHallOfFame = new Set<string>();

// ── Load Commands from Subfolders ──
const root = path.join(__dirname, 'commands');
if (!fs.existsSync(root)) {
  console.error(`Commands folder not found at ${root}`);
  process.exit(1);
}

for (const folder of fs.readdirSync(root)) {
  const folderPath = path.join(root, folder);
  if (!fs.statSync(folderPath).isDirectory()) continue;

  const files = fs
    .readdirSync(folderPath)
    .filter(f => f.endsWith('.ts') || f.endsWith('.js'));

  for (const file of files) {
    const fullPath = path.join(folderPath, file);
    const commandModule = require(fullPath);
    const cmd = commandModule.data;
    if (cmd?.name && typeof commandModule.execute === 'function') {
      client.commands.set(cmd.name, commandModule);
      console.log(`Loaded command [${folder}] → ${cmd.name}`);
    } else {
      console.warn(`Skipping ${file} in ${folder}: missing data.name or execute()`);
    }
  }
}

// Helper function to load starboard configs
function loadStarboardConfigs(): StarboardConfig[] {
  const configFile = path.join(__dirname, '../data/starboard.json');
  if (!fs.existsSync(configFile)) {
    return [];
  }
  try {
    return JSON.parse(fs.readFileSync(configFile, 'utf-8'));
  } catch (err) {
    console.error('Error loading starboard configs:', err);
    return [];
  }
}

// Helper function to save starboard configs
function saveStarboardConfigs(configs: StarboardConfig[]): void {
  const configFile = path.join(__dirname, '../data/starboard.json');
  const dirPath = path.dirname(configFile);

  if (!fs.existsSync(dirPath)) {
    fs.mkdirSync(dirPath, { recursive: true });
  }

  fs.writeFileSync(configFile, JSON.stringify(configs, null, 2), 'utf-8');
}

// ── On Bot Ready ──
client.once(Events.ClientReady, () => {
  console.log(`✅ Logged in as ${client.user?.tag}`);
});

// ── Handle Slash Commands ──
client.on(Events.InteractionCreate, async (interaction: Interaction) => {
  if (!interaction.isChatInputCommand()) return;

  const command = client.commands.get(interaction.commandName);
  if (!command) return;

  try {
    // public reply by default; commands themselves decide if they DM or respond ephemerally
    await command.execute(interaction);
  } catch (err) {
    console.error(`Error executing ${interaction.commandName}`, err);
    if (interaction.deferred || interaction.replied) {
      await interaction.followUp({ content: '❌ There was an error running that command.', ephemeral: true });
    } else {
      await interaction.reply({ content: '❌ There was an error running that command.', ephemeral: true });
    }
  }
});

client.on(Events.MessageCreate, async (message: Message) => {
  if (message.author.bot || !message.guild) return;

  // Load starboard configs
  const configs = loadStarboardConfigs();
  const cfg = configs.find(c => c.guildId === message.guildId);
  if (!cfg) return;                                                   // this guild not set up

  // ─── The rest of your starboard logic ───
  if (!cfg.channelIds.includes(message.channel.id)) return;
  if (cfg.onlyAttachments && message.attachments.size === 0) return;

  try {
    await message.react(cfg.emoji);
  } catch (e) {
    console.error('Starboard reaction failed', e);
  }

  if (cfg.autoThread && message.channel instanceof TextChannel) {
    try {
      await message.channel.threads.create({
        name: `Discussion – ${cfg.emoji}`,
        startMessage: message.id,
        autoArchiveDuration: 60
      });
    } catch (e) {
      console.error('Thread creation failed', e);
    }
  }
});

// Fix type issues with MessageReactionAdd event
client.on(
  Events.MessageReactionAdd,
  async (reaction: MessageReaction | PartialMessageReaction, user: User | PartialUser) => {
    if (user.bot) return;

    // Only care about our starboard emoji
    const configs = loadStarboardConfigs();

    // We need to fetch the message if it's partial
    if (reaction.partial) {
      try {
        await reaction.fetch();
      } catch (error) {
        console.error('Something went wrong when fetching the reaction:', error);
        return;
      }
    }

    const guildId = reaction.message.guild?.id;
    if (!guildId) return;

    const cfg = configs.find(c => c.guildId === guildId);
    if (!cfg) return;

    // Check emoji matches after fetching (to ensure we have the full data)
    if (reaction.emoji.toString() !== cfg.emoji) return;

    // Make sure we have the full message
    const msg = reaction.message as Message | PartialMessage;
    if (msg.partial) {
      try {
        await msg.fetch();
      } catch (error) {
        console.error('Something went wrong when fetching the message:', error);
        return;
      }
    }

    // Safety check for channel ID
    const channelId = msg.channel.id;
    if (!channelId) return;

    // Ensure it's in a monitored channel
    if (!cfg.channelIds.includes(channelId)) return;

    // Get full message object
    const fullMsg = await msg.fetch();

    // Attachments rule
    if (cfg.onlyAttachments && fullMsg.attachments.size === 0) return;

    // Auto-thread as before (if not already threaded)
    if (cfg.autoThread &&
      fullMsg.channel instanceof TextChannel &&
      !fullMsg.hasThread) {
      try {
        await fullMsg.channel.threads.create({
          name: `Discussion – ${cfg.emoji}`,
          startMessage: fullMsg.id,
          autoArchiveDuration: 60
        });
      } catch (err) {
        console.error('Thread creation failed', err);
      }
    }

    // Hall of Fame logic
    if (cfg.hallOfFameChannelId && cfg.threshold) {
      // Count reactions of that emoji
      const count = reaction.count ?? 0;
      if (count >= cfg.threshold) {
        // Check if already posted to Hall of Fame (to prevent duplicates)
        if (client.postedToHallOfFame?.has(fullMsg.id)) return;

        // Fetch target channel
        const guild = fullMsg.guild;
        if (!guild) return;

        const hofChan = guild.channels.cache.get(cfg.hallOfFameChannelId);
        if (!hofChan?.isTextBased() || hofChan.isThread()) return;

        const textChan = hofChan as TextChannel;

        // Get message author - safely handle null cases
        const msgAuthor = fullMsg.author;
        if (!msgAuthor) {
          console.error('Message author is null');
          return;
        }

        // Build embed properly with EmbedBuilder to fix type issues
        const embed = new EmbedBuilder()
          .setAuthor({
            name: msgAuthor.tag || 'Unknown User',
            iconURL: msgAuthor.displayAvatarURL()
          })
          .setDescription(fullMsg.content || null)
          .setTimestamp()
          .setFooter({
            text: `${cfg.emoji} ${count} | Original: ${fullMsg.url}`
          });

        // Add image if there's an attachment
        const attachment = fullMsg.attachments.first();
        if (attachment?.contentType?.startsWith('image')) {
          embed.setImage(attachment.url); // Embed only if it's an image
        }


        await textChan.send({ embeds: [embed] }); // No files array

        // Mark as posted to prevent duplicates
        client.postedToHallOfFame?.add(fullMsg.id);
      }
    }
  }
);

// ── Login ──
client.login(process.env.DISCORD_TOKEN);