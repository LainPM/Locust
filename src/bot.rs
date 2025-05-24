use serenity::async_trait;
use serenity::builder::{CreateInteractionResponse, CreateInteractionResponseMessage, CreateMessage, CreateEmbed};
use serenity::client::{Context, EventHandler};
use serenity::model::gateway::Ready;
use serenity::model::id::{ChannelId, UserId};
use serenity::model::prelude::*;
use serenity::prelude::*;
use std::sync::Arc;
use dashmap::DashMap;
use tracing::{error, info, debug};
use chrono::Utc;

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
        info!("Creating new Handler instance");
        let gemini_client = GeminiClient::new(config.gemini_api_key.clone());
        Self {
            config,
            gemini_client,
            active_conversations: Arc::new(DashMap::new()),
            intent_matcher: IntentMatcher::new(),
        }
    }

    async fn handle_command_intent(&self, ctx: &Context, msg: &Message, intent: Intent) -> Result<(), serenity::Error> {
        let http = ctx.http.clone();
        info!("Handling command intent: {:?}", intent);
        
        match intent {
            Intent::CheckPing => {
                let start = std::time::Instant::now();
                let typing_msg = msg.channel_id.say(&http, "Pinging...").await?;
                let api_latency = start.elapsed().as_millis();
                
                let ws_latency = ctx.shard.lock().await
                    .latency()
                    .map(|d| d.as_millis())
                    .unwrap_or(0);
                
                let embed = CreateEmbed::new()
                    .title("🏓 Pong!")
                    .color(0x57F287)
                    .field("Latency", format!("{}ms", api_latency), true)
                    .field("WebSocket", format!("{}ms", ws_latency), true)
                    .timestamp(Utc::now());
                
                typing_msg.delete(&http).await.ok();
                msg.reply(&http, CreateMessage::new().embed(embed)).await?;
            },
            Intent::CheckServerInfo => {
                if let Some(guild_id) = msg.guild_id {
                    if let Some(guild) = ctx.cache.guild(guild_id) {
                        let guild = guild.clone();
                        let owner = guild.owner_id.to_user(&http).await.map_or("Unknown".to_string(), |u| u.tag());
                        
                        let embed = CreateEmbed::new()
                            .title(format!("📊 {}", guild.name))
                            .color(0x5865F2)
                            .thumbnail(guild.icon_url().unwrap_or_default())
                            .field("👑 Owner", owner, true)
                            .field("👥 Members", format!("{} members", guild.member_count), true)
                            .field("📅 Created", guild.id.created_at().format("%b %d, %Y"), true)
                            .field("🎭 Roles", guild.roles.len().to_string(), true)
                            .field("💬 Channels", guild.channels.len().to_string(), true)
                            .field("🆔 Server ID", format!("`{}`", guild.id), false)
                            .timestamp(Utc::now());
                        
                        msg.reply(&http, CreateMessage::new().embed(embed)).await?;
                    }
                }
            },
            Intent::CheckMemberCount => {
                if let Some(guild_id) = msg.guild_id {
                    if let Some(guild) = ctx.cache.guild(guild_id) {
                        let guild = guild.clone();
                        let embed = CreateEmbed::new()
                            .title("👥 Member Statistics")
                            .color(0x57F287)
                            .field("🏠 Server", guild.name, false)
                            .field("📊 Total Members", format!("**{}** members", guild.member_count), false)
                            .timestamp(Utc::now());
                        
                        msg.reply(&http, CreateMessage::new().embed(embed)).await?;
                    }
                }
            },
            Intent::AskUsername => {
                msg.reply(&http, format!("Your username is: **{}**", msg.author.tag())).await?;
            },
            Intent::AskNickname => {
                if let Some(guild_id) = msg.guild_id {
                    let nickname = msg.author.nick_in(&http, guild_id).await.unwrap_or_else(|| msg.author.name.clone());
                    msg.reply(&http, format!("Your nickname in this server is: **{}**", nickname)).await?;
                } else {
                    msg.reply(&http, format!("Your username is: **{}** (no nickname in DMs)", msg.author.name)).await?;
                }
            },
            Intent::AskUserId => {
                msg.reply(&http, format!("Your user ID is: `{}`", msg.author.id)).await?;
            },
            Intent::AskBio => {
                msg.reply(&http, "I cannot access user bios through the Discord API. You can check your bio in your Discord profile settings!").await?;
            },
            Intent::AskAvatar => {
                let avatar_url = msg.author.avatar_url().unwrap_or_else(|| msg.author.default_avatar_url());
                let embed = CreateEmbed::new()
                    .title(format!("{}'s Avatar", msg.author.name))
                    .image(avatar_url)
                    .color(0x5865F2);
                msg.reply(&http, CreateMessage::new().embed(embed)).await?;
            },
            _ => Ok(())
        }?;
        Ok(())
    }
}

#[async_trait]
impl EventHandler for Handler {
    async fn ready(&self, ctx: Context, ready: Ready) {
        info!("{} is connected and ready!", ready.user.name);
        info!("Bot ID: {}", ready.user.id);
        info!("Connected to {} guilds", ready.guilds.len());
        
        let register_commands = vec![
            commands::register_ping(),
            commands::register_serverinfo(),
            commands::register_membercount(),
        ];

        match Command::set_global_commands(&ctx.http, register_commands).await {
            Ok(commands) => info!("Successfully registered {} application commands", commands.len()),
            Err(e) => error!("Failed to register application commands: {}", e),
        }
    }

    async fn interaction_create(&self, ctx: Context, interaction: Interaction) {
        if let Interaction::Command(command) = interaction {
            info!("Received command: {}", command.data.name);
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

        debug!("Received message from {}: {}", msg.author.tag(), msg.content);
        let http = ctx.http.clone();

        if self.intent_matcher.should_stop_conversation(&msg.content, msg.author.id, msg.channel_id, &self.active_conversations) {
            info!("Stopping conversation with {} in channel {}", msg.author.tag(), msg.channel_id);
            self.active_conversations.remove(&msg.channel_id);
            if let Err(e) = msg.reply(&http, "Alright! Feel free to reach out anytime you need help with Roblox development! 👋").await {
                error!("Failed to send stop confirmation: {}", e);
            }
            return;
        }

        if let Some(intent) = self.intent_matcher.detect_intent(&msg.content) {
            match intent {
                Intent::CheckPing | Intent::CheckServerInfo | Intent::CheckMemberCount | 
                Intent::AskUsername | Intent::AskNickname | Intent::AskUserId | 
                Intent::AskBio | Intent::AskAvatar => {
                    if let Err(e) = self.handle_command_intent(&ctx, &msg, intent).await {
                        error!("Failed to handle command intent: {}", e);
                    }
                    return;
                },
                _ => {}
            }
        }
        
        let should_respond = self.gemini_client.should_respond_to_message(
            &msg.content,
            &self.config.bot_name,
            msg.author.id,
            msg.channel_id,
            &self.active_conversations,
        );

        if should_respond {
            info!("Responding to message from {} in channel {}", msg.author.tag(), msg.channel_id);
            let is_existing_active_convo_for_user = self.active_conversations.get(&msg.channel_id)
                .map_or(false, |user| *user.value() == msg.author.id);

            if !is_existing_active_convo_for_user {
                self.active_conversations.insert(msg.channel_id, msg.author.id);
                info!("Started new conversation with {} in channel {}", msg.author.tag(), msg.channel_id);
            }

            let _typing_guard = msg.channel_id.start_typing(&http);
            
            match self.gemini_client.generate_response(&msg.content, &msg.author).await {
                Ok(response) => {
                    debug!("Generated AI response: {}", response);
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
