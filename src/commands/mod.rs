use serenity::builder::{CreateCommand, CreateEmbed, CreateInteractionResponse, CreateInteractionResponseMessage};
use serenity::model::prelude::*;
use serenity::prelude::*;
use chrono::{DateTime, Utc};

pub async fn ping(ctx: &Context, command: &CommandInteraction) -> Result<(), serenity::Error> {
    let start = std::time::Instant::now();
    
    let response = CreateInteractionResponse::Message(
        CreateInteractionResponseMessage::new().content("🏓 Pong!")
    );
    
    command.create_response(&ctx.http, response).await?;

    let duration = start.elapsed();
    let api_latency = duration.as_millis();
    
    let latency_text = format!("🏓 Pong!\n**API Latency:** {}ms", api_latency);

    command
        .edit_response(&ctx.http, 
            CreateInteractionResponseMessage::new().content(latency_text)
        )
        .await?;

    Ok(())
}

pub async fn serverinfo(ctx: &Context, command: &CommandInteraction) -> Result<(), serenity::Error> {
    let guild_id = match command.guild_id {
        Some(id) => id,
        None => {
            let response = CreateInteractionResponse::Message(
                CreateInteractionResponseMessage::new()
                    .content("This command can only be used in a server.")
                    .ephemeral(true)
            );
            command.create_response(&ctx.http, response).await?;
            return Ok(());
        }
    };

    let guild = match ctx.cache.guild(guild_id) {
        Some(guild) => guild,
        None => {
            let response = CreateInteractionResponse::Message(
                CreateInteractionResponseMessage::new()
                    .content("Could not fetch server information.")
                    .ephemeral(true)
            );
            command.create_response(&ctx.http, response).await?;
            return Ok(());
        }
    };

    let created_at: DateTime<Utc> = guild.id.created_at().into();
    let owner = guild.owner_id.to_user(&ctx.http).await.ok();
    
    let embed = CreateEmbed::new()
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
        .field("Verification Level", format!("{:?}", guild.verification_level), true);

    let response = CreateInteractionResponse::Message(
        CreateInteractionResponseMessage::new().embed(embed)
    );
    
    command.create_response(&ctx.http, response).await?;

    Ok(())
}

pub async fn membercount(ctx: &Context, command: &CommandInteraction) -> Result<(), serenity::Error> {
    let guild_id = match command.guild_id {
        Some(id) => id,
        None => {
            let response = CreateInteractionResponse::Message(
                CreateInteractionResponseMessage::new()
                    .content("This command can only be used in a server.")
                    .ephemeral(true)
            );
            command.create_response(&ctx.http, response).await?;
            return Ok(());
        }
    };

    let guild = match ctx.cache.guild(guild_id) {
        Some(guild) => guild,
        None => {
            let response = CreateInteractionResponse::Message(
                CreateInteractionResponseMessage::new()
                    .content("Could not fetch server information.")
                    .ephemeral(true)
            );
            command.create_response(&ctx.http, response).await?;
            return Ok(());
        }
    };

    let message = format!(
        "This server, **{}**, has **{}** members.",
        guild.name, guild.member_count
    );

    let response = CreateInteractionResponse::Message(
        CreateInteractionResponseMessage::new().content(message)
    );
    
    command.create_response(&ctx.http, response).await?;

    Ok(())
}

pub fn register_ping() -> CreateCommand {
    CreateCommand::new("ping").description("Check the bot's latency")
}

pub fn register_serverinfo() -> CreateCommand {
    CreateCommand::new("serverinfo").description("Display information about the current server")
}

pub fn register_membercount() -> CreateCommand {
    CreateCommand::new("membercount").description("Display the current member count of the server")
}
