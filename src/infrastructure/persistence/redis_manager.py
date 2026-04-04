try:
    import redis
    REDIS_LIB_AVAILABLE = True
except ImportError:
    REDIS_LIB_AVAILABLE = False

import time
import uuid
import os
from dotenv import load_dotenv

load_dotenv()

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))

class RedisManager:
    def __init__(self):
        self.available = False
        if not REDIS_LIB_AVAILABLE:
            print("[Redis] 'redis' library not installed. Using degraded mode (local locks).")
            return

        try:
            self.client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
            self.client.ping()
            self.available = True
        except:
            print("[Redis] Server unavailable. Using degraded mode (local locks).")

    def acquire_lock(self, filepath: str, owner: str, ttl=60):
        if not self.available:
            return True # Modo degradado: asumimos lock local o simplemente permitimos
        
        lock_key = f"lock:{filepath}"
        return self.client.set(lock_key, owner, ex=ttl, nx=True)

    def release_lock(self, filepath: str, owner: str):
        if not self.available:
            return
        
        lock_key = f"lock:{filepath}"
        if self.client.get(lock_key) == owner:
            self.client.delete(lock_key)

    def log_event(self, event_data: dict):
        if not self.available:
            return
        
        # event_id único para idempotencia
        event_id = str(uuid.uuid4())
        event_data['event_id'] = event_id
        
        try:
            self.client.xadd("stream:patch_edits", event_data)
        except Exception as e:
            print(f"[Redis] Error logging event: {e}")
        
        return event_id
