from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    data_root: Path = Path("data")

    app_name: str = "Hackalem API"
    frontend_origin: str = "http://localhost:3000"
    supabase_url: str = "https://example.supabase.co"
    supabase_publishable_key: str = "replace-with-publishable-key"
    supabase_jwt_audience: str = "authenticated"
    gpu_api_url: str | None = None
    gpu_api_token: SecretStr | None = None
    gpu_api_timeout_seconds: float = 30.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
