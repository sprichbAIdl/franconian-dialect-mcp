#!/usr/bin/env python3
"""
Business logic service for Franconian translations.
Pure service layer with no external dependencies.
"""

from __future__ import annotations

from .domain import FranconianTranslation
from .validation import RawTranslationRequest, ValidatedTranslationRequest
from .repository import FranconianTranslationRepository


# Service layer - pure business logic
class FranconianTranslationService:
    """Service for finding Franconian translations of German words."""
    
    def __init__(self, repository: FranconianTranslationRepository) -> None:
        self._repository = repository
    
    async def translate_to_franconian(
        self,
        german_word: str,
        scope: str = "landkreis_ansbach",
        town: str | None = None,
        exact_match: bool = False
    ) -> list[FranconianTranslation]:
        """Translate German word to Franconian dialect - single validation boundary."""
        # Single validation at system boundary
        raw_request = RawTranslationRequest(
            german_word=german_word,
            scope=scope,
            town=town,
            exact_match=exact_match
        )
        
        # Convert to validated domain object
        validated_request = ValidatedTranslationRequest.from_raw(raw_request)
        
        # Execute translation search
        translations = await self._repository.find_franconian_translations(validated_request)
        
        # Try broader search if no exact matches found
        if not translations and exact_match:
            broader_request = validated_request.model_copy(update={"exact_match": False})
            translations = await self._repository.find_franconian_translations(broader_request)
        
        # Sort by confidence score
        return sorted(translations, key=lambda t: t.confidence, reverse=True)