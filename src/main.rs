mod ai;
mod bot;
mod commands;
mod config;

use anyhow::Result;
use bot::{Handler, ShardManagerContainer};
use config::Config;
use serenity::prelude::*;
use std::sync::Arc;
use tracing::{error, info};
use tracing_subscriber;

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt::init();
    info!("Starting Axis bot...");

    let config = match Config::from_env() {
        Ok(config) => {
            info!("Configuration loaded successfully");
            config
        }
        Err(e) => {
            error!("Failed to load configuration: {}", e);
            return Err(e);
        }
    };

    let handler = Handler::new(config.clone());
    
    let intents = GatewayIntents::GUILD_MESSAGES
        | GatewayIntents::DIRECT_MESSAGES
        | GatewayIntents::MESSAGE_CONTENT
        | GatewayIntents::GUILDS;

    let mut client = match Client::builder(&config.discord_token, intents)
        .event_handler(handler)
        .await
    {
        Ok(client) => client,
        Err(e) => {
            error!("Failed to create Discord client: {}", e);
            return Err(e.into());
        }
    };

    {
        let mut data = client.data.write().await;
        data.insert::<ShardManagerContainer>(client.shard_manager.clone());
    }

    info!("Axis bot is starting up...");

    if let Err(e) = client.start().await {
        error!("Client error: {:?}", e);
        return Err(e.into());
    }

    Ok(())
}
