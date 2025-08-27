#!/usr/bin/env python3
"""
Input validation for Franconian dialect MCP server.
Single validation boundary following LangSec principles.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator

from .domain import GermanWord, TownName, SearchScope, ValidationError


# Single validation boundary - follows "push burden of proof upward"
class RawTranslationRequest(BaseModel):
    """Raw input validated once at system boundary - minimalist input language."""
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True, extra='forbid')
    
    german_word: str
    scope: str = "landkreis_ansbach"
    town: str | None = None
    exact_match: bool = False
    
    @field_validator('german_word')
    @classmethod
    def validate_german_word(cls, v: str) -> str:
        """Constrain input to safe subset - no complex language features."""
        if not v or len(v.encode('utf-8')) > 100:  # Strict length limit
            raise ValueError("Invalid German word")
        # Only allow basic German characters - minimalist alphabet
        if not all(c.isalpha() or c in 'äöüßÄÖÜ -' for c in v):
            raise ValueError("Invalid characters in German word")
        return v.strip()
    
    @field_validator('scope')
    @classmethod
    def validate_scope(cls, v: str) -> str:
        """Validate scope against deterministic finite set."""
        try:
            SearchScope(v)
            return v
        except ValueError:
            raise ValueError(f"Invalid scope: {v}")
    
    @field_validator('town')
    @classmethod
    def validate_town(cls, v: str | None) -> str | None:
        """Validate town name with strict constraints."""
        if v is None:
            return None
        if len(v.encode('utf-8')) > 50:  # Strict limit
            raise ValueError("Town name too long")
        # Only allow basic characters for town names
        if not all(c.isalpha() or c in 'äöüßÄÖÜ -' for c in v):
            raise ValueError("Invalid characters in town name")
        return v.strip()


# Validated domain representation - "write functions on data representation you wish you had"
class ValidatedTranslationRequest(BaseModel):
    """Fully validated translation request in domain representation."""
    model_config = ConfigDict(frozen=True)
    
    german_word: GermanWord
    scope: SearchScope
    town: TownName | None
    exact_match: bool
    
    @classmethod
    def from_raw(cls, raw: RawTranslationRequest) -> ValidatedTranslationRequest:
        """Convert from raw input to validated domain object."""
        return cls(
            german_word=GermanWord(raw.german_word),
            scope=SearchScope(raw.scope),
            town=TownName(raw.town) if raw.town else None,
            exact_match=raw.exact_match
        )