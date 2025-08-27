#!/usr/bin/env python3
"""
Domain models, types, and exceptions for Franconian dialect MCP server.
Following LangSec principles with precise type definitions.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, NewType

from pydantic import BaseModel, ConfigDict


# Domain types - precise representations following LangSec principles
GermanWord = NewType('GermanWord', str)
FranconianWord = NewType('FranconianWord', str)
TownName = NewType('TownName', str)
XMLContent = NewType('XMLContent', str)


class SearchScope(StrEnum):
    """Minimalist search scope - constrained to essential options."""
    LANDKREIS_ANSBACH = "landkreis_ansbach"
    CITY_ANSBACH = "city_ansbach"


class BDOError(Exception):
    """Base exception for BDO operations."""
    
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


class ValidationError(BDOError):
    """Input validation failure at system boundary."""


class APIError(BDOError):
    """API communication failure."""


# MCP Response Models - structured output with schema validation
class FranconianTranslation(BaseModel):
    """Structured MCP response for Franconian translations."""
    model_config = ConfigDict(frozen=True)
    
    german_word: str
    franconian_word: str
    meaning: str
    evidence: str
    location: str
    grammar: str | None = None
    etymology: str | None = None
    confidence: float
    source: str = "BDO-WBF"


class BDOMetadata(BaseModel):
    """BDO API response metadata - validated structure."""
    model_config = ConfigDict(frozen=True)
    
    result_count: int
    timestamp: str
    api_version: str = "1.0"
    licence: str = "CC-BY"