from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "GoodToGreat-Gateway"
    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8080
    log_level: str = "INFO"

    # DeepBridge (existing integration — unchanged).
    deepseek_api_base_url: str = "http://127.0.0.1:8000"

    # Optional gateway API key. When set, all /v1/* routes require Bearer auth.
    gtg_api_key: str = ""

    # g4f in-process provider (replaces the Free-GPT4-WEB-API sidecar).
    g4f_enabled: bool = True
    # Force a specific g4f provider class name (e.g. "DDG", "Airforce").
    # Leave empty to let g4f auto-select the best available provider.
    g4f_provider: str = ""

    # Perchance / URV AI Chat (browser bridge via DrissionPage).
    # Off by default — requires chromium + DrissionPage 3.2.x.
    perchance_enabled: bool = False
    perchance_generator: str = "urv-ai-chat"
    perchance_generator_url: str = "https://perchance.org/urv-ai-chat"
    perchance_chrome_path: str = "/data/data/com.termux/files/usr/lib/chromium/chrome"
    perchance_port: int = 9333
    perchance_user_data_dir: str = "~/.cache/perchance-profile"
    perchance_log_path: str = "~/.config/perchance/chrome.log"
    perchance_timeout_seconds: float = 120.0

    # GPTBridge: legacy external-sidecar mode (kept for backward compatibility).
    # Enable only if you are running a separate Free-GPT4-WEB-API process.
    gptbridge_enabled: bool = False
    gptbridge_base_url: str = "http://127.0.0.1:5500"
    gptbridge_timeout_seconds: float = 90.0

    # Local Ollama server — no API key required.
    ollama_enabled: bool = True
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_timeout_seconds: float = 180.0

    request_timeout_seconds: float = 120.0

    # Token-bucket rate limiting for /v1/* routes.
    rate_limit_enabled: bool = True
    rate_limit_requests: int = 30
    rate_limit_window_seconds: float = 60.0

    # Reject chat bodies above this size (bytes) before parsing, to bound memory/CPU use.
    max_request_body_bytes: int = 1_000_000

    # --- Onyx / FreeTheAI ---
    onyx_base_url: str = "https://api.freetheai.org/v1"
    onyx_api_key: str = ""
    onyx_timeout: int = 120

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()

