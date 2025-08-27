#!/usr/bin/env python3
"""
Data access layer for BDO API integration.
Repository pattern with XML validation following LangSec principles.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from .domain import (
    FranconianTranslation, 
    BDOMetadata, 
    ValidationError,
    XMLContent,
    SearchScope
)
from .validation import ValidatedTranslationRequest
from .http_client import MinimalistHTTPClient


# Complete XML validation before processing - no shotgun parsing
class ValidatedBDOResponse:
    """Completely validated BDO response structure."""
    
    def __init__(self, metadata: BDOMetadata, translations: list[FranconianTranslation]) -> None:
        self.metadata = metadata
        self.translations = translations
    
    @classmethod
    def from_xml_content(cls, xml_content: XMLContent, german_word: str) -> ValidatedBDOResponse:
        """Validate ENTIRE XML structure before any processing - follows LangSec principles."""
        if not xml_content.strip():
            raise ValidationError("Empty XML response")
        
        try:
            # Parse and validate complete structure first
            root = ET.fromstring(xml_content)
            
            # Extract and validate metadata
            info = root.find(".//info")
            if info is None:
                raise ValidationError("Missing BDO response metadata")
            
            result_count = int(info.findtext("result_count", "0"))
            timestamp = info.findtext("timestamp", "")
            
            metadata = BDOMetadata(
                result_count=result_count,
                timestamp=timestamp
            )
            
            # Validate all articles completely before processing
            translations = []
            for artikel in root.findall(".//artikel"):
                translation = cls._validate_and_extract_translation(artikel, german_word)
                if translation:
                    translations.append(translation)
            
            return cls(metadata=metadata, translations=translations)
            
        except ET.ParseError as e:
            raise ValidationError(f"Invalid XML structure: {e}")
    
    @staticmethod
    def _validate_and_extract_translation(artikel: ET.Element, german_word: str) -> FranconianTranslation | None:
        """Validate individual article structure completely before extraction."""
        # Extract lemma (Franconian word)
        lemma_elem = artikel.find(".//lemma/value")
        if lemma_elem is None or not lemma_elem.text:
            return None
        franconian_word = lemma_elem.text.strip()
        
        # Extract meaning (should match or relate to German word)
        meaning_elem = artikel.find(".//bedeutung")
        if meaning_elem is None or not meaning_elem.text:
            return None
        meaning = meaning_elem.text.strip()
        
        # Find evidence with location in Ansbach area
        best_evidence = None
        best_location = None
        
        for beleg in artikel.findall(".//beleg-angabe"):
            evidence_elem = beleg.find(".//beleg-text")
            region_elem = beleg.find(".//beleg-region")
            
            if evidence_elem is None or region_elem is None:
                continue
            
            town = region_elem.get("ort", "").strip()
            county = region_elem.get("landkreis", "").strip()
            
            # Prioritize Ansbach area locations
            if county == "AN" or "Ansbach" in town:
                best_evidence = evidence_elem.text.strip() if evidence_elem.text else ""
                best_location = f"{town}, Landkreis {county}" if county else town
                break
        
        if not best_evidence or not best_location:
            return None
        
        # Extract optional grammar info
        grammar_elem = artikel.find(".//grammatik")
        grammar = None
        if grammar_elem is not None:
            word_type = grammar_elem.get("wortart")
            gender = grammar_elem.get("genus")
            if word_type or gender:
                grammar = f"{word_type or ''} {gender or ''}".strip()
        
        # Extract etymology
        etymology_elem = artikel.find(".//etymologie")
        etymology = etymology_elem.text.strip() if etymology_elem is not None and etymology_elem.text else None
        
        # Calculate confidence based on meaning match
        confidence = cls._calculate_confidence(german_word, meaning, franconian_word)
        
        return FranconianTranslation(
            german_word=german_word,
            franconian_word=franconian_word,
            meaning=meaning,
            evidence=best_evidence,
            location=best_location,
            grammar=grammar,
            etymology=etymology,
            confidence=confidence
        )
    
    @staticmethod
    def _calculate_confidence(german_word: str, meaning: str, franconian_word: str) -> float:
        """Calculate translation confidence score."""
        # Simple heuristic - exact word match gives highest confidence
        if german_word.lower() in meaning.lower():
            return 0.95
        # Partial match
        elif any(word in meaning.lower() for word in german_word.lower().split()):
            return 0.75
        # Related meaning
        else:
            return 0.5


# Simple parameter builder - deterministic mapping
class BDOParameterBuilder:
    """Simple parameter builder for BDO API - minimalist approach."""
    
    @staticmethod
    def build_params(request: ValidatedTranslationRequest) -> dict[str, str]:
        """Build API parameters - deterministic mapping from validated request."""
        params = {
            "dictionary": "wbf",  # Franconian dictionary only
            "bedeutung": request.german_word,  # Search in meanings for German word
            "case": "no",
            "exact": "yes" if request.exact_match else "no"
        }
        
        # Set geographic scope
        if request.scope == SearchScope.LANDKREIS_ANSBACH:
            params["landkreise"] = "AN"
        elif request.scope == SearchScope.CITY_ANSBACH:
            params["orte"] = "Ansbach"
        
        # Add specific town if provided
        if request.town and request.scope != SearchScope.CITY_ANSBACH:
            params["orte"] = request.town
        
        return params


# Repository with single responsibility
class FranconianTranslationRepository:
    """Repository for Franconian translation data access."""
    
    BASE_URL = "https://bdo.badw.de/api/v1"
    
    def __init__(self, http_client: MinimalistHTTPClient) -> None:
        self._http_client = http_client
    
    async def find_franconian_translations(
        self, 
        request: ValidatedTranslationRequest
    ) -> list[FranconianTranslation]:
        """Find Franconian translations for German word."""
        # Build parameters using deterministic mapping
        params = BDOParameterBuilder.build_params(request)
        
        # Get raw XML response
        raw_xml = await self._http_client.get_raw_response(self.BASE_URL, params)
        
        # Validate XML completely before processing
        validated_response = ValidatedBDOResponse.from_xml_content(
            XMLContent(raw_xml), 
            request.german_word
        )
        
        return validated_response.translations