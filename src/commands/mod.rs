use serenity::builder::{CreateCommand, CreateEmbed, CreateInteractionResponse, CreateInteractionResponseMessage, EditInteractionResponse};
use serenity::model::prelude::*;
use serenity::prelude::*;
use chrono::{DateTime, Utc};

pub async fn ping(ctx: &Context, command: &CommandInteraction) -> Result<(), serenity::Error> {
    let http = ctx.http.clone(); // Clone http client
    let start = std::time::Instant::now();
    
    // Initial response removed.

    let duration = start.elapsed();
    let api_latency = duration.as_millis();
    
    // latency_text now only contains the latency.
    let latency_text = format!("**API Latency:** {}ms", api_latency);

    // Create the response, as there's no initial message to edit.
    command
        .create_response(&http, 
            CreateInteractionResponse::Message(
                CreateInteractionResponseMessage::new().content(latency_text)
            )
        )
        .await?;

    Ok(())
}

pub async fn serverinfo(ctx: &Context, command: &CommandInteraction) -> Result<(), serenity::Error> {
    let http = ctx.http.clone(); // Clone http client
    let guild_id = match command.guild_id {
        Some(id) => id,
        None => {
            let response = CreateInteractionResponse::Message(
                CreateInteractionResponseMessage::new()
                    .content("This command can only be used in a server.")
                    .ephemeral(true)
            );
            command.create_response(&http, response).await?;
            return Ok(());
        }
    };

    // Perform cache access and data processing in a separate block, returning a Result.
    type ServerInfoData = (String, String, String, UserId, String, String, String, String, String, String, String);
    let guild_info_result: Result<ServerInfoData, ()> = {
        match ctx.cache.guild(guild_id) {
            Some(guild_ref) => {
                let owned_guild = (*guild_ref).clone();
                let created_at_unix = owned_guild.id.created_at().unix_timestamp();
                let created_at: DateTime<Utc> = DateTime::from_timestamp(created_at_unix, 0)
                    .expect("Invalid timestamp from Discord API");
                Ok((
                    owned_guild.name.clone(),
                    owned_guild.icon_url().unwrap_or_default(),
                    owned_guild.id.to_string(),
                    owned_guild.owner_id,
                    owned_guild.member_count.to_string(),
                    created_at.format("%Y-%m-%d %H:%M:%S UTC").to_string(),
                    owned_guild.roles.len().to_string(),
                    owned_guild.channels.len().to_string(),
                    format!("{:?}", owned_guild.premium_tier),
                    owned_guild.premium_subscription_count.unwrap_or(0).to_string(),
                    format!("{:?}", owned_guild.verification_level),
                ))
            }
            None => Err(()),
        }
    }; // CacheRef is dropped here.

    // Handle the result of cache access.
    match guild_info_result {
        Ok((
            guild_name,
            icon_url,
            server_id_str,
            owner_id,
            member_count_str,
            created_at_str,
            roles_len_str,
            channels_len_str,
            premium_tier_str,
            boosters_str,
            verification_level_str,
        )) => {
            // All data is owned and Send. Perform awaits using this data.
            let owner_tag = owner_id.to_user(&http).await.map_or("Unknown".to_string(), |u| u.tag());
            
            let embed = CreateEmbed::new() // This was the start of the misplaced block
                .title(format!("{} Server Information", guild_name))
                .color(0x00ff00)
                .thumbnail(icon_url)
                .field("Server ID", server_id_str, true)
                .field("Owner", owner_tag, true)
                .field("Member Count", member_count_str, true)
                .field("Creation Date", created_at_str, true)
                .field("Roles", roles_len_str, true)
                .field("Channels", channels_len_str, true)
                .field("Boost Level", premium_tier_str, true)
                .field("Boosters", boosters_str, true)
                .field("Verification Level", verification_level_str, true);
            
            let response = CreateInteractionResponse::Message(
                CreateInteractionResponseMessage::new().embed(embed)
            );
            command.create_response(&http, response).await?;
        }
        Err(_) => {
            // Cache miss or other error signaled by Err(())
            let err_response = CreateInteractionResponse::Message(
                CreateInteractionResponseMessage::new()
                    .content("Could not fetch server information.")
                    .ephemeral(true)
            );
            command.create_response(&http, err_response).await?;
        }
    }

    Ok(())
}

pub async fn membercount(ctx: &Context, command: &CommandInteraction) -> Result<(), serenity::Error> {
    let http = ctx.http.clone(); // Clone http client
    let guild_id = match command.guild_id {
        Some(id) => id,
        None => {
            let response = CreateInteractionResponse::Message(
                CreateInteractionResponseMessage::new()
                    .content("This command can only be used in a server.")
                    .ephemeral(true)
            );
            command.create_response(&http, response).await?;
            return Ok(());
        }
    };

    // Perform cache access and data processing in a separate block, returning a Result.
    let guild_data_result: Result<(String, u64), ()> = { // Renamed and type changed
        let guild_option = ctx.cache.guild(guild_id);
        match guild_option {
            Some(guild_ref) => {
                let owned_guild = (*guild_ref).clone();
                Ok((owned_guild.name.clone(), owned_guild.member_count)) // Return tuple
            }
            None => Err(()),
        }
    }; // CacheRef (guild_ref) is dropped here.

    // Handle the result of cache access.
    match guild_data_result {
        Ok((guild_name, member_count)) => {
            let embed = CreateEmbed::new()
                .title("Member Statistics")
                .color(0x00bfff) // Deep sky blue
                .field("Server", guild_name, true)
                .field("Members", member_count.to_string(), true);

            let response = CreateInteractionResponse::Message(
                CreateInteractionResponseMessage::new().embed(embed)
            );
            command.create_response(&http, response).await?;
        }
        Err(_) => {
            // Cache miss or other error signaled by Err(())
            let err_response = CreateInteractionResponse::Message(
                CreateInteractionResponseMessage::new()
                    .content("Could not fetch server information for member count.")
                    .ephemeral(true)
            );
            command.create_response(&http, err_response).await?;
        }
    }

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