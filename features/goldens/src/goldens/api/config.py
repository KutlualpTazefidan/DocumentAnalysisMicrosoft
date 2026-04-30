"""Runtime config sourced from `GOLDENS_*` env vars (via pydantic-settings).

Loaded once when create_app() builds the FastAPI instance; tests override
via monkeypatch.setenv before instantiating.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ApiConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GOLDENS_", extra="ignore")

    api_token: str = Field(min_length=1)
    data_root: Path = Path("outputs")
    log_level: Literal["debug", "info", "warning", "error"] = "info"
