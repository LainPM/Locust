from botMain.dependencies import (
    asyncio,
    datetime,
    discord,
    traceback
)

class CommandHandler():
    async def process_commands(self, message):
        if message.content.startswith(self.command_prefix):
            ctx = await self.get_context(message)
            if ctx.command is not None:
                # Check if this is a bot owner command
                is_owner_command = ctx.command.checks and any(check.__qualname__.startswith('is_owner') for check in ctx.command.checks)
                
                # Invoke the command
                await self.invoke(ctx)
                
                # If it's an owner command, delete the message after 5 seconds
                if is_owner_command and message.guild:
                    try:
                        await asyncio.sleep(5)
                        await message.delete()
                    except:
                        pass

    async def get_registered_commands(self, force_refresh=False):
        """Get all commands currently registered with Discord"""
        now = datetime.datetime.now()
        
        # Use cached result if available and recent (within last 5 minutes)
        if not force_refresh and self.last_command_fetch and (now - self.last_command_fetch).total_seconds() < 300:
            return self.registered_commands
        
        try:
            # Get application ID
            application_id = self.application.id
            
            # Global commands endpoint
            route = discord.http.Route(
                'GET',
                '/applications/{application_id}/commands',
                application_id=application_id
            )
            
            registered_commands = await self.http.request(route)
            
            # Update cache
            self.registered_commands = registered_commands
            self.last_command_fetch = now
            
            return registered_commands
        except discord.HTTPException as e:
            print(f"HTTP error fetching registered commands: {e}")
            # Return cached results if available
            return self.registered_commands if self.registered_commands else []
        except Exception as e:
            print(f"Unexpected error fetching registered commands: {e}")
            print(traceback.format_exc())
            return self.registered_commands if self.registered_commands else []

    def get_command_json(self, command):
        """Extract JSON data from a command"""
        data = {
            "name": command.name,
            "description": command.description
        }
        
        # Add options/parameters if present
        options = []
        for param in getattr(command, 'parameters', []):
            option = {
                "name": param.name,
                "description": param.description,
                "required": param.required,
                "type": param.type.value
            }
            
            # Add choices if any
            if hasattr(param, 'choices') and param.choices:
                option["choices"] = [
                    {"name": choice.name, "value": choice.value}
                    for choice in param.choices
                ]
            
            options.append(option)
        
        if options:
            data["options"] = options
        
        return data
    
    def is_command_synced(self, command, registered_commands):
        """Check if a command is already properly synced with Discord"""
        for reg_cmd in registered_commands:
            if reg_cmd["name"] == command.name:
                # Command exists, but we should also check if it needs updating
                # For simplicity, we'll just check the description and parameter count
                if reg_cmd["description"] != command.description:
                    return False
                
                # Check parameters
                cmd_params = getattr(command, 'parameters', [])
                reg_options = reg_cmd.get("options", [])
                
                if len(cmd_params) != len(reg_options):
                    return False
                
                # Command exists and looks similar enough
                return True
                
        # Command doesn't exist
        return False