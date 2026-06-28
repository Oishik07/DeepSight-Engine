from pathlib import Path
from pydantic_settings import BaseSettings
from typing import Optional

# Resolve the project root dynamically to guarantee the .env file is found
ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT_DIR / ".env"

class Settings(BaseSettings):
    PROJECT_NAME: str = "Deep Research Agent"
    DATABASE_URL: str = "sqlite+aiosqlite:///./research.db" # Defaulting to SQLite for easy V1 dev, can be overriden
    # If the user sets postgres: postgresql+asyncpg://user:pass@localhost:5432/db
    GOOGLE_CLIENT_ID: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    OPENROUTER_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    GOOGLE_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    TAVILY_API_KEY: Optional[str] = None

    class Config:
        env_file = str(ENV_FILE)

settings = Settings()
