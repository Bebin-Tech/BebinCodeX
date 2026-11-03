from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=Path(__file__).resolve().parents[2] / '.env', extra='ignore')
    database_url: str = 'sqlite:///./devpilot.db'
    encryption_key: str = ''
    app_origin: str = 'http://localhost:3000'
    cookie_secure: bool = False
    ollama_url: str = 'http://localhost:11434'
    openai_url: str = 'https://api.openai.com/v1'
    anthropic_url: str = 'https://api.anthropic.com'
    gemini_url: str = 'https://generativelanguage.googleapis.com/v1beta/openai'
    groq_url: str = 'https://api.groq.com/openai/v1'
    deepseek_url: str = 'https://api.deepseek.com'
    compatible_url: str = ''


settings = Settings()
