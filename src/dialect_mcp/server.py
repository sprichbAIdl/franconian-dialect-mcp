#!/usr/bin/env python3
"""
MCP server setup and endpoints for Franconian dialect translations.
FastMCP server with tools, resources, and prompts.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from mcp.server.fastmcp import FastMCP, Context
from mcp.server.session import ServerSession

from .domain import FranconianTranslation, ValidationError, BDOError, ErrorResponse
from .service import FranconianTranslationService
from .repository import FranconianTranslationRepository
from .http_client import MinimalistHTTPClient

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class AppContext:
    """Application context holding shared resources."""
    service: FranconianTranslationService


def create_translation_service() -> FranconianTranslationService:
    """Factory function to create a translation service with all dependencies."""
    http_client = MinimalistHTTPClient()
    repository = FranconianTranslationRepository(http_client)
    return FranconianTranslationService(repository)


@asynccontextmanager
async def lifespan(app: FastMCP) -> AsyncIterator[AppContext]:
    """Manage the lifecycle of the translation service."""
    logger.info("Starting Franconian Translation Service")
    service = create_translation_service()
    try:
        yield AppContext(service=service)
    finally:
        logger.info("Shutting down Franconian Translation Service")
        await service.close()


mcp = FastMCP("Franconian Translation Server", lifespan=lifespan)


@mcp.tool()
async def find_franconian_equivalent(
    german_word: str,
    scope: str = "landkreis_ansbach",
    town: str | None = None,
    exact_match: bool = False,
    limit: int = 5,
) -> list[FranconianTranslation]:
    """
    Find Franconian dialect equivalent(s) of a German word.

    Specialized for the Ansbach region (Landkreis Ansbach) in Franconia.

    Args:
        german_word: Standard German word (e.g., "Wurst", "Haus", "klein")
        scope: Search scope - 'landkreis_ansbach' (default) or 'city_ansbach'
        town: Optional specific town name in Landkreis Ansbach
        exact_match: Whether to require exact matches in meanings
        limit: Maximum number of results to return (default: 5, max: 20)
               Conservative default to prevent token overflow and focus on best matches

    Returns:
        List of FranconianTranslation objects with structured data (limited to top results)
        Results are sorted by confidence, so you get the best matches first

    Examples:
        - find_franconian_equivalent("Wurst") → top 5 variants
        - find_franconian_equivalent("Haus", limit=3) → top 3 variants
        - find_franconian_equivalent("klein", limit=10) → top 10 variants
    """
    # Create service directly since Context injection doesn't work reliably
    # with all MCP client implementations (similar to resources)
    service = create_translation_service()

    try:
        # Enforce reasonable limits to prevent MCP token overflow
        limit = max(1, min(limit, 20))  # Between 1 and 20 (reduced from 50)

        translations = await service.translate_to_franconian(
            german_word, scope, town, exact_match
        )

        if not translations:
            return []

        # Return only top N results (already sorted by confidence in service)
        return translations[:limit]

    except ValidationError as e:
        logger.error(f"Validation error: {e}", exc_info=True)
        raise ValueError(f"Invalid input: {e}") from e
    except BDOError as e:
        logger.error(f"BDO API error: {e}", exc_info=True)
        raise RuntimeError(f"Translation search failed: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error in find_franconian_equivalent: {e}", exc_info=True)
        raise RuntimeError(f"Translation search failed unexpectedly: {e}") from e
    finally:
        # Clean up the service instance
        await service.close()


@mcp.resource("franconian://word/{german_word}")
async def get_franconian_word_info(german_word: str) -> str:
    """Get comprehensive information about Franconian translation of a German word."""
    # Resources don't support Context injection in current FastMCP version
    # Create service inline for now
    service = create_translation_service()

    try:
        translations = await service.translate_to_franconian(german_word, limit=5)

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

    except ValidationError as e:
        logger.error(f"Validation error in word resource: {e}", exc_info=True)
        return f"Invalid input for '{german_word}': {e}"
    except BDOError as e:
        logger.error(f"BDO API error in word resource: {e}", exc_info=True)
        return f"Failed to retrieve Franconian information for '{german_word}': {e}"
    except Exception as e:
        logger.error(f"Unexpected error in word resource: {e}", exc_info=True)
        return f"Unexpected error retrieving Franconian information for '{german_word}': {e}"


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
        ("groß", "groß"),
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
    include_etymology: bool = False,
) -> str:
    """Generate a prompt for translating German words to Franconian dialect."""
    prompt_parts = [
        f"Help me find the Franconian dialect equivalent for the Standard German word '{german_word}' "
        f"as used in the Ansbach region (Landkreis Ansbach) in the context of {context}."
    ]

    prompt_parts.append(
        "Please search the BDO (Bayerns Dialekte Online) database and provide:"
    )

    prompt_parts.extend(
        [
            "1. The local Franconian/Ansbach dialect version",
            "2. Usage examples from the region",
            "3. Location-specific variations within Landkreis Ansbach",
            "4. Grammatical information if available",
        ]
    )

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
    """Run the MCP server with proper cleanup via lifespan context."""
    logger.info("Starting Franconian Translation MCP Server")
    mcp.run()
