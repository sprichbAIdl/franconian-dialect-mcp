#!/usr/bin/env python3
"""
Input validation for Franconian dialect MCP server.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from .domain import GermanWord, TownName, SearchScope, ValidationError


class RawTranslationRequest(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True, extra="forbid")

    german_word: str
    scope: str = "landkreis_ansbach"
    town: str | None = None
    exact_match: bool = False

    @field_validator("german_word")
    @classmethod
    def validate_german_word(cls, v: str) -> str:
        if not v or len(v.encode("utf-8")) > 100:
            raise ValueError("Invalid German word")
        # Only allow basic German characters - minimalist alphabet
        if not all(c.isalpha() or c in "äöüßÄÖÜ -" for c in v):
            raise ValueError("Invalid characters in German word")
        return v.strip()

    @field_validator("scope")
    @classmethod
    def validate_scope(cls, v: str) -> str:
        try:
            SearchScope(v)
            return v
        except ValueError:
            raise ValueError(f"Invalid scope: {v}")

    @field_validator("town")
    @classmethod
    def validate_town(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if len(v.encode("utf-8")) > 50:
            raise ValueError("Town name too long")
        if not all(c.isalpha() or c in "äöüßÄÖÜ -" for c in v):
            raise ValueError("Invalid characters in town name")
        return v.strip()

    @model_validator(mode="after")
    def validate_custom_town_requires_town_parameter(self) -> "RawTranslationRequest":
        """Validate that CUSTOM_TOWN scope requires town parameter."""
        if self.scope == "custom_town" and not self.town:
            raise ValueError("CUSTOM_TOWN scope requires town parameter to be provided")
        return self


class ValidatedTranslationRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    german_word: GermanWord
    scope: SearchScope
    town: TownName | None
    exact_match: bool

    @classmethod
    def from_raw(cls, raw: RawTranslationRequest) -> ValidatedTranslationRequest:
        return cls(
            german_word=GermanWord(raw.german_word),
            scope=SearchScope(raw.scope),
            town=TownName(raw.town) if raw.town else None,
            exact_match=raw.exact_match,
        )
