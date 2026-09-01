from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    control_plane_url: str = "http://127.0.0.1:8000"
    control_plane_token: str
    mcp_host: str = "127.0.0.1"
    mcp_port: int = 3060
    mcp_path: str = "/mcp"


@lru_cache
def get_settings() -> Settings:
    return Settings()
