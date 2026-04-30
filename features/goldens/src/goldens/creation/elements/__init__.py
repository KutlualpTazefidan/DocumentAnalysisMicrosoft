"""Shared element-loader package consumed by curate (A.4) and synthetic
generation (A.5)."""

from goldens.creation.elements.adapter import DocumentElement, ElementsLoader
from goldens.creation.elements.analyze_json import AnalyzeJsonLoader

__all__ = ["AnalyzeJsonLoader", "DocumentElement", "ElementsLoader"]
