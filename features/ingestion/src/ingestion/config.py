"""Document Intelligence configuration loaded from environment.

`IngestionConfig.from_env()` is the only way to construct a Config; it reads
required variables from os.environ. Missing variables raise KeyError with a
clear message naming the missing key.

This config is for the analyze stage only. The embed and upload stages use
`query_index.Config` directly because they are talking to AI Search and
AzureOpenAI, not to Document Intelligence.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

_REQUIRED_VARS: tuple[str, ...] = (
    "DOC_INTEL_ENDPOINT",
    "DOC_INTEL_KEY",
)


@dataclass(frozen=True)
class IngestionConfig:
    doc_intel_endpoint: str
    doc_intel_key: str

    @classmethod
    def from_env(cls) -> IngestionConfig:
        for var in _REQUIRED_VARS:
            if var not in os.environ:
                raise KeyError(f"Required environment variable not set: {var}")
        return cls(
            doc_intel_endpoint=os.environ["DOC_INTEL_ENDPOINT"],
            doc_intel_key=os.environ["DOC_INTEL_KEY"],
        )
