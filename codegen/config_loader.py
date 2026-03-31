"""
Codegen — Config Loader
========================
Pydantic models for research_config.yaml validation.
Loads and saves a ResearchConfig from/to YAML.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field


# ─── Models ───────────────────────────────────────────────


class ProjectConfig(BaseModel):
    title: str
    short_title: str
    researcher_name: str


class PaperConfig(BaseModel):
    id: str
    label: str
    focus: str


class ScholarConfig(BaseModel):
    name: str
    key: str
    context: str


class DatabaseConfig(BaseModel):
    name: str
    purpose: str


class ResearchContext(BaseModel):
    summary: str
    critical_note: str
    databases: list[DatabaseConfig] = []


class ColumnDef(BaseModel):
    name: str
    type: str = "text"
    options: list[str] = []


class CustomSection(BaseModel):
    id: str
    label: str
    columns: list[ColumnDef] = []


class RubricDimension(BaseModel):
    name: str
    weight: float
    scale_1: str
    scale_3: str
    scale_5: str


class RelevanceRubric(BaseModel):
    dimensions: list[RubricDimension] = []


class GoogleSheetsConfig(BaseModel):
    spreadsheet_id: str = ""
    auto_spreadsheet_id: str = ""


class ApiConfig(BaseModel):
    mailto: str = ""


class ResearchConfig(BaseModel):
    project: ProjectConfig
    papers: list[PaperConfig] = []
    research_context: ResearchContext
    key_scholars: list[ScholarConfig] = []
    theories: list[str] = []
    custom_sections: list[CustomSection] = []
    dropdowns: dict = {}
    relevance_rubric: RelevanceRubric = RelevanceRubric()
    google_sheets: GoogleSheetsConfig = GoogleSheetsConfig()
    api: ApiConfig = ApiConfig()
    fallback_keywords: list[str] = []


# ─── Load / Save ──────────────────────────────────────────


def load_config(path: str | Path) -> ResearchConfig:
    """Load and validate a research_config.yaml file."""
    path = Path(path)
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return ResearchConfig(**raw)


def save_config(config: ResearchConfig, path: str | Path) -> None:
    """Serialize a ResearchConfig back to YAML."""
    path = Path(path)
    data = config.model_dump()
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
