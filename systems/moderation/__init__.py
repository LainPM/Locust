# systems/moderation/__init__.py
from systems.base_system import System
from .filter import ContentFilter
from .anti_raid import RaidProtection
from .anti_spam import SpamProtection
from .punishment import PunishmentManager
from .purge import PurgeHandler  # Add this import

class ModerationSystem(System):
    """Comprehensive content moderation system"""
    
    def __init__(self, bot):
        super().__init__(bot)
        
        # Components
        self.filter = ContentFilter(self)
        self.raid_protection = RaidProtection(self)
        self.spam_protection = SpamProtection(self)
        self.punishments = PunishmentManager(self)
        self.purge_handler = PurgeHandler(self)  # Add this component
        
        # Settings cache
        self.filter_settings_cache = {}  # Guild ID -> settings
        self.raid_settings_cache = {}    # Guild ID -> settings
        
        # Shared resources - caches and trackers
        self.message_cache = {}          # User ID -> list of recent messages
        self.violation_counts = {}       # Guild ID -> User ID -> violation count
        self.processing_users = set()    # Users currently being processed
        self.muted_users = {}            # User ID -> unmute time
        
    # The rest of the class remains the same
