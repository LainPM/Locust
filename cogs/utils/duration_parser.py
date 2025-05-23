import re
import datetime

def parse_duration(duration_str: str) -> datetime.timedelta | None:
    if not duration_str:
        return None
    duration_str = duration_str.lower()
    regex = re.compile(
        r"((?P<days>\d+?)d(?:ays?)? ?)?"
        r"((?P<hours>\d+?)h(?:ours?)? ?)?"
        r"((?P<minutes>\d+?)m(?:inutes?)? ?)?"
        r"((?P<seconds>\d+?)s(?:econds?)?)?"
    )
    parts = regex.match(duration_str)
    if not parts or not parts.group(0): # Check if any part of the regex matched
        return None
    
    time_params = {}
    for name, param in parts.groupdict().items():
        if param:
            time_params[name] = int(param)
    
    if not time_params: # No valid time units found
        return None
        
    return datetime.timedelta(**time_params)

def format_timedelta(delta: datetime.timedelta) -> str:
    if delta is None:
        return "Permanent"
        
    parts = []
    total_seconds = int(delta.total_seconds())

    if total_seconds < 0:
        return "Invalid duration"

    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60

    if days > 0: parts.append(f"{days}d")
    if hours > 0: parts.append(f"{hours}h")
    if minutes > 0: parts.append(f"{minutes}m")
    if seconds > 0 or not parts : parts.append(f"{seconds}s")

    return " ".join(parts) if parts else "0s"
