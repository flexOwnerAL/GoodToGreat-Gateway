from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "GoodToGreat-Gateway"
    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8080
    log_level: str = "INFO"
    deepseek_api_base_url: str = "http://127.0.0.1:8000"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
