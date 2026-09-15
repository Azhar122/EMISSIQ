"""Central configuration. Every tunable number the engines use lives here so no
calculation downstream contains an unexplained constant."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# The .env sits at the repo root, two levels above services/api/.
REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # pydantic-settings loads env_file entries in order and later ones win,
        # so the example (defaults) goes first and the real .env overrides it.
        env_file=(REPO_ROOT / ".env.example", REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://emissiq:emissiq@localhost:5433/emissiq"

    # --- AI ---------------------------------------------------------------
    ai_provider_order: str = "groq,ollama,scripted"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"

    # --- Economics --------------------------------------------------------
    gas_price_omr_per_mmbtu: float = 1.500
    ch4_energy_mmbtu_per_kg: float = 0.05226  # LHV of methane, 50.0 MJ/kg
    display_currency: str = "OMR"
    usd_per_omr: float = 2.6008
    gwp100_ch4: float = 29.8  # IPCC AR6, fossil methane, 100-year
    gwp20_ch4: float = 82.5  # IPCC AR6, fossil methane, 20-year

    def model_post_init(self, __context) -> None:
        # Hosted Postgres (Render, Heroku, Supabase) hands out postgres:// or
        # postgresql:// URLs; SQLAlchemy needs the psycopg driver spelled out.
        url = self.database_url
        if url.startswith("postgres://"):
            url = "postgresql+psycopg://" + url[len("postgres://"):]
        elif url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://"):]
        object.__setattr__(self, "database_url", url)

    @property
    def provider_order(self) -> list[str]:
        return [p.strip() for p in self.ai_provider_order.split(",") if p.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
