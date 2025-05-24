use dashmap::DashMap;
use serenity::model::id::{ChannelId, UserId};
use std::sync::Arc;

#[derive(Debug, Clone)]
pub enum Intent {
    StopConversation,
    StartConversation,
    AskForHelp,
    ThankYou,
    CheckPing,
    CheckServerInfo,
    CheckMemberCount,
    AskUsername,
    AskNickname,
    AskUserId,
    AskBio,
    AskAvatar,
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
                (vec!["what is the ping", "check ping", "ping", "latency", "bot ping", "what's the ping"], Intent::CheckPing),
                (vec!["server info", "serverinfo", "guild info", "about this server", "server details"], Intent::CheckServerInfo),
                (vec!["member count", "how many members", "membercount", "total members"], Intent::CheckMemberCount),
                (vec!["what is my username", "my username", "what's my username", "my name"], Intent::AskUsername),
                (vec!["what is my nickname", "my nickname", "what's my nickname", "my nick"], Intent::AskNickname),
                (vec!["what is my id", "my user id", "what's my id", "my userid"], Intent::AskUserId),
                (vec!["what is my bio", "my bio", "what's my bio", "my about me"], Intent::AskBio),
                (vec!["my avatar", "what's my avatar", "my profile picture", "my pfp"], Intent::AskAvatar),
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
