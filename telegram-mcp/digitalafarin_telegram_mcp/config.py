from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    control_plane_url: str = "http://127.0.0.1:9750"
    control_plane_token: str
    telegram_mcp_host: str = "127.0.0.1"
    telegram_mcp_port: int = 3061
    telegram_mcp_path: str = "/mcp"


@lru_cache
def get_settings() -> Settings:
    return Settings()
