from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "Deep Research Agent"
    DATABASE_URL: str = "sqlite+aiosqlite:///./research.db" # Defaulting to SQLite for easy V1 dev, can be overriden
    # If the user sets postgres: postgresql+asyncpg://user:pass@localhost:5432/db

    class Config:
        env_file = ".env"

settings = Settings()
