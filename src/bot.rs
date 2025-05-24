use serenity::async_trait;
use serenity::builder::{CreateInteractionResponse, CreateInteractionResponseMessage};
use serenity::client::{Context, EventHandler};
use serenity::model::gateway::Ready;
use serenity::model::id::{ChannelId, UserId};
use serenity::model::prelude::*;
use serenity::prelude::*;
use std::sync::Arc;
use dashmap::DashMap;
use tracing::{error, info};

use crate::ai::{GeminiClient, intents::{IntentMatcher, Intent}};
use crate::commands;
use crate::config::Config;

pub struct ShardManagerContainer;

impl TypeMapKey for ShardManagerContainer {
    type Value = Arc<serenity::gateway::ShardManager>;
}

pub struct Handler {
    pub config: Config,
    pub gemini_client: GeminiClient,
    pub active_conversations: Arc<DashMap<ChannelId, UserId>>,
    pub intent_matcher: IntentMatcher,
}

impl Handler {
    pub fn new(config: Config) -> Self {
        let gemini_client = GeminiClient::new(config.gemini_api_key.clone());
        Self {
            config,
            gemini_client,
            active_conversations: Arc::new(DashMap::new()),
            intent_matcher: IntentMatcher::new(),
        }
    }
}

#[async_trait]
impl EventHandler for Handler {
    async fn ready(&self, ctx: Context, ready: Ready) {
        info!("{} is connected and ready!", ready.user.name);
        
        let register_commands = vec![
            commands::register_ping(),
            commands::register_serverinfo(),
            commands::register_membercount(),
        ];

        match Command::set_global_commands(&ctx.http, register_commands).await {
            Ok(_) => info!("Successfully registered application commands"),
            Err(e) => error!("Failed to register application commands: {}", e),
        }
    }

    async fn interaction_create(&self, ctx: Context, interaction: Interaction) {
        if let Interaction::Command(command) = interaction {
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
                let response = CreateInteractionResponse::Message(
                    CreateInteractionResponseMessage::new()
                        .content("An error occurred while processing the command.")
                        .ephemeral(true)
                );
                let _ = command.create_response(&ctx.http, response).await;
            }
        }
    }

    async fn message(&self, ctx: Context, msg: Message) {
        if msg.author.bot {
            return;
        }

        let http = ctx.http.clone();

        if self.intent_matcher.should_stop_conversation(&msg.content, msg.author.id, msg.channel_id, &self.active_conversations) {
            self.active_conversations.remove(&msg.channel_id);
            if let Err(e) = msg.reply(&http, "Alright! Feel free to reach out anytime you need help with Roblox development! 👋").await {
                error!("Failed to send stop confirmation: {}", e);
            }
            return;
        }
        
        let should_respond = self.gemini_client.should_respond_to_message(
            &msg.content,
            &self.config.bot_name,
            msg.author.id,
            msg.channel_id,
            &self.active_conversations,
        );

        if should_respond {
            let is_existing_active_convo_for_user = self.active_conversations.get(&msg.channel_id)
                .map_or(false, |user| *user.value() == msg.author.id);

            if !is_existing_active_convo_for_user {
                self.active_conversations.insert(msg.channel_id, msg.author.id);
            }

            let _typing_guard = msg.channel_id.start_typing(&http);
            
            match self.gemini_client.generate_response(&msg.content, &msg.author).await {
                Ok(response) => {
                    if let Err(e) = msg.reply(&http, response).await {
                        error!("Failed to send AI response: {}", e);
                    }
                }
                Err(e) => {
                    error!("Failed to generate AI response: {}", e);
                    let fallback_message = if e.to_string().contains("timeout") {
                        "Sorry, I'm taking too long to respond. Please try again!"
                    } else if e.to_string().contains("API error") {
                        "I'm having some technical difficulties right now. Please try again later!"
                    } else {
                        "Sorry, I'm having trouble generating a response right now."
                    };
                    if let Err(e) = msg.reply(&http, fallback_message).await {
                        error!("Failed to send fallback AI response: {}", e);
                    }
                }
            }
        }
    }
}
