import {
    SlashCommandBuilder,
    ChatInputCommandInteraction,
    PermissionFlagsBits,
    EmbedBuilder,
    GuildMember
} from 'discord.js';
import fs from 'fs';
import path from 'path';

module.exports = {
    data: new SlashCommandBuilder()
        .setName('warn')
        .setDescription('Warn a user for misconduct.')
        .addUserOption(option =>
            option.setName('user')
                .setDescription('User to warn')
                .setRequired(true)
        )
        .addStringOption(option =>
            option.setName('reason')
                .setDescription('Reason for the warning')
                .setRequired(true)
        )
        .setDefaultMemberPermissions(PermissionFlagsBits.ModerateMembers),

    async execute(interaction: ChatInputCommandInteraction) {
        const target = interaction.options.getMember('user') as GuildMember;
        const reason = interaction.options.getString('reason', true);
        const staff = interaction.member as GuildMember;

        // Role check — only users with "Staff" role can use
        if (!staff.roles.cache.some(role => role.name === 'Staff')) {
            return interaction.reply({ content: '❌ You don’t have permission to use this command.', ephemeral: true });
        }

        if (!target || target.user.bot) {
            return interaction.reply({ content: '❌ Invalid target.', ephemeral: true });
        }

        // Generate case ID
        const caseId = Math.random().toString(36).substring(2, 10).toUpperCase();

        // Save to file
        const dataDir = path.join(__dirname, '../../../data');
        const warnFile = path.join(dataDir, 'warnings.json');
        if (!fs.existsSync(dataDir)) fs.mkdirSync(dataDir);
        let warnings: any[] = [];
        if (fs.existsSync(warnFile)) {
            const rawData = fs.readFileSync(warnFile, 'utf-8');
            // Check if the file content is not empty
            if (rawData.trim()) {
                try {
                    warnings = JSON.parse(rawData);
                } catch (err) {
                    console.error('Error parsing JSON from warnings file:', err);
                    warnings = []; // Reset to empty array if JSON is invalid
                }
            }
        }


        const warning = {
            caseId,
            userId: target.id,
            staffId: staff.id,
            reason,
            timestamp: new Date().toISOString()
        };

        warnings.push(warning);
        fs.writeFileSync(warnFile, JSON.stringify(warnings, null, 2));

        // DM the user
        try {
            await target.send({
                embeds: [
                    new EmbedBuilder()
                        .setTitle('⚠️ You have been warned')
                        .setDescription(`**Reason:** ${reason}\n**Case ID:** ${caseId}`)
                        .setColor('Orange')
                        .setTimestamp()
                ]
            });
        } catch (err) {
            console.warn(`Could not DM ${target.user.tag}.`);
        }

        // Reply in server
        await interaction.reply({
            embeds: [
                new EmbedBuilder()
                    .setTitle('⚠️ User Warned')
                    .addFields(
                        { name: 'User', value: `${target}`, inline: true },
                        { name: 'Staff', value: `${staff}`, inline: true },
                        { name: 'Reason', value: reason },
                        { name: 'Case ID', value: caseId }
                    )
                    .setColor('Orange')
                    .setTimestamp()
            ]
        });
    }
};  