import asyncio
from typing import Any, Dict, Optional
import time

class SkillsManager:
    """
    SkillsManager with async TTL caching.
    """
    def __init__(self, ttl_seconds: int = 3600):
        self.ttl_seconds = ttl_seconds
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        
    async def get_skill(self, skill_name: str) -> Optional[Any]:
        """
        Retrieves a skill from the cache if it hasn't expired.
        """
        async with self._lock:
            if skill_name in self._cache:
                entry = self._cache[skill_name]
                if time.time() - entry['timestamp'] < self.ttl_seconds:
                    return entry['data']
                else:
                    del self._cache[skill_name]
        return None
        
    async def set_skill(self, skill_name: str, data: Any):
        """
        Saves a skill to the cache with the current timestamp.
        """
        async with self._lock:
            self._cache[skill_name] = {
                'data': data,
                'timestamp': time.time()
            }
            
    async def clear_cache(self):
        """Clears the entire cache."""
        async with self._lock:
            self._cache.clear()
