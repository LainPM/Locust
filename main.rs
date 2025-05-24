use serenity::{
    async_trait,
    framework::standard::{
        macros::{command, group},
        CommandResult, StandardFramework,
    },
    http::Http,
    model::{
        channel::Message,
        gateway::Ready,
        id::GuildId,
        interactions::{
            application_command::{ApplicationCommand, ApplicationCommandOptionType},
            Interaction, InteractionResponseType,
        },
    },
    prelude::*,
};
use std::env;
use dotenv::dotenv;
use chrono::Utc;
use serde::{Deserialize, Serialize};

#[derive(Serialize)]
struct GeminiRequest {
    contents: Vec<Content>,
}

#[derive(Serialize)]
struct Content {
    parts: Vec<Part>,
}

#[derive(Serialize)]
struct Part {
    text: String,
}

#[derive(Deserialize)]
struct GeminiResponse {
    candidates: Vec<Candidate>,
}

#[derive(Deserialize)]
struct Candidate {
    content: CandidateContent,
}

#[derive(Deserialize)]
struct CandidateContent {
    parts: Vec<ResponsePart>,
}

#[derive(Deserialize)]
struct ResponsePart {
    text: String,
}

struct Handler;

#[async_trait]
impl EventHandler for Handler {
    async fn ready(&self, ctx: Context, ready: Ready) {
        println!("{} is connected!", ready.user.name);
        
        // Register slash commands
        let guild_id = GuildId(env::var("GUILD_ID")
            .expect("Expected GUILD_ID in environment")
            .parse()
            .expect("GUILD_ID must be an integer"));

        let commands = GuildId::set_application_commands(&guild_id, &ctx.http, |commands| {
            commands
                .create_application_command(|command| {
                    command.name("ping").description("Check bot latency")
                })
                .create_application_command(|command| {
                    command.name("serverinfo").description("Get server information")
                })
                .create_application_command(|command| {
                    command.name("membercount").description("Get server member count")
                })
        })
        .await;

        println!("Registered slash commands: {:#?}", commands);
    }

    async fn interaction_create(&self, ctx: Context, interaction: Interaction) {
        if let Interaction::ApplicationCommand(command) = interaction {
            let content = match command.data.name.as_str() {
                "ping" => {
                    let shard = ctx.shard_id;
                    let latency = ctx.shard.latency()
                        .map(|l| format!("{}ms", l.as_millis()))
                        .unwrap_or_else(|| "N/A".to_string());
                    format!("Pong! Latency: {}", latency)
                }
                "serverinfo" => {
                    if let Some(guild_id) = command.guild_id {
                        if let Ok(guild) = guild_id.to_partial_guild(&ctx.http).await {
                            format!(
                                "**Server Info**\n\
                                Name: {}\n\
                                ID: {}\n\
                                Owner: <@{}>\n\
                                Members: {}\n\
                                Created: <t:{}:F>\n\
                                Boost Level: {}",
                                guild.name,
                                guild.id,
                                guild.owner_id,
                                guild.member_count.unwrap_or(0),
                                guild.id.created_at().unix_timestamp(),
                                guild.premium_tier
                            )
                        } else {
                            "Failed to get server info".to_string()
                        }
                    } else {
                        "This command can only be used in a server".to_string()
                    }
                }
                "membercount" => {
                    if let Some(guild_id) = command.guild_id {
                        if let Ok(guild) = guild_id.to_partial_guild(&ctx.http).await {
                            format!("This server has **{}** members", guild.member_count.unwrap_or(0))
                        } else {
                            "Failed to get member count".to_string()
                        }
                    } else {
                        "This command can only be used in a server".to_string()
                    }
                }
                _ => "Unknown command".to_string(),
            };

            if let Err(why) = command
                .create_interaction_response(&ctx.http, |response| {
                    response
                        .kind(InteractionResponseType::ChannelMessageWithSource)
                        .interaction_response_data(|message| message.content(content))
                })
                .await
            {
                println!("Cannot respond to slash command: {}", why);
            }
        }
    }

    async fn message(&self, ctx: Context, msg: Message) {
        if msg.author.bot {
            return;
        }

        let content = msg.content.to_lowercase();
        if content.starts_with("hey axis") || content.starts_with("hi axis") || content.starts_with("hello axis") {
            let _ = msg.channel_id.start_typing(&ctx.http);
            
            if let Ok(response) = get_gemini_response(&msg.content).await {
                if let Err(why) = msg.channel_id.say(&ctx.http, response).await {
                    println!("Error sending message: {:?}", why);
                }
            } else {
                let _ = msg.channel_id.say(&ctx.http, "Sorry, I'm having trouble processing that right now.").await;
            }
        }
    }
}

async fn get_gemini_response(prompt: &str) -> Result<String, Box<dyn std::error::Error + Send + Sync>> {
    let api_key = env::var("GEMINI_API_KEY")?;
    let url = format!(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={}",
        api_key
    );

    let request_body = GeminiRequest {
        contents: vec![Content {
            parts: vec![Part {
                text: prompt.to_string(),
            }],
        }],
    };

    let client = reqwest::Client::new();
    let response = client
        .post(&url)
        .json(&request_body)
        .send()
        .await?;

    let gemini_response: GeminiResponse = response.json().await?;
    
    if let Some(candidate) = gemini_response.candidates.first() {
        if let Some(part) = candidate.content.parts.first() {
            return Ok(part.text.clone());
        }
    }

    Err("No response from Gemini".into())
}

#[tokio::main]
async fn main() {
    dotenv().ok();

    let token = env::var("DISCORD_TOKEN").expect("Expected DISCORD_TOKEN in environment");
    let intents = GatewayIntents::GUILD_MESSAGES
        | GatewayIntents::DIRECT_MESSAGES
        | GatewayIntents::MESSAGE_CONTENT
        | GatewayIntents::GUILDS;

    let mut client = Client::builder(&token, intents)
        .event_handler(Handler)
        .await
        .expect("Error creating client");

    if let Err(why) = client.start().await {
        println!("Client error: {:?}", why);
    }
}
