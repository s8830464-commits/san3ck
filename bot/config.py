from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    TELEGRAM_BOT_TOKEN: str
    ADMIN_TELEGRAM_ID: int
    ALLOWED_TELEGRAM_IDS: str = "7338758544,816827728"
    DATABASE_URL: str = "sqlite+aiosqlite:///./notes.db"
    DEFAULT_NOTES_PER_PAGE: int = 5

    # Web Server Settings
    WEB_SERVER_HOST: str = "127.0.0.1"
    WEB_SERVER_PORT: int = 8080
    WEB_SITE_URL: str = "http://localhost:8080"

    # AI / LLM Settings (Free Groq, Gemini, OpenRouter)
    AI_API_KEY: str = ""
    AI_PROVIDER: str = "groq"  # "groq", "gemini", "openrouter", "openai"
    AI_MODEL: str = "qwen/qwen3.8-27b"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()

