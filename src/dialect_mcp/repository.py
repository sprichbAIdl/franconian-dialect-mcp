#!/usr/bin/env python3
"""
Data access layer for BDO API integration.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from .domain import (
    FranconianTranslation,
    BDOMetadata,
    ValidationError,
    XMLContent,
    SearchScope,
)
from .validation import ValidatedTranslationRequest
from .http_client import MinimalistHTTPClient


class ValidatedBDOResponse:
    def __init__(
        self, metadata: BDOMetadata, translations: list[FranconianTranslation]
    ) -> None:
        self.metadata = metadata
        self.translations = translations

    @classmethod
    def from_xml_content(
        cls, xml_content: XMLContent, german_word: str
    ) -> ValidatedBDOResponse:
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

            metadata = BDOMetadata(result_count=result_count, timestamp=timestamp)

            # Validate all articles completely before processing
            translations = []
            for artikel in root.findall(".//artikel"):
                translation = cls._validate_and_extract_translation(
                    artikel, german_word
                )
                if translation:
                    translations.append(translation)

            return cls(metadata=metadata, translations=translations)

        except ET.ParseError as e:
            raise ValidationError(f"Invalid XML structure: {e}")

    @staticmethod
    def _validate_and_extract_translation(
        artikel: ET.Element, german_word: str
    ) -> FranconianTranslation | None:
        # Extract lemma (Franconian word)
        lemma_elem = artikel.find(".//lemma")
        if lemma_elem is None or not lemma_elem.text:
            return None
        franconian_word = lemma_elem.text.strip()

        # Extract meaning (should match or relate to German word)
        meaning_elem = artikel.find(".//bedeutung")
        if meaning_elem is None or not meaning_elem.text:
            return None
        meaning = meaning_elem.text.strip()

        # Find evidence with location preference for Ansbach area
        best_evidence = None
        best_location = None
        fallback_evidence = None
        fallback_location = None

        for beleg in artikel.findall(".//beleg-angabe"):
            evidence_elem = beleg.find(".//beleg-text")
            region_elem = beleg.find(".//beleg-region")

            if evidence_elem is None or region_elem is None:
                continue

            town = region_elem.get("ort", "").strip()
            county = region_elem.get("landkreis", "").strip()
            evidence_text = evidence_elem.text.strip() if evidence_elem.text else ""
            location_text = f"{town}, Landkreis {county}" if county else town

            # Prioritize Ansbach area locations
            if county == "AN" or "Ansbach" in town:
                best_evidence = evidence_text
                best_location = location_text
                break
            # Keep first valid evidence as fallback
            elif not fallback_evidence and evidence_text and location_text:
                fallback_evidence = evidence_text
                fallback_location = location_text

        # Use Ansbach evidence if found, otherwise fallback
        final_evidence = best_evidence or fallback_evidence
        final_location = best_location or fallback_location

        if not final_evidence or not final_location:
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
        etymology = (
            etymology_elem.text.strip()
            if etymology_elem is not None and etymology_elem.text
            else None
        )

        # Calculate confidence based on meaning match
        confidence = ValidatedBDOResponse._calculate_confidence(
            german_word, meaning, franconian_word
        )

        return FranconianTranslation(
            german_word=german_word,
            franconian_word=franconian_word,
            meaning=meaning,
            evidence=final_evidence,
            location=final_location,
            grammar=grammar,
            etymology=etymology,
            confidence=confidence,
        )

    @staticmethod
    def _calculate_confidence(
        german_word: str, meaning: str, franconian_word: str
    ) -> float:
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


class BDOParameterBuilder:
    # Mapping of Landkreis scopes to their official abbreviations
    LANDKREIS_CODES = {
        # Oberfranken
        SearchScope.LANDKREIS_BAMBERG: "BA",
        SearchScope.LANDKREIS_BAYREUTH: "BT",
        SearchScope.LANDKREIS_COBURG: "CO",
        SearchScope.LANDKREIS_FORCHHEIM: "FO",
        SearchScope.LANDKREIS_HOF: "HO",
        SearchScope.LANDKREIS_KRONACH: "KC",
        SearchScope.LANDKREIS_KULMBACH: "KU",
        SearchScope.LANDKREIS_LICHTENFELS: "LIF",
        SearchScope.LANDKREIS_WUNSIEDEL: "WUN",
        # Mittelfranken
        SearchScope.LANDKREIS_ANSBACH: "AN",
        SearchScope.LANDKREIS_ERLANGEN_HOECHSTADT: "ERH",
        SearchScope.LANDKREIS_FUERTH: "FÜ",
        SearchScope.LANDKREIS_NEUSTADT_AISCH_BAD_WINDSHEIM: "NEA",
        SearchScope.LANDKREIS_NUERNBERGER_LAND: "LAU",
        SearchScope.LANDKREIS_ROTH: "RH",
        SearchScope.LANDKREIS_WEISSENBURG_GUNZENHAUSEN: "WUG",
        # Unterfranken
        SearchScope.LANDKREIS_ASCHAFFENBURG: "AB",
        SearchScope.LANDKREIS_BAD_KISSINGEN: "KG",
        SearchScope.LANDKREIS_HASSBERGE: "HAS",
        SearchScope.LANDKREIS_KITZINGEN: "KT",
        SearchScope.LANDKREIS_MAIN_SPESSART: "MSP",
        SearchScope.LANDKREIS_MILTENBERG: "MIL",
        SearchScope.LANDKREIS_RHOEN_GRABFELD: "NES",
        SearchScope.LANDKREIS_SCHWEINFURT: "SW",
        SearchScope.LANDKREIS_WUERZBURG: "WÜ",
    }

    # Mapping of city scopes to their official names
    CITY_NAMES = {
        # Oberfranken
        SearchScope.CITY_BAMBERG: "Bamberg",
        SearchScope.CITY_BAYREUTH: "Bayreuth",
        SearchScope.CITY_COBURG: "Coburg",
        SearchScope.CITY_HOF: "Hof",
        # Mittelfranken
        SearchScope.CITY_ANSBACH: "Ansbach",
        SearchScope.CITY_ERLANGEN: "Erlangen",
        SearchScope.CITY_FUERTH: "Fürth",
        SearchScope.CITY_NUERNBERG: "Nürnberg",
        SearchScope.CITY_SCHWABACH: "Schwabach",
        # Unterfranken
        SearchScope.CITY_ASCHAFFENBURG: "Aschaffenburg",
        SearchScope.CITY_SCHWEINFURT: "Schweinfurt",
        SearchScope.CITY_WUERZBURG: "Würzburg",
    }

    # Regional scope mappings - all districts in each region
    REGIONAL_LANDKREISE = {
        SearchScope.OBERFRANKEN: [
            "BA",
            "BT",
            "CO",
            "FO",
            "HO",
            "KC",
            "KU",
            "LIF",
            "WUN",
        ],
        SearchScope.MITTELFRANKEN: ["AN", "ERH", "FÜ", "NEA", "LAU", "RH", "WUG"],
        SearchScope.UNTERFRANKEN: [
            "AB",
            "KG",
            "HAS",
            "KT",
            "MSP",
            "MIL",
            "NES",
            "SW",
            "WÜ",
        ],
    }

    # Area scope mappings - city + district combinations
    AREA_MAPPINGS = {
        # Oberfranken Areas
        SearchScope.AREA_BAMBERG: ("Bamberg", "BA"),
        SearchScope.AREA_BAYREUTH: ("Bayreuth", "BT"),
        SearchScope.AREA_COBURG: ("Coburg", "CO"),
        SearchScope.AREA_HOF: ("Hof", "HO"),
        # Mittelfranken Areas
        SearchScope.AREA_ANSBACH: ("Ansbach", "AN"),
        SearchScope.AREA_ERLANGEN: ("Erlangen", "ERH"),
        SearchScope.AREA_FUERTH: ("Fürth", "FÜ"),
        SearchScope.AREA_NUERNBERG: (
            "Nürnberg",
            "LAU",
        ),  # Nürnberg city + Nürnberger Land district
        # Unterfranken Areas
        SearchScope.AREA_ASCHAFFENBURG: ("Aschaffenburg", "AB"),
        SearchScope.AREA_SCHWEINFURT: ("Schweinfurt", "SW"),
        SearchScope.AREA_WUERZBURG: ("Würzburg", "WÜ"),
    }

    @staticmethod
    def build_params(request: ValidatedTranslationRequest) -> dict[str, str]:
        params = {
            "dictionary": "wbf",  # Franconian dictionary only
            "bedeutung": request.german_word,  # Search in meanings for German word
            "case": "no",
            "exact": "yes" if request.exact_match else "no",
        }

        # Set geographic scope based on scope type
        if request.scope in BDOParameterBuilder.LANDKREIS_CODES:
            # Single Landkreis scope
            params["landkreise"] = BDOParameterBuilder.LANDKREIS_CODES[request.scope]
        elif request.scope in BDOParameterBuilder.CITY_NAMES:
            # City scope
            params["orte"] = BDOParameterBuilder.CITY_NAMES[request.scope]
        elif request.scope in BDOParameterBuilder.REGIONAL_LANDKREISE:
            # Regional scope - search across multiple districts
            landkreise_list = BDOParameterBuilder.REGIONAL_LANDKREISE[request.scope]
            params["landkreise"] = ",".join(landkreise_list)
        elif request.scope in BDOParameterBuilder.AREA_MAPPINGS:
            # Area scope - combine city and district
            city_name, district_code = BDOParameterBuilder.AREA_MAPPINGS[request.scope]
            params["orte"] = city_name
            params["landkreise"] = district_code
        elif request.scope == SearchScope.CUSTOM_TOWN:
            # Custom town scope - search specific village/town only
            # Town parameter is required (validated in RawTranslationRequest)
            params["orte"] = request.town

        # Add specific town if provided (overrides city scopes but works with area scopes)
        # Note: For CUSTOM_TOWN, the town is already set above, so this won't override
        if request.town and request.scope != SearchScope.CUSTOM_TOWN:
            params["orte"] = request.town

        return params


class FranconianTranslationRepository:
    """Repository for Franconian translation data access."""

    BASE_URL = "https://bdo.badw.de/api/v1"

    def __init__(self, http_client: MinimalistHTTPClient) -> None:
        self._http_client = http_client

    async def find_franconian_translations(
        self, request: ValidatedTranslationRequest
    ) -> list[FranconianTranslation]:
        params = BDOParameterBuilder.build_params(request)

        raw_xml = await self._http_client.get_raw_response(self.BASE_URL, params)

        validated_response = ValidatedBDOResponse.from_xml_content(
            XMLContent(raw_xml), request.german_word
        )

        return validated_response.translations
