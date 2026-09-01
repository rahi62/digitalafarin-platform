from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    platform_agent_token: str
    agent_service_prefixes: str = "digitalafarin-"

    @property
    def service_prefixes(self) -> tuple[str, ...]:
        raw = [item.strip() for item in self.agent_service_prefixes.split(",")]
        return tuple(item for item in raw if item)


@lru_cache
def get_settings() -> Settings:
    return Settings()
