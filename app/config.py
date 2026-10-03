"""Application settings loaded from environment / .env (pydantic-settings)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "dev"
    mock_mode: bool = True
    secret_key: str = "change-me"
    log_level: str = "INFO"
    tz: str = "Europe/London"

    database_url: str = f"sqlite:///{ROOT / 'data' / 'dealfinder.db'}"

    anthropic_api_key: str = ""
    claude_model: str = "claude-opus-5-5"

    ebay_client_id: str = ""
    ebay_client_secret: str = ""
    ebay_marketplace_id: str = "EBAY_GB"
    ebay_env: str = "production"
    ebay_sell_oauth_token: str = ""
    ebay_marketplace_insights_enabled: bool = False

    notifier: str = "mock"
    ntfy_server: str = "https://ntfy.sh"
    ntfy_topic: str = ""
    ntfy_token: str = ""
    pushover_user_key: str = ""
    pushover_app_token: str = ""
    dashboard_base_url: str = "http://localhost:8000"

    browser_profile_dir: str = str(ROOT / "data" / "browser_profile")
    browser_headless: bool = True
    browser_sources_enabled: bool = False
    browser_min_delay_s: int = 45
    browser_max_delay_s: int = 120
    browser_max_page_loads_per_hour: int = 40
    browser_quiet_hours: str = "23-07"

    scheduler_enabled: bool = True
    source_poll_interval_min: int = 15
    digest_interval_min: int = 30
    daily_summary_hour: int = 8

    passed_deal_retention_days: int = 90

    @property
    def is_test(self) -> bool:
        return self.app_env == "test"

    @property
    def llm_is_mock(self) -> bool:
        return self.mock_mode or not self.anthropic_api_key

    @property
    def ebay_is_mock(self) -> bool:
        return self.mock_mode or not (self.ebay_client_id and self.ebay_client_secret)


@lru_cache
def get_settings() -> Settings:
    return Settings()
