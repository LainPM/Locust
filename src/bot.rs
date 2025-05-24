use serenity::async_trait;
use serenity::builder::{CreateInteractionResponse, CreateInteractionResponseMessage};
use serenity::client::{Context, EventHandler};
// Command, Interaction, InteractionResponseType are expected to be in prelude
use serenity::model::gateway::Ready;
use serenity::model::id::{ChannelId, UserId}; // Added for explicitness
use serenity::model::prelude::*;
use serenity::prelude::*;
use std::sync::Arc;
use dashmap::DashMap; // Added dashmap
use tracing::{error, info};

use crate::ai::GeminiClient;
use crate::commands;
use crate::config::Config;

pub struct ShardManagerContainer;

impl TypeMapKey for ShardManagerContainer {
    type Value = Arc<serenity::gateway::ShardManager>;
}

pub struct Handler {
    pub config: Config,
    pub gemini_client: GeminiClient,
    pub active_conversations: Arc<DashMap<ChannelId, UserId>>, // Added field
}

impl Handler {
    pub fn new(config: Config) -> Self {
        let gemini_client = GeminiClient::new(config.gemini_api_key.clone());
        Self {
            config,
            gemini_client,
            active_conversations: Arc::new(DashMap::new()), // Initialized field
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

        // Assuming Command is in prelude (e.g. serenity::model::prelude::Command)
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

        let http = ctx.http.clone(); // Clone http for potential use in replies

        // Define stop phrases
        let stop_phrases = [
            "stop", "goodbye", "bye axis", "that's all", "nevermind", "thanks bye",
            "thank you goodbye", "ok stop", "alright stop",
        ];
        let content_lower = msg.content.to_lowercase();

        // Check for stop phrases first
        for phrase in stop_phrases.iter() {
            if content_lower.contains(phrase) { // Using contains for more flexibility
                if let Some(active_user) = self.active_conversations.get(&msg.channel_id) {
                    if *active_user.value() == msg.author.id {
                        self.active_conversations.remove(&msg.channel_id);
                        if let Err(e) = msg.channel_id.say(&http, "Alright, let me know if you need anything else!").await {
                            error!("Failed to send stop confirmation: {}", e);
                        }
                        return; // Stop processing further for this message
                    }
                }
                // If a stop phrase is said but no active conversation with this user,
                // or if it's a general stop phrase not tied to an active convo,
                // we might not need to do anything or could have a generic non-committal reply.
                // For now, if it matches a stop phrase and they were the active user, we stop.
                // Otherwise, if they say "stop" but aren't in a convo, it might be a trigger for a new one if "stop" is part of a longer sentence.
                // The current logic for should_respond_to_message will handle if "stop" (as part of a sentence) can trigger.
                // If a stop phrase is detected AND they are the active user, we definitely stop and return.
            }
        }
        
        // Determine if the bot should respond (active convo or trigger)
        let should_respond = self.gemini_client.should_respond_to_message(
            &msg.content,
            &self.config.bot_name,
            msg.author.id,
            msg.channel_id,
            &self.active_conversations,
        );

        if should_respond {
            // If it's a new conversation (trigger phrase was used and no active convo for this channel yet,
            // or active convo was for a different user which should_respond_to_message would have filtered out unless it's a new trigger)
            // then add this user and channel to active_conversations.
            if !self.active_conversations.contains_key(&msg.channel_id) {
                 // This check ensures we only insert if there wasn't an active conversation already
                 // for this channel (which implies a trigger phrase started this interaction).
                 // Or if the active user was different and the new message is a trigger.
                 // should_respond_to_message already handles the logic:
                 //  - if active_conversations has channel_id and user_id matches -> true
                 //  - if trigger phrase -> true
                 // So, if should_respond is true, and it wasn't because of an existing active convo for this user, it's a new one.
                 
                 // A more direct way to check if it's a *newly triggered* conversation for *this specific user*:
                 // Check if it's a trigger phrase AND ( (no active convo in channel) OR (active convo in channel is for different user) )
                 // However, the current logic in should_respond handles this well:
                 // it returns true if (active convo with user) OR (trigger phrase).
                 // So if should_respond is true, we need to ensure the map is updated if it was a trigger.
                 
                 // If should_respond is true, and the reason it's true is *not* because
                 // self.active_conversations.get(&msg.channel_id) matched msg.author.id,
                 // then it must be a trigger phrase starting a new conversation.
                 let is_existing_active_convo_for_user = self.active_conversations.get(&msg.channel_id)
                    .map_or(false, |user| *user.value() == msg.author.id);

                if !is_existing_active_convo_for_user {
                    self.active_conversations.insert(msg.channel_id, msg.author.id);
                    // Optional: Send a greeting like "Hey there! How can I help?"
                    // For now, let the first AI response serve as the greeting.
                }
            } // If it *is* an existing active convo for this user, the map is already correct.


            let _typing_guard = msg.channel_id.start_typing(&http); // RAII guard
            
            match self.gemini_client.generate_response(&msg.content).await {
                Ok(response) => {
                    if let Err(e) = msg.channel_id.say(&http, response).await {
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
                    if let Err(e) = msg.channel_id.say(&http, fallback_message).await {
                        error!("Failed to send fallback AI response: {}", e);
                    }
                }
            }
        }
    }
}
