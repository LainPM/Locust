from botMain.dependencies import (
    asyncio,
    discord,
    traceback
)

class SyncHandler():
    async def sync_direct(self, command_data, guild_id=None, timeout=10.0):
        """Sync a command directly using Discord's API with timeout"""
        # Create a task for the sync operation
        sync_task = asyncio.create_task(self._sync_request(command_data, guild_id))
        
        try:
            # Wait for the task with a timeout
            return await asyncio.wait_for(sync_task, timeout=timeout)
        except asyncio.TimeoutError:
            # Task took too long, cancel it
            sync_task.cancel()
            print(f"Command sync timed out after {timeout} seconds for command: {command_data.get('name', 'unknown')}")
            return False, TimeoutError(f"Sync operation timed out after {timeout} seconds")
        
    async def _sync_request(self, command_data, guild_id=None):
        """Internal method to make the actual sync request"""
        try:
            # Get application ID
            application_id = self.application.id
            
            if guild_id:
                # Guild-specific endpoint
                route = discord.http.Route(
                    'POST',
                    '/applications/{application_id}/guilds/{guild_id}/commands',
                    application_id=application_id,
                    guild_id=guild_id
                )
            else:
                # Global endpoint
                route = discord.http.Route(
                    'POST',
                    '/applications/{application_id}/commands',
                    application_id=application_id
                )
            
            result = await self.http.request(route, json=command_data)
            return True, result
        except discord.HTTPException as e:
            # Properly handle rate limits and other HTTP errors
            if e.status == 429:
                print(f"Rate limited syncing command: {command_data.get('name', 'unknown')}")
                print(f"Retry After: {e.retry_after} seconds")
                print(f"Headers: {e.response.headers if hasattr(e, 'response') else 'No headers'}")
            else:
                print(f"HTTP error syncing command: {e}")
                print(f"Status: {e.status}")
                print(f"Code: {e.code if hasattr(e, 'code') else 'No code'}")
                
            return False, e
        except Exception as e:
            print(f"Unexpected error syncing command: {e}")
            print(traceback.format_exc())
            return False, e