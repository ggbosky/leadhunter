"""Konfigurace aplikace (načítá se z proměnných prostředí / souboru .env)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Project Two Lead Hunter"
    environment: str = "development"

    # --- Databáze & úložiště ---
    data_dir: Path = BACKEND_DIR / "data"
    database_url: str = ""  # výchozí: sqlite v data_dir

    # --- Zabezpečení API ---
    api_token: str = ""  # pokud je nastaven, API vyžaduje hlavičku Authorization: Bearer <token>
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # --- Automatizace ---
    scheduler_enabled: bool = True
    worker_enabled: bool = True
    worker_concurrency: int = 2
    worker_poll_seconds: float = 2.0

    # --- HTTP / crawling ---
    user_agent: str = "ProjectTwoLeadHunter/1.0 (+https://projectwo.com/; business website analysis)"
    http_timeout: float = 20.0
    max_page_bytes: int = 3_000_000
    per_domain_delay_seconds: float = 2.0
    max_pages_per_site: int = 5
    block_private_networks: bool = True

    # --- Playwright ---
    playwright_executable_path: str = ""
    screenshot_timeout_ms: int = 25_000
    screenshot_max_height: int = 6000

    # --- Konektory ---
    overpass_urls: str = (
        "https://overpass-api.de/api/interpreter,"
        "https://overpass.kumi.systems/api/interpreter,"
        "https://maps.mail.ru/osm/tools/overpass/api/interpreter,"
        "https://overpass.private.coffee/api/interpreter"
    )
    ares_base_url: str = "https://ares.gov.cz/ekonomicke-subjekty-v-be/rest"
    brave_api_key: str = ""
    google_cse_key: str = ""
    google_cse_cx: str = ""

    # --- AI ---
    text_provider: str = "auto"  # auto | ollama | anthropic | openai | none
    vision_provider: str = "auto"  # auto | ollama | anthropic | openai | none
    ollama_url: str = "http://localhost:11434"
    ollama_text_model: str = "qwen2.5:7b-instruct"
    ollama_vision_model: str = "qwen2.5vl:7b"
    ollama_timeout: float = 240.0
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-5-5"
    anthropic_vision_model: str = "claude-sonnet-5-5"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    openai_vision_model: str = "gpt-4o-mini"

    # --- Testy ---
    disable_network: bool = Field(default=False, description="Pro testy – zakáže síťové volání konektorů")

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            url = self.database_url.strip()
            # Neon / Supabase / Heroku dávají postgres:// nebo postgresql:// – použijeme ovladač psycopg 3
            for prefix in ("postgres://", "postgresql://"):
                if url.startswith(prefix):
                    return "postgresql+psycopg://" + url[len(prefix):]
            return url
        return f"sqlite:///{(self.data_dir / 'leadhunter.db').as_posix()}"

    @property
    def screenshot_dir(self) -> Path:
        return self.data_dir / "screenshots"

    @property
    def overpass_url_list(self) -> list[str]:
        return [u.strip() for u in self.overpass_urls.split(",") if u.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    s.screenshot_dir.mkdir(parents=True, exist_ok=True)
    return s
