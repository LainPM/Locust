use dashmap::DashMap;
use serenity::model::id::{ChannelId, UserId};
use std::sync::Arc;

#[derive(Debug, Clone)]
pub enum Intent {
    StopConversation,
    StartConversation,
    AskForHelp,
    ThankYou,
}

pub struct IntentMatcher {
    pub patterns: Vec<(Vec<&'static str>, Intent)>,
}

impl IntentMatcher {
    pub fn new() -> Self {
        Self {
            patterns: vec![
                (vec!["stop", "goodbye", "bye", "that's all", "nevermind", "done", "exit", "quit", "leave"], Intent::StopConversation),
                (vec!["hey", "hi", "hello", "yo", "sup", "help", "assist"], Intent::StartConversation),
                (vec!["how do i", "can you help", "what is", "explain", "show me", "teach me"], Intent::AskForHelp),
                (vec!["thanks", "thank you", "thx", "ty", "appreciated"], Intent::ThankYou),
            ],
        }
    }

    pub fn detect_intent(&self, content: &str) -> Option<Intent> {
        let content_lower = content.to_lowercase();
        
        for (patterns, intent) in &self.patterns {
            if patterns.iter().any(|&pattern| content_lower.contains(pattern)) {
                return Some(intent.clone());
            }
        }
        
        None
    }

    pub fn should_stop_conversation(&self, content: &str, user_id: UserId, channel_id: ChannelId, active_conversations: &Arc<DashMap<ChannelId, UserId>>) -> bool {
        if let Some(active_user) = active_conversations.get(&channel_id) {
            if *active_user.value() == user_id {
                if let Some(Intent::StopConversation) = self.detect_intent(content) {
                    return true;
                }
            }
        }
        false
    }
}
