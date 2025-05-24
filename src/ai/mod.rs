pub mod intents;

use reqwest::Client;
use serde_json::{json, Value};
use anyhow::{Result, Context};
use dashmap::DashMap;
use serenity::model::id::{ChannelId, UserId};
use serenity::model::prelude::User;
use std::sync::Arc;

pub struct GeminiClient {
    client: Client,
    api_key: String,
}

impl GeminiClient {
    pub fn new(api_key: String) -> Self {
        Self {
            client: Client::new(),
            api_key,
        }
    }

    pub async fn generate_response(&self, prompt: &str, user: &User) -> Result<String> {
        let url = format!(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={}",
            self.api_key
        );

        let user_context = format!(
            "User Info - Username: {}, ID: {}, Bot: {}",
            user.tag(),
            user.id,
            user.bot
        );

        let system_prompt = format!(
            "You are Axis, a helpful Discord bot specifically designed for a Roblox Development server. \
            Your primary purpose is to assist with Roblox game development, Luau scripting, and development best practices. \
            You have extensive knowledge about Roblox Studio, Roblox APIs, game design patterns, and optimization techniques. \
            Be friendly, concise (max 2000 characters), and helpful. When providing code examples, use Luau syntax. \
            Current user context: {}. \
            User message: {}",
            user_context, prompt
        );

        let payload = json!({
            "contents": [{
                "parts": [{
                    "text": system_prompt
                }]
            }],
            "generationConfig": {
                "temperature": 0.7,
                "topK": 40,
                "topP": 0.95,
                "maxOutputTokens": 800,
            }
        });

        let response = self.client
            .post(&url)
            .json(&payload)
            .timeout(std::time::Duration::from_secs(10))
            .send()
            .await
            .context("Failed to send request to Gemini API")?;

        if !response.status().is_success() {
            let status = response.status();
            let error_text = response.text().await.unwrap_or_default();
            return Err(anyhow::anyhow!("Gemini API error {}: {}", status, error_text));
        }

        let json: Value = response.json().await
            .context("Failed to parse Gemini API response")?;

        let text = json["candidates"][0]["content"]["parts"][0]["text"]
            .as_str()
            .unwrap_or("I'm having trouble generating a response right now.")
            .to_string();

        if text.len() > 2000 {
            Ok(format!("{}...", &text[..1997]))
        } else {
            Ok(text)
        }
    }

    pub fn should_respond_to_message(
        &self,
        content: &str,
        bot_name: &str,
        author_id: UserId,
        channel_id: ChannelId,
        active_conversations: &Arc<DashMap<ChannelId, UserId>>,
    ) -> bool {
        if let Some(active_user_id) = active_conversations.get(&channel_id) {
            if *active_user_id == author_id {
                return true;
            }
        }

        let content_lower = content.to_lowercase().trim().to_string();
        let bot_name_lower = bot_name.to_lowercase();
        
        let triggers = [
            format!("hey {}", bot_name_lower),
            format!("hi {}", bot_name_lower),
            format!("hello {}", bot_name_lower),
            format!("yo {}", bot_name_lower),
            format!("{} help", bot_name_lower),
            format!("@{}", bot_name_lower),
        ];
        
        triggers.iter().any(|trigger| content_lower.contains(trigger))
    }
}
