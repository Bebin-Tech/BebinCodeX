from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator, model_validator


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
    vercel: bool = False
    vercel_url: str = ''
    vercel_project_production_url: str = ''
    sandbox_enabled: bool = False

    @field_validator('database_url')
    @classmethod
    def psycopg_url(cls, value):
        for prefix in ('postgres://', 'postgresql://'):
            if value.startswith(prefix):
                return 'postgresql+psycopg://' + value[len(prefix):]
        return value

    @model_validator(mode='after')
    def validate_cloud(self):
        if self.vercel and (not self.database_url.startswith('postgresql+psycopg://') or not self.encryption_key):
            raise ValueError('Vercel deployment requires PostgreSQL DATABASE_URL and ENCRYPTION_KEY')
        return self

    @property
    def allowed_origins(self):
        origins = {self.app_origin}
        if self.vercel:
            for host in (self.vercel_url, self.vercel_project_production_url):
                if host and '/' not in host and host.endswith('.vercel.app'):
                    origins.add('https://' + host)
        return origins


settings = Settings()
