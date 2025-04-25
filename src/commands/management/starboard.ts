import {
  ChatInputCommandInteraction,
  SlashCommandBuilder,
  ChannelType,
  PermissionFlagsBits
} from 'discord.js';
import fs from 'fs';
import path from 'path';

interface StarboardConfig {
  guildId: string;
  channelIds: string[];
  emoji: string;
  onlyAttachments: boolean;
  autoThread: boolean;
  hallOfFameChannelId?: string;   // optional HOF channel
  threshold?: number;             // optional reaction count
}

const configPath = path.join(__dirname, '../../../data/starboard.json');

function saveConfig(guildId: string, data: Omit<StarboardConfig, 'guildId'>) {
  let configs: StarboardConfig[] = [];
  if (fs.existsSync(configPath)) {
    configs = JSON.parse(fs.readFileSync(configPath, 'utf-8'));
  }
  configs = configs.filter(c => c.guildId !== guildId);
  configs.push({ guildId, ...data });
  fs.writeFileSync(configPath, JSON.stringify(configs, null, 2));
}

export const data = new SlashCommandBuilder()
  .setName('starboard')
  .setDescription('Configure starboard reaction behavior')
  .setDefaultMemberPermissions(PermissionFlagsBits.ManageGuild)
  .addStringOption(opt =>
    opt
      .setName('channels')
      .setDescription('List of channels to monitor (#mentions or IDs, space-separated)')
      .setRequired(true)
  )
  .addStringOption(opt =>
    opt
      .setName('emoji')
      .setDescription('Emoji to react with')
      .setRequired(true)
  )
  .addBooleanOption(opt =>
    opt
      .setName('only_attachments')
      .setDescription('Only react to messages with attachments')
      .setRequired(false)
  )
  .addBooleanOption(opt =>
    opt
      .setName('auto_thread')
      .setDescription('Automatically create a thread after reacting')
      .setRequired(false)
  )
  .addChannelOption(opt =>
    opt
      .setName('hall_of_fame')
      .setDescription('Optional channel for Hall of Fame reposts')
      .addChannelTypes(ChannelType.GuildText)
      .setRequired(false)
  )
  .addIntegerOption(opt =>
    opt
      .setName('threshold')
      .setDescription('Number of reactions before reposting to Hall of Fame')
      .setMinValue(1)
      .setRequired(false)
  );

export async function execute(interaction: ChatInputCommandInteraction) {
  const guildId          = interaction.guildId!;
  const channelsInput    = interaction.options.getString('channels', true);
  const emoji            = interaction.options.getString('emoji', true);
  const onlyAttachments  = interaction.options.getBoolean('only_attachments') ?? false;
  const autoThread       = interaction.options.getBoolean('auto_thread') ?? false;
  const hofChannel       = interaction.options.getChannel('hall_of_fame');
  const threshold        = interaction.options.getInteger('threshold') ?? undefined;

  // extract numeric IDs
  const ids = Array.from(new Set(
    Array.from(channelsInput.matchAll(/(\d{17,19})/g), m => m[1])
  ));

  // validate channels
  const validChannelIds: string[] = [];
  for (const id of ids) {
    const chan = interaction.guild?.channels.cache.get(id);
    if (chan?.type === ChannelType.GuildText) validChannelIds.push(id);
  }
  if (validChannelIds.length === 0) {
    return interaction.reply('❌ No valid text channels found in your input.');
  }

  const configData: Omit<StarboardConfig, 'guildId'> = {
    channelIds: validChannelIds,
    emoji,
    onlyAttachments,
    autoThread,
    hallOfFameChannelId: hofChannel?.id,
    threshold
  };

  saveConfig(guildId, configData);

  // build confirmation message
  const lines = [
    `✅ Starboard configured for channels: ${validChannelIds.map(id => `<#${id}>`).join(' ')}`,
    `• Emoji: ${emoji}`,
    `• Only attachments: ${onlyAttachments}`,
    `• Auto-thread: ${autoThread}`
  ];
  if (hofChannel) lines.push(`• Hall of Fame: <#${hofChannel.id}>`);
  if (threshold) lines.push(`• Threshold: ${threshold} reactions`);

  await interaction.reply(lines.join('\n'));
}