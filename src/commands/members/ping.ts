import { SlashCommandBuilder, ChatInputCommandInteraction } from 'discord.js';

module.exports = {
  data: new SlashCommandBuilder()
    .setName('ping')
    .setDescription('Replies with pong and shows latency.'), // no setDefaultMemberPermissions, no setDMPermission

  async execute(interaction: ChatInputCommandInteraction) {
    // Acknowledge the interaction so we can edit later
    await interaction.deferReply();

    // Grab the deferred reply to measure real round-trip latency
    const sent = await interaction.fetchReply();
    const latency = sent.createdTimestamp - interaction.createdTimestamp;

    // Edit the reply publicly with the latency
    await interaction.editReply(`🏓 Pong! Latency is **${latency}ms**`);
  }
};