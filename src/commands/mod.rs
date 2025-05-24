use serenity::builder::CreateApplicationCommand;
use serenity::model::prelude::*;
use serenity::model::application::interaction::{InteractionResponseType};
use serenity::prelude::*;
use chrono::{DateTime, Utc};

pub async fn ping(ctx: &Context, command: &CommandInteraction) -> Result<(), serenity::Error> {
    let start = std::time::Instant::now();
    
    command
        .create_response(&ctx.http, |response| {
            response
                .kind(InteractionResponseType::ChannelMessageWithSource)
                .interaction_response_data(|message| message.content("🏓 Pong!"))
        })
        .await?;

    let duration = start.elapsed();
    let api_latency = duration.as_millis();
    
    let websocket_latency = {
        let data = ctx.data.read().await;
        data.get::<crate::bot::ShardManagerContainer>()
            .map(|shard_manager| {
                // Get latency from shard manager if available
                None::<u128> // Simplified for now
            })
            .flatten()
    };

    let latency_text = match websocket_latency {
        Some(ws_latency) => format!("🏓 Pong!\n**API Latency:** {}ms\n**WebSocket Latency:** {}ms", api_latency, ws_latency),
        None => format!("🏓 Pong!\n**API Latency:** {}ms", api_latency),
    };

    command
        .edit_response(&ctx.http, |response| {
            response.content(latency_text)
        })
        .await?;

    Ok(())
}

pub async fn serverinfo(ctx: &Context, command: &CommandInteraction) -> Result<(), serenity::Error> {
    let guild_id = match command.guild_id {
        Some(id) => id,
        None => {
            command
                .create_response(&ctx.http, |response| {
                    response
                        .kind(InteractionResponseType::ChannelMessageWithSource)
                        .interaction_response_data(|message| {
                            message.content("This command can only be used in a server.").ephemeral(true)
                        })
                })
                .await?;
            return Ok(());
        }
    };

    let guild = match ctx.cache.guild(guild_id) {
        Some(guild) => guild,
        None => {
            command
                .create_response(&ctx.http, |response| {
                    response
                        .kind(InteractionResponseType::ChannelMessageWithSource)
                        .interaction_response_data(|message| {
                            message.content("Could not fetch server information.").ephemeral(true)
                        })
                })
                .await?;
            return Ok(());
        }
    };

    let created_at: DateTime<Utc> = guild.id.created_at().into();
    let owner = guild.owner_id.to_user(&ctx.http).await.ok();
    
    command
        .create_response(&ctx.http, |response| {
            response
                .kind(InteractionResponseType::ChannelMessageWithSource)
                .interaction_response_data(|message| {
                    message.embed(|embed| {
                        embed
                            .title(format!("{} Server Information", guild.name))
                            .color(0x00ff00)
                            .thumbnail(guild.icon_url().unwrap_or_default())
                            .field("Server ID", guild.id.to_string(), true)
                            .field("Owner", owner.map_or("Unknown".to_string(), |u| u.tag()), true)
                            .field("Member Count", guild.member_count.to_string(), true)
                            .field("Creation Date", created_at.format("%Y-%m-%d %H:%M:%S UTC").to_string(), true)
                            .field("Roles", guild.roles.len().to_string(), true)
                            .field("Channels", guild.channels.len().to_string(), true)
                            .field("Boost Level", guild.premium_tier.to_string(), true)
                            .field("Boosters", guild.premium_subscription_count.unwrap_or(0).to_string(), true)
                            .field("Verification Level", format!("{:?}", guild.verification_level), true)
                    })
                })
        })
        .await?;

    Ok(())
}

pub async fn membercount(ctx: &Context, command: &CommandInteraction) -> Result<(), serenity::Error> {
    let guild_id = match command.guild_id {
        Some(id) => id,
        None => {
            command
                .create_response(&ctx.http, |response| {
                    response
                        .kind(InteractionResponseType::ChannelMessageWithSource)
                        .interaction_response_data(|message| {
                            message.content("This command can only be used in a server.").ephemeral(true)
                        })
                })
                .await?;
            return Ok(());
        }
    };

    let guild = match ctx.cache.guild(guild_id) {
        Some(guild) => guild,
        None => {
            command
                .create_response(&ctx.http, |response| {
                    response
                        .kind(InteractionResponseType::ChannelMessageWithSource)
                        .interaction_response_data(|message| {
                            message.content("Could not fetch server information.").ephemeral(true)
                        })
                })
                .await?;
            return Ok(());
        }
    };

    let message = format!(
        "This server, **{}**, has **{}** members.",
        guild.name, guild.member_count
    );

    command
        .create_response(&ctx.http, |response| {
            response
                .kind(InteractionResponseType::ChannelMessageWithSource)
                .interaction_response_data(|message_builder| message_builder.content(message))
        })
        .await?;

    Ok(())
}

pub fn register_ping(command: &mut CreateApplicationCommand) -> &mut CreateApplicationCommand {
    command.name("ping").description("Check the bot's latency")
}

pub fn register_serverinfo(command: &mut CreateApplicationCommand) -> &mut CreateApplicationCommand {
    command.name("serverinfo").description("Display information about the current server")
}

pub fn register_membercount(command: &mut CreateApplicationCommand) -> &mut CreateApplicationCommand {
    command.name("membercount").description("Display the current member count of the server")
}
