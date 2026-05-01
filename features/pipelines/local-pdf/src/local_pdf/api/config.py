"""Runtime config sourced from env vars (via pydantic-settings).

Token comes from `GOLDENS_API_TOKEN` so a single token works across the
goldens API and this pipeline (matches A-Plus.1's env-var name).
Pipeline-specific knobs use the `LOCAL_PDF_` prefix.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ApiConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    api_token: str = Field(min_length=1, validation_alias="GOLDENS_API_TOKEN")
    data_root: Path = Field(default=Path("data/raw-pdfs"), validation_alias="LOCAL_PDF_DATA_ROOT")
    log_level: Literal["debug", "info", "warning", "error"] = Field(
        default="info", validation_alias="LOCAL_PDF_LOG_LEVEL"
    )
    yolo_weights: Path | None = Field(default=None, validation_alias="LOCAL_PDF_YOLO_WEIGHTS")
    mineru_binary: str = Field(default="mineru", validation_alias="LOCAL_PDF_MINERU_BIN")
