use serenity::async_trait;
use serenity::client::{Context, EventHandler};
use serenity::model::application::interaction::{Interaction, InteractionResponseType};
use serenity::model::application::command::Command;
use serenity::model::gateway::Ready;
use serenity::model::prelude::*;
use serenity::prelude::*;
use std::sync::Arc;
use tracing::{error, info};

use crate::ai::GeminiClient;
use crate::commands;
use crate::config::Config;

pub struct ShardManagerContainer;

impl TypeMapKey for ShardManagerContainer {
    type Value = Arc<Mutex<serenity::gateway::ShardManager>>;
}

pub struct Handler {
    pub config: Config,
    pub gemini_client: GeminiClient,
}

impl Handler {
    pub fn new(config: Config) -> Self {
        let gemini_client = GeminiClient::new(config.gemini_api_key.clone());
        Self {
            config,
            gemini_client,
        }
    }
}

#[async_trait]
impl EventHandler for Handler {
    async fn ready(&self, ctx: Context, ready: Ready) {
        info!("{} is connected and ready!", ready.user.name);
        
        let commands = Command::set_global_application_commands(&ctx.http, |commands| {
            commands
                .create_application_command(|command| commands::register_ping(command))
                .create_application_command(|command| commands::register_serverinfo(command))
                .create_application_command(|command| commands::register_membercount(command))
        })
        .await;

        match commands {
            Ok(_) => info!("Successfully registered application commands"),
            Err(e) => error!("Failed to register application commands: {}", e),
        }
    }

    async fn interaction_create(&self, ctx: Context, interaction: Interaction) {
        if let Interaction::ApplicationCommand(command) = interaction {
            let result = match command.data.name.as_str() {
                "ping" => commands::ping(&ctx, &command).await,
                "serverinfo" => commands::serverinfo(&ctx, &command).await,
                "membercount" => commands::membercount(&ctx, &command).await,
                _ => {
                    error!("Unknown command: {}", command.data.name);
                    Ok(())
                }
            };

            if let Err(e) = result {
                error!("Error handling command {}: {}", command.data.name, e);
                let _ = command
                    .create_interaction_response(&ctx.http, |response| {
                        response
                            .kind(InteractionResponseType::ChannelMessageWithSource)
                            .interaction_response_data(|message| {
                                message
                                    .content("An error occurred while processing the command.")
                                    .ephemeral(true)
                            })
                    })
                    .await;
            }
        }
    }

    async fn message(&self, ctx: Context, msg: Message) {
        if msg.author.bot {
            return;
        }

        if self.gemini_client.should_respond_to_message(&msg.content, &self.config.bot_name) {
            let typing = msg.channel_id.start_typing(&ctx.http);
            
            match self.gemini_client.generate_response(&msg.content).await {
                Ok(response) => {
                    let _ = typing.map(|t| t.stop());
                    
                    if let Err(e) = msg.channel_id.say(&ctx.http, response).await {
                        error!("Failed to send AI response: {}", e);
                    }
                }
                Err(e) => {
                    let _ = typing.map(|t| t.stop());
                    error!("Failed to generate AI response: {}", e);
                    
                    let _ = msg
                        .channel_id
                        .say(&ctx.http, "Sorry, I'm having trouble generating a response right now.")
                        .await;
                }
            }
        }
    }
}
