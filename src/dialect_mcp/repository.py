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


class SemanticConfidenceCalculator:
    """
    Calculates semantic confidence scores for translation matches.

    Considers semantic relationship types (exact, derived, antonym, contextual),
    part-of-speech consistency, and evidence quality.
    """

    # Common German derivational suffixes for nouns from adjectives
    DERIVATIONAL_SUFFIXES = [
        "heit",   # Freundlichkeit, Schönheit
        "keit",   # Dankbarkeit, Fröhlichkeit
        "ung",    # Wanderung (from wandern)
        "schaft", # Freundschaft
    ]

    # Common adjective comparison suffixes
    COMPARATIVE_SUFFIXES = [
        "er",     # schöner, größer
        "ere",    # schönere
        "erer",   # schönerer
    ]

    SUPERLATIVE_SUFFIXES = [
        "ste",    # schönste, größte
        "ster",   # schönster
        "stes",   # schönstes
    ]

    # Antonym prefixes and patterns
    ANTONYM_PREFIXES = ["un", "nicht ", "in", "miss"]

    @staticmethod
    def calculate_confidence(
        german_word: str,
        meaning: str,
        franconian_word: str,
        grammar: str | None = None,
    ) -> float:
        """
        Calculate semantic confidence score (0.0 - 1.0).

        Args:
            german_word: The German query word
            meaning: The meaning/definition from BDO
            franconian_word: The Franconian evidence text
            grammar: Optional grammar information

        Returns:
            Confidence score between 0.0 and 1.0
        """
        german_lower = german_word.lower().strip()
        meaning_lower = meaning.lower().strip()

        # Base score from semantic relationship
        base_score = SemanticConfidenceCalculator._calculate_semantic_relationship_score(
            german_lower, meaning_lower
        )

        # Grammar consistency adjustment
        if grammar:
            grammar_adjustment = SemanticConfidenceCalculator._calculate_grammar_adjustment(
                german_lower, meaning_lower, grammar
            )
            base_score += grammar_adjustment

        # Evidence quality adjustment
        evidence_adjustment = SemanticConfidenceCalculator._calculate_evidence_quality_adjustment(
            franconian_word
        )
        base_score += evidence_adjustment

        # Clamp to valid range [0.0, 1.0]
        return max(0.0, min(1.0, base_score))

    @staticmethod
    def _calculate_semantic_relationship_score(
        german_lower: str, meaning_lower: str
    ) -> float:
        """Determine base confidence from semantic relationship type."""

        # EXACT MATCH: meaning is exactly the word or starts with it
        # Examples: "groß" → "groß", "sprechen" → "sprechen, reden"
        if meaning_lower == german_lower:
            return 0.95

        # Meaning starts with the word followed by punctuation or space
        # BUT check for qualifying words or if it's an action ABOUT the word
        if meaning_lower.startswith(f"{german_lower},") or \
           meaning_lower.startswith(f"{german_lower};") or \
           meaning_lower.startswith(f"{german_lower} "):

            # Split to see what comes after the word
            after_word = meaning_lower[len(german_lower):].strip()

            # Check for action verbs that indicate this is about DOING something to/with the word
            # Examples: "Kinder schimpfen" = scolding children (not "children" itself)
            action_verbs = ["schimpfen", "tadeln", "rufen", "holen", "bringen",
                           "sehen", "hören", "machen", "tun", "haben", "geben",
                           "nehmen", "bekommen", "kriegen", "spielen", "lernen"]

            # If immediately followed by action verb, this is contextual, not the word itself
            for verb in action_verbs:
                if after_word.startswith(verb) or after_word.startswith(f", {verb}"):
                    return 0.45  # Action involving the word, not word itself

            # Check if there are qualifiers before the word that modify its meaning
            # Examples: "unaufrichtig freundlich", "nicht gut", "sehr groß"
            words_before = meaning_lower.split(german_lower)[0].strip().split()

            # Qualifying/modifying words that change the core meaning
            modifiers = ["nicht", "un", "kein", "ohne", "sehr", "zu", "unaufrichtig",
                        "falsch", "pseudo", "schein", "kaum"]

            # If preceded by modifiers, lower confidence
            if words_before and any(mod in " ".join(words_before) for mod in modifiers):
                return 0.65  # Modified meaning, not direct match

            # Clean match at start
            return 0.95

        # ANTONYM: meaning is the opposite (strong negative signal!)
        # Examples: "freundlich" → "unfreundlich", "gut" → "nicht gut"
        if SemanticConfidenceCalculator._is_antonym(german_lower, meaning_lower):
            return 0.30  # Low confidence - opposite meaning

        # DERIVED NOUN FROM ADJECTIVE/VERB
        # Examples: "freundlich" → "Freundlichkeit", "wandern" → "Wanderung"
        for suffix in SemanticConfidenceCalculator.DERIVATIONAL_SUFFIXES:
            derived_form = f"{german_lower}{suffix}"
            if derived_form in meaning_lower:
                # Check if it's a clean match (not part of longer word)
                if SemanticConfidenceCalculator._is_clean_word_match(
                    derived_form, meaning_lower
                ):
                    return 0.70  # Derived form - different POS but same semantic root

        # Also check for adjective forms in meaning (e.g., "freundliches Wesen")
        # This catches "freundlich" → "freundliches/freundlicher/freundliche"
        for adj_suffix in ["es", "er", "e", "en", "em"]:
            adj_form = f"{german_lower}{adj_suffix}"
            if adj_form in meaning_lower:
                # Check if it appears in first few words (likely definition)
                words = meaning_lower.split()
                if adj_form in words[:5]:
                    return 0.75  # Inflected adjective in definition

        # COMPARATIVE/SUPERLATIVE FORMS
        # Examples: "groß" → "größer", "schön" → "schönste"
        # Need to handle umlaut changes: groß → größer, alt → älter
        stem_variants = SemanticConfidenceCalculator._apply_umlaut(german_lower)
        for suffix in SemanticConfidenceCalculator.COMPARATIVE_SUFFIXES + \
                      SemanticConfidenceCalculator.SUPERLATIVE_SUFFIXES:
            for stem in stem_variants:
                comparative_form = f"{stem}{suffix}"
                if comparative_form in meaning_lower:
                    return 0.85  # Inflected form - same POS, same meaning

        # WORD APPEARS IN MEANING
        # Distinguish between definition vs. contextual usage
        if german_lower in meaning_lower:
            # Get position of word in meaning
            words_in_meaning = meaning_lower.split()

            # Find the position of our query word
            try:
                word_position = words_in_meaning.index(german_lower)
            except ValueError:
                # Word is part of a compound, check substring match
                word_position = 999  # Mark as late position

            # Word in first position = likely direct definition
            if word_position == 0:
                return 0.80

            # Word in positions 1-3 = could be definition or contextual
            # Examples: "freundlich sein", "Kinder schimpfen" (contextual!)
            elif word_position <= 2:
                # Check if it's an action ABOUT the thing (lower confidence)
                # Pattern: "<word> <verb>" = action involving word, not word itself
                action_verbs = ["schimpfen", "tadeln", "rufen", "holen", "bringen",
                               "sehen", "hören", "machen", "tun", "sein", "werden",
                               "haben", "geben", "nehmen", "bekommen", "kriegen"]

                # If next word is a verb, this is likely contextual (action involving the word)
                if word_position + 1 < len(words_in_meaning):
                    next_word = words_in_meaning[word_position + 1]
                    if any(verb in next_word for verb in action_verbs):
                        return 0.45  # Contextual - action involving the word

                return 0.75  # Definition with the word early

            # Word appears later = likely contextual/example
            # Examples: "Person, die nur in der Öffentlichkeit freundlich ist"
            else:
                return 0.50

        # PARTIAL WORD MATCH (any word from multi-word query)
        # Examples: "sehr groß" → "groß"
        german_words = german_lower.split()
        if len(german_words) > 1:
            for word in german_words:
                if len(word) > 2 and word in meaning_lower:  # Skip short words (der, die, das)
                    return 0.60

        # NO CLEAR RELATIONSHIP
        return 0.40

    @staticmethod
    def _apply_umlaut(word: str) -> list[str]:
        """
        Generate possible umlaut variants for comparative/superlative detection.

        Returns list of possible forms including original and umlauted versions.
        Examples: "groß" → ["groß", "größ"], "alt" → ["alt", "ält"]
        """
        variants = [word]  # Always include original

        # Common umlaut transformations in German comparatives
        umlaut_map = {
            "a": "ä",
            "o": "ö",
            "u": "ü",
            "au": "äu",
        }

        for old, new in umlaut_map.items():
            if old in word:
                # Replace last occurrence (typically the stem vowel)
                pos = word.rfind(old)
                umlauted = word[:pos] + new + word[pos + len(old):]
                variants.append(umlauted)

        return variants

    @staticmethod
    def _is_antonym(german_lower: str, meaning_lower: str) -> bool:
        """Detect if meaning represents opposite of query word."""
        # Check for negation prefixes
        for prefix in SemanticConfidenceCalculator.ANTONYM_PREFIXES:
            antonym_pattern = f"{prefix}{german_lower}"
            if antonym_pattern in meaning_lower:
                return True

        # Check for "nicht <word>" pattern
        if f"nicht {german_lower}" in meaning_lower:
            return True

        return False

    @staticmethod
    def _is_clean_word_match(word: str, text: str) -> bool:
        """Check if word appears as complete word (not as substring of longer word)."""
        # Simple heuristic: check if word is followed by space, comma, or end of string
        index = text.find(word)
        if index == -1:
            return False

        # Check character after word (if exists)
        end_index = index + len(word)
        if end_index < len(text):
            next_char = text[end_index]
            return next_char in [' ', ',', ';', '.', '!', '?', ')']

        return True  # Word at end of text

    @staticmethod
    def _calculate_grammar_adjustment(
        german_lower: str, meaning_lower: str, grammar: str
    ) -> float:
        """Calculate adjustment based on part-of-speech consistency."""
        grammar_lower = grammar.lower()

        # Extract POS from grammar string
        # Examples: "Adjektiv", "Substantiv F", "Verb (schwach)"
        result_pos = None
        if "substantiv" in grammar_lower or "nomen" in grammar_lower:
            result_pos = "noun"
        elif "adjektiv" in grammar_lower:
            result_pos = "adjective"
        elif "verb" in grammar_lower:
            result_pos = "verb"
        elif "adverb" in grammar_lower:
            result_pos = "adverb"

        if not result_pos:
            return 0.0  # No clear POS identified

        # Detect expected POS from query word patterns (heuristic)
        query_pos = SemanticConfidenceCalculator._guess_pos_from_word(german_lower)

        if not query_pos:
            return 0.0  # Can't determine query POS

        # Same POS = small bonus
        if query_pos == result_pos:
            return 0.05

        # Different POS = small penalty (unless it's a known derivation)
        # Don't penalize derivational relationships we already scored high
        return 0.0  # Neutral - derivational relationships already handled

    @staticmethod
    def _guess_pos_from_word(german_lower: str) -> str | None:
        """Heuristically guess POS from German word patterns."""
        # Common adjective endings
        if any(german_lower.endswith(suffix) for suffix in [
            "lich", "ig", "bar", "sam", "haft", "los"
        ]):
            return "adjective"

        # Common noun endings (and capitalization in original - but we have lowercase)
        if any(german_lower.endswith(suffix) for suffix in [
            "heit", "keit", "ung", "schaft", "tum", "nis"
        ]):
            return "noun"

        # Common verb endings
        if any(german_lower.endswith(suffix) for suffix in [
            "en", "eln", "ern", "igen", "ieren"
        ]):
            return "verb"

        return None  # Can't determine

    @staticmethod
    def _calculate_evidence_quality_adjustment(franconian_word: str) -> float:
        """Calculate adjustment based on evidence text quality."""
        word_count = len(franconian_word.split())

        # Single word = cleanest result
        if word_count == 1:
            return 0.05

        # Short phrase (2-4 words) = still good
        if word_count <= 4:
            return 0.02

        # Medium phrase (5-10 words) = contextual but acceptable
        if word_count <= 10:
            return 0.0

        # Long sentence (>10 words) = likely example/explanation
        return -0.08


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
        # Extract lemma (the German dictionary headword - NOT the Franconian form!)
        lemma_elem = artikel.find(".//lemma")
        if lemma_elem is None or not lemma_elem.text:
            return None
        lemma = lemma_elem.text.strip()

        # Extract meaning (should match or relate to German word)
        meaning_elem = artikel.find(".//bedeutung")
        if meaning_elem is None or not meaning_elem.text:
            return None
        meaning = meaning_elem.text.strip()

        # Find evidence with location preference for Ansbach area
        # The beleg-text contains the ACTUAL Franconian transcription!
        best_evidence = None
        best_location = None
        fallback_evidence = None
        fallback_location = None

        for beleg in artikel.findall(".//beleg-angabe"):
            evidence_elem = beleg.find(".//beleg-text")
            region_elem = beleg.find(".//beleg-region")

            if evidence_elem is None or region_elem is None:
                continue
            if not evidence_elem.text:
                continue

            town = region_elem.get("ort", "").strip()
            county = region_elem.get("landkreis", "").strip()
            evidence_text = evidence_elem.text.strip()
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

        # Use the evidence text as the "Franconian word"
        # This contains the actual dialect transcription/usage
        franconian_word = final_evidence

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

        # Calculate confidence using semantic relationship analysis
        confidence = SemanticConfidenceCalculator.calculate_confidence(
            german_word, meaning, franconian_word, grammar
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

    async def close(self) -> None:
        """Close the repository and cleanup resources."""
        await self._http_client.close()
