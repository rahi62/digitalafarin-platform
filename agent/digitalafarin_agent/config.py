from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Legacy local pull API. Optional once outbound mode is enabled.
    platform_agent_token: str | None = None

    # Outbound control-plane mode.
    platform_control_url: str | None = None
    platform_enrollment_token: str | None = None
    agent_token_path: Path = Path("/var/lib/digitalafarin-agent/agent.token")
    agent_heartbeat_interval_seconds: int = 15
    agent_name: str = "DigitalAfarin VPS"
    agent_service_prefixes: str = "digitalafarin-"

    @property
    def service_prefixes(self) -> tuple[str, ...]:
        raw = [item.strip() for item in self.agent_service_prefixes.split(",")]
        return tuple(item for item in raw if item)


@lru_cache
def get_settings() -> Settings:
    return Settings()
