use reqwest::Client;
use serde_json::{json, Value};
use anyhow::{Result, Context};
use dashmap::DashMap;
use serenity::model::id::{ChannelId, UserId};
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

    pub async fn generate_response(&self, prompt: &str) -> Result<String> {
        let url = format!(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={}",
            self.api_key
        );

        let payload = json!({
            "contents": [{
                "parts": [{
                    "text": format!("You are Axis, a helpful Discord bot. Respond to this message in a friendly and concise way (max 2000 characters): {}", prompt)
                }]
            }]
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

        // Ensure response fits Discord's message limit
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
        // Check for active conversation
        if let Some(active_user_id) = active_conversations.get(&channel_id) {
            if *active_user_id == author_id {
                return true; // Active conversation with this user in this channel
            }
        }

        // If no active conversation, check for trigger phrases
        let content_lower = content.to_lowercase().trim().to_string();
        let bot_name_lower = bot_name.to_lowercase();
        
        let triggers = [
            format!("hey {}", bot_name_lower),
            format!("hi {}", bot_name_lower),
            format!("hello {}", bot_name_lower),
            format!("yo {}", bot_name_lower),
            format!("hey {},", bot_name_lower),
            format!("hi {},", bot_name_lower),
            format!("hello {},", bot_name_lower),
        ];
        
        if triggers.iter().any(|trigger| content_lower.starts_with(trigger)) {
            return true; // Trigger phrase detected
        }

        false // Neither active conversation nor trigger phrase
    }
}
