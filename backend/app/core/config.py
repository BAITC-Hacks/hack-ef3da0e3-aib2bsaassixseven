from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Tirke API"
    frontend_origin: str = "http://localhost:3000"
    supabase_url: str = "https://example.supabase.co"
    supabase_publishable_key: str = "replace-with-publishable-key"
    supabase_jwt_audience: str = "authenticated"


@lru_cache
def get_settings() -> Settings:
    return Settings()
