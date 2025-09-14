#!/usr/bin/env python3
"""
MCP server setup and endpoints for Franconian dialect translations.
FastMCP server with tools, resources, and prompts.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

from .domain import FranconianTranslation, ValidationError, BDOError
from .service import FranconianTranslationService
from .repository import FranconianTranslationRepository
from .http_client import MinimalistHTTPClient

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_translation_service() -> FranconianTranslationService:
    http_client = MinimalistHTTPClient()
    repository = FranconianTranslationRepository(http_client)
    return FranconianTranslationService(repository)


mcp = FastMCP("Franconian Translation Server")
translation_service = create_translation_service()


@mcp.tool()
async def find_franconian_equivalent(
    german_word: str,
    scope: str = "landkreis_ansbach",
    town: str | None = None,
    exact_match: bool = False
) -> list[FranconianTranslation]:
    """
    Find Franconian dialect equivalent(s) of a German word.
    
    Specialized for the Ansbach region (Landkreis Ansbach) in Franconia.
    
    Args:
        german_word: Standard German word (e.g., "Wurst", "Haus", "klein")
        scope: Search scope - 'landkreis_ansbach' or 'city_ansbach'
        town: Optional specific town name in Landkreis Ansbach
        exact_match: Whether to require exact matches in meanings
        
    Returns:
        List of FranconianTranslation objects with structured data
        
    Examples:
        - find_franconian_equivalent("Wurst") → "Worscht"
        - find_franconian_equivalent("Haus") → "Haus" (same in Franconian)
        - find_franconian_equivalent("klein") → "glaa"
    """
    try:
        translations = await translation_service.translate_to_franconian(
            german_word, scope, town, exact_match
        )
        
        if not translations:
            return []
        
        return translations
        
    except ValidationError as e:
        logger.error(f"Validation error: {e}")
        raise ValueError(f"Invalid input: {e}")
    except BDOError as e:
        logger.error(f"BDO API error: {e}")
        raise RuntimeError(f"Translation search failed: {e}")


@mcp.resource("franconian://word/{german_word}")
async def get_franconian_word_info(german_word: str) -> str:
    """Get comprehensive information about Franconian translation of a German word."""
    try:
        translations = await translation_service.translate_to_franconian(german_word)
        
        if not translations:
            return f"No Franconian equivalent found for '{german_word}' in the Ansbach region."
        
        # Format as rich text resource
        result = f"Franconian Translations for '{german_word}' (Ansbach Region):\n\n"
        
        for i, translation in enumerate(translations[:5], 1):  # Limit to top 5
            result += f"{i}. {translation.franconian_word}\n"
            result += f"   Meaning: {translation.meaning}\n"
            result += f"   Location: {translation.location}\n"
            result += f"   Evidence: {translation.evidence}\n"
            result += f"   Confidence: {translation.confidence:.1%}\n"
            
            if translation.grammar:
                result += f"   Grammar: {translation.grammar}\n"
            if translation.etymology:
                result += f"   Etymology: {translation.etymology}\n"
            result += "\n"
        
        if len(translations) > 5:
            result += f"... and {len(translations) - 5} more variants found.\n"
        
        return result
        
    except Exception as e:
        logger.error(f"Error in franconian word resource: {e}")
        return f"Error retrieving Franconian information for '{german_word}': {e}"


@mcp.resource("franconian://examples")
async def get_translation_examples() -> str:
    """Get examples of German to Franconian translations from the Ansbach area."""
    examples = [
        ("Wurst", "Worscht"),
        ("Haus", "Haus"),
        ("klein", "glaa"),
        ("Brot", "Brod"),
        ("Wasser", "Wasser"),
        ("Mädchen", "Madla"),
        ("sprechen", "schwätza"),
        ("gehen", "geh"),
        ("schön", "schee"),
        ("groß", "groß")
    ]
    
    result = "Common German to Franconian Translations (Ansbach Region):\n\n"
    
    for german, franconian in examples:
        result += f"• {german} → {franconian}\n"
    
    result += "\nNote: These are typical examples. Actual translations may vary by specific location within Landkreis Ansbach."
    
    return result


@mcp.prompt()
async def translate_to_franconian_prompt(
    german_word: str,
    context: str = "everyday conversation",
    include_pronunciation: bool = False,
    include_etymology: bool = False
) -> str:
    """Generate a prompt for translating German words to Franconian dialect."""
    prompt_parts = [
        f"Help me find the Franconian dialect equivalent for the Standard German word '{german_word}' "
        f"as used in the Ansbach region (Landkreis Ansbach) in the context of {context}."
    ]
    
    prompt_parts.append(
        "Please search the BDO (Bayerns Dialekte Online) database and provide:"
    )
    
    prompt_parts.extend([
        "1. The local Franconian/Ansbach dialect version",
        "2. Usage examples from the region", 
        "3. Location-specific variations within Landkreis Ansbach",
        "4. Grammatical information if available"
    ])
    
    if include_pronunciation:
        prompt_parts.append("5. Pronunciation guidance and phonetic differences")
    
    if include_etymology:
        prompt_parts.append("6. Etymological background and historical development")
    
    prompt_parts.append(
        "Focus particularly on authentic usage in towns like Ansbach, Merkendorf, "
        "Dietenhofen, Feuchtwangen, and surrounding villages in the Franconian region."
    )
    
    return " ".join(prompt_parts)


def run_server() -> None:
    """Run the MCP server with proper cleanup."""
    logger.info("Starting Franconian Translation MCP Server")
    try:
        mcp.run()
    finally:
        logger.info("Shutting down server")
        async def cleanup():
            if hasattr(translation_service._repository, '_http_client'):
                await translation_service._repository._http_client.close()
        
        try:
            loop = asyncio.get_event_loop()
            if not loop.is_closed():
                loop.run_until_complete(cleanup())
        except RuntimeError:
            pass