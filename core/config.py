from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional, List, Union
import os # For potential path joining if needed

class Settings(BaseSettings):
    """
    Application settings.
    Values are loaded from environment variables and/or a .env file.
    When deployed, the 'server' directory becomes the project root.
    The .env file is expected to be at that root level.
    """
    # --- Core Settings ---
    DATABASE_URL: str
    API_V1_STR: str = "/api"
    PROJECT_NAME: str = "Quick Poll API"
    DEBUG_MODE: bool = False

    # --- Rate Limiter ---
    REDIS_URL: Optional[str] = None

    # --- CORS ---
    # Expects a comma-separated string in .env, e.g., "http://localhost:3000,http://127.0.0.1:3000"
    CORS_ALLOWED_ORIGINS_STR: Optional[str] = "" # Reads from .env

    @property
    def CORS_ALLOWED_ORIGINS(self) -> List[str]:
        if self.CORS_ALLOWED_ORIGINS_STR:
            return [origin.strip() for origin in self.CORS_ALLOWED_ORIGINS_STR.split(",") if origin.strip()]
        return []

    # --- .env file location ---
    # Pydantic resolves env_file relative to the Current Working Directory (CWD)
    # when the application starts. Since main.py and .env will be at the
    # root of the 'quick-poll-api' deployment (which is the current 'server' dir),
    # ".env" is the correct path.
    model_config = SettingsConfigDict(
        env_file=".env", # Looks for .env in the CWD (e.g., server/ or quick-poll-api/ root)
        extra='ignore',
        env_file_encoding='utf-8'
    )

settings = Settings()

# Example of how to use it for CORS in main.py:
# if settings.CORS_ALLOWED_ORIGINS:
#     app.add_middleware(
#         CORSMiddleware,
#         allow_origins=settings.CORS_ALLOWED_ORIGINS,
#         allow_credentials=True,
#         allow_methods=["*"],
#         allow_headers=["*"],
#     )