from slowapi import Limiter
from slowapi.util import get_remote_address
import logging
from .config import settings # Import the settings object

logger = logging.getLogger(__name__)

# Get REDIS_URL from the centralized settings
storage_uri = settings.REDIS_URL

if not storage_uri:
    logger.warning("REDIS_URL is not set in environment or .env file. Limiter will use IN-MEMORY storage (suitable for development).")
    limiter = Limiter(key_func=get_remote_address)
else:
    logger.info(f"REDIS_URL found ('{storage_uri}'). Limiter will use Redis as storage backend (suitable for production).")
    limiter = Limiter(key_func=get_remote_address, storage_uri=storage_uri)

# Optional: Log the final state
# This check is a bit internal to slowapi's structure, might need adjustment if slowapi changes
try:
    if "memory" in str(type(limiter.storage._storage)).lower(): # Accessing internal _storage
        logger.info("Limiter confirmed to be using IN-MEMORY storage.")
    elif "redis" in str(type(limiter.storage._storage)).lower(): # Accessing internal _storage
         logger.info("Limiter confirmed to be using REDIS storage.")
    else:
        logger.info("Limiter is using a persistent storage backend (details may vary).")
except AttributeError:
    logger.info("Limiter storage type check not straightforward, but configuration applied.")