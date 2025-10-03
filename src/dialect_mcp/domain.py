#!/usr/bin/env python3
"""
Domain models, types, and exceptions for Franconian dialect MCP server.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, NewType

from pydantic import BaseModel, ConfigDict


# Domain types
GermanWord = NewType("GermanWord", str)
FranconianWord = NewType("FranconianWord", str)
TownName = NewType("TownName", str)
XMLContent = NewType("XMLContent", str)


class SearchScope(StrEnum):
    # Regional scopes for the three main Franconian regions
    OBERFRANKEN = "oberfranken"
    MITTELFRANKEN = "mittelfranken"
    UNTERFRANKEN = "unterfranken"

    # Oberfranken - Kreisfreie Städte (Independent Cities)
    CITY_BAMBERG = "city_bamberg"
    CITY_BAYREUTH = "city_bayreuth"
    CITY_COBURG = "city_coburg"
    CITY_HOF = "city_hof"

    # Mittelfranken - Kreisfreie Städte (Independent Cities)
    CITY_ANSBACH = "city_ansbach"
    CITY_ERLANGEN = "city_erlangen"
    CITY_FUERTH = "city_fuerth"
    CITY_NUERNBERG = "city_nuernberg"
    CITY_SCHWABACH = "city_schwabach"

    # Unterfranken - Kreisfreie Städte (Independent Cities)
    CITY_ASCHAFFENBURG = "city_aschaffenburg"
    CITY_SCHWEINFURT = "city_schweinfurt"
    CITY_WUERZBURG = "city_wuerzburg"

    # Oberfranken - Landkreise (Districts)
    LANDKREIS_BAMBERG = "landkreis_bamberg"
    LANDKREIS_BAYREUTH = "landkreis_bayreuth"
    LANDKREIS_COBURG = "landkreis_coburg"
    LANDKREIS_FORCHHEIM = "landkreis_forchheim"
    LANDKREIS_HOF = "landkreis_hof"
    LANDKREIS_KRONACH = "landkreis_kronach"
    LANDKREIS_KULMBACH = "landkreis_kulmbach"
    LANDKREIS_LICHTENFELS = "landkreis_lichtenfels"
    LANDKREIS_WUNSIEDEL = "landkreis_wunsiedel"

    # Mittelfranken - Landkreise (Districts)
    LANDKREIS_ANSBACH = "landkreis_ansbach"
    LANDKREIS_ERLANGEN_HOECHSTADT = "landkreis_erlangen_hoechstadt"
    LANDKREIS_FUERTH = "landkreis_fuerth"
    LANDKREIS_NEUSTADT_AISCH_BAD_WINDSHEIM = "landkreis_neustadt_aisch_bad_windsheim"
    LANDKREIS_NUERNBERGER_LAND = "landkreis_nuernberger_land"
    LANDKREIS_ROTH = "landkreis_roth"
    LANDKREIS_WEISSENBURG_GUNZENHAUSEN = "landkreis_weissenburg_gunzenhausen"

    # Unterfranken - Landkreise (Districts)
    LANDKREIS_ASCHAFFENBURG = "landkreis_aschaffenburg"
    LANDKREIS_BAD_KISSINGEN = "landkreis_bad_kissingen"
    LANDKREIS_HASSBERGE = "landkreis_hassberge"
    LANDKREIS_KITZINGEN = "landkreis_kitzingen"
    LANDKREIS_MAIN_SPESSART = "landkreis_main_spessart"
    LANDKREIS_MILTENBERG = "landkreis_miltenberg"
    LANDKREIS_RHOEN_GRABFELD = "landkreis_rhoen_grabfeld"
    LANDKREIS_SCHWEINFURT = "landkreis_schweinfurt"
    LANDKREIS_WUERZBURG = "landkreis_wuerzburg"

    # Area scopes - combine independent cities with their surrounding districts
    # Oberfranken Areas
    AREA_BAMBERG = "area_bamberg"  # Stadt + Landkreis Bamberg
    AREA_BAYREUTH = "area_bayreuth"  # Stadt + Landkreis Bayreuth
    AREA_COBURG = "area_coburg"  # Stadt + Landkreis Coburg
    AREA_HOF = "area_hof"  # Stadt + Landkreis Hof

    # Mittelfranken Areas
    AREA_ANSBACH = "area_ansbach"  # Stadt + Landkreis Ansbach
    AREA_ERLANGEN = "area_erlangen"  # Stadt + Landkreis Erlangen-Höchstadt
    AREA_FUERTH = "area_fuerth"  # Stadt + Landkreis Fürth
    AREA_NUERNBERG = "area_nuernberg"  # Stadt + Landkreis Nürnberger Land

    # Unterfranken Areas
    AREA_ASCHAFFENBURG = "area_aschaffenburg"  # Stadt + Landkreis Aschaffenburg
    AREA_SCHWEINFURT = "area_schweinfurt"  # Stadt + Landkreis Schweinfurt
    AREA_WUERZBURG = "area_wuerzburg"  # Stadt + Landkreis Würzburg

    # Note: Schwabach (Mittelfranken) has no corresponding district
    # Note: Some districts don't have corresponding independent cities

    # Special scope for custom town/village searches
    CUSTOM_TOWN = "custom_town"  # Requires town parameter - for specific villages/towns


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


# Structured error response models
class ErrorResponse(BaseModel):
    """Structured error response for MCP tools."""

    model_config = ConfigDict(frozen=True)

    error_type: str
    message: str
    details: dict[str, str] | None = None
