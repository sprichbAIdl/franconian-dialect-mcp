#!/usr/bin/env python3
"""
MCP Tool for Franconian Translation using BDO API

Modern MCP-compliant implementation with proper resource exposure,
structured output, and comprehensive error handling.

Requires Python 3.13+ for modern typing features.
"""

from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from enum import StrEnum
from pathlib import Path
from typing import Any, AsyncGenerator, Final, Literal, Self
from urllib.parse import quote_plus

import httpx
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession
from mcp.types import TextContent
from pydantic import BaseModel, Field, field_validator, model_validator

from src.dialect_mcp.error import BDOApiError
from src.dialect_mcp.geography import BavarianRegion, FranconianTown, NeighboringAreasInfo
from src.dialect_mcp.search_strategy import BasicSearchStrategy, NeighboringAreasSearchStrategy, SearchStrategy


# Constants
BASE_URL: Final[str] = "https://bdo.badw.de"
SEARCH_ENDPOINT: Final[str] = f"{BASE_URL}/suche"
REQUEST_TIMEOUT: Final[float] = 60.0
MAX_RESULTS_PER_QUERY: Final[int] = 50
DEFAULT_RESULTS_LIMIT: Final[int] = 10


class BDOProject(StrEnum):
    """BDO dictionary projects."""
    WBF = "WBF"  # Fränkisches Wörterbuch (Franconian Dictionary)
    BWB = "BWB"  # Bayerisches Wörterbuch (Bavarian Dictionary)
    DIBS = "DIBS"  # Dialektologisches Informationssystem von Bayerisch-Schwaben



# Structured Output Models for MCP
class TranslationEntry(BaseModel):
    """Single translation entry with structured data."""
    franconian_word: str = Field(description="Franconian dialect word")
    german_word: str = Field(description="German source word")
    definition: str | None = Field(default=None, description="Definition or meaning")
    location: str | None = Field(default=None, description="Geographic location")
    source_project: str | None = Field(default=None, description="Dictionary project source")


class TranslationResult(BaseModel):
    """Structured translation result for MCP tools."""
    query: str = Field(description="Original German word searched")
    total_results: int = Field(description="Total number of results found")
    searched_areas: list[str] = Field(description="Geographic areas searched")
    translations: list[TranslationEntry] = Field(description="Found translations")
    success: bool = Field(description="Whether the search was successful")
    error_message: str | None = Field(default=None, description="Error message if failed")




# Internal Models (not exposed to MCP)
class SearchParameters(BaseModel):
    """Internal search parameters."""
    german_word: str = Field(min_length=1)
    limit: int = Field(default=DEFAULT_RESULTS_LIMIT, ge=1, le=MAX_RESULTS_PER_QUERY)
    exact_match: bool = False
    region: BavarianRegion | None = None
    county: str | None = None
    project: BDOProject | None = None
    include_neighboring: bool = False

    @field_validator('german_word')
    @classmethod
    def validate_german_word(cls, v: str) -> str:
        """Validate and normalize German word input."""
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("german_word cannot be empty")
        return cleaned


class BDOApiParams(BaseModel):
    """Validated API parameters for BDO requests."""
    stichwort: str
    anzahl: int = Field(ge=1, le=MAX_RESULTS_PER_QUERY)
    format: Literal["json"] = "json"
    exakt: Literal["1"] | None = None
    regbez: str | None = None
    kreis: str | None = None
    projekt: str | None = None

    @classmethod
    def from_search_params(cls, params: SearchParameters) -> Self:
        """Convert search parameters to API parameters."""
        return cls(
            stichwort=params.german_word,
            anzahl=params.limit,
            exakt="1" if params.exact_match else None,
            regbez=params.region.value if params.region else None,
            kreis=params.county,
            projekt=params.project.value if params.project else None
        )


# Template Method Pattern for API Operations
class BDOApiClient:
    """Template method pattern for BDO API operations."""
    
    def __init__(self) -> None:
        """Initialize API client."""
        self._client: httpx.AsyncClient | None = None
        self.logger = logging.getLogger(self.__class__.__name__)
        self._setup_logging()
    
    def _setup_logging(self) -> None:
        """Configure logging for the client."""
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
    
    @property
    def client(self) -> httpx.AsyncClient:
        """Get or create HTTP client instance."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(REQUEST_TIMEOUT),
                follow_redirects=True,
                headers={
                    'User-Agent': 'Franconian-Translation-MCP-Tool/2.0 (Python/3.13)',
                    'Accept': 'application/json, text/html, */*',
                    'Accept-Language': 'de-DE,de;q=0.9,en;q=0.8'
                }
            )
        return self._client
    
    async def close(self) -> None:
        """Close the HTTP client and cleanup resources."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
    
    @asynccontextmanager
    async def _managed_client(self) -> AsyncGenerator[httpx.AsyncClient, None]:
        """Async context manager for HTTP client."""
        try:
            yield self.client
        except Exception:
            await self.close()
            raise
    
    async def make_request(self, params: BDOApiParams) -> dict[str, Any]:
        """Template method for making API requests - throws exceptions on failure."""
        async with self._managed_client() as client:
            try:
                self.logger.debug(f"Making API request with params: {params}")
                
                response = await client.get(
                    SEARCH_ENDPOINT, 
                    params=params.model_dump(exclude_none=True)
                )
                response.raise_for_status()
                
                return self._parse_response(response)
                
            except httpx.HTTPStatusError as e:
                raise BDOApiError(f"HTTP {e.response.status_code}: {e.response.reason_phrase}", e.response.status_code)
            except httpx.RequestError as e:
                raise BDOApiError(f"Network error: {e}")
            except json.JSONDecodeError as e:
                raise BDOApiError(f"Invalid JSON response: {e}")
    
    def _parse_response(self, response: httpx.Response) -> dict[str, Any]:
        """Parse HTTP response to JSON."""
        content_type = response.headers.get('content-type', '').lower()
        
        if 'application/json' in content_type:
            return response.json()
        elif response.text.strip().startswith(('{', '[')):
            return response.json()
        else:
            raise BDOApiError("API returned HTML instead of JSON - parameter names may be incorrect")
    
    def extract_results(self, response_data: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract results from API response data."""
        if isinstance(response_data, dict):
            # Try common result field names
            for field in ('results', 'entries', 'items', 'documents', 'data'):
                if field in response_data:
                    results = response_data[field]
                    return results if isinstance(results, list) else [results]
            return [response_data]
        elif isinstance(response_data, list):
            return response_data
        else:
            return []


# Factory Method Pattern for Search Strategies
class SearchStrategyFactory:
    """Factory for creating appropriate search strategies."""
    
    @staticmethod
    def create_strategy(params: SearchParameters) -> SearchStrategy:
        """Create appropriate search strategy based on parameters."""
        if params.include_neighboring:
            return NeighboringAreasSearchStrategy()
        else:
            return BasicSearchStrategy()


# Create MCP server
mcp = FastMCP("Franconian Translation Tool")

# Initialize API client
api_client = BDOApiClient()


# MCP Resources - Expose static data
@mcp.resource("franconian://regions")
def get_franconian_regions() -> str:
    """Get available Franconian administrative regions."""
    regions = [
        BavarianRegion.MITTELFRANKEN.value,
        BavarianRegion.OBERFRANKEN.value,
        BavarianRegion.UNTERFRANKEN.value
    ]
    return json.dumps({
        "franconian_regions": regions,
        "description": "Administrative regions (Regierungsbezirke) in Franconia"
    }, indent=2, ensure_ascii=False)


@mcp.resource("franconian://towns")
def get_franconian_towns() -> str:
    """Get available Franconian towns with neighboring areas."""
    strategy = NeighboringAreasSearchStrategy()
    towns_data = {}
    
    for town in FranconianTown:
        if town in strategy.NEIGHBORING_AREAS:
            towns_data[town.value] = {
                "neighboring_areas": strategy.NEIGHBORING_AREAS[town],
                "total_neighbors": len(strategy.NEIGHBORING_AREAS[town])
            }
    
    return json.dumps({
        "franconian_towns": towns_data,
        "description": "Major Franconian towns and their neighboring areas"
    }, indent=2, ensure_ascii=False)


@mcp.resource("franconian://counties/{region}")
def get_counties_by_region(region: str) -> str:
    """Get common counties for a specific Franconian region."""
    counties_map = {
        BavarianRegion.MITTELFRANKEN.value: [
            "Ansbach", "Nürnberg", "Fürth", "Erlangen", 
            "Schwabach", "Neustadt a.d. Aisch", "Weißenburg"
        ],
        BavarianRegion.OBERFRANKEN.value: [
            "Bamberg", "Bayreuth", "Coburg", "Forchheim", 
            "Hof", "Kronach", "Kulmbach", "Lichtenfels"
        ],
        BavarianRegion.UNTERFRANKEN.value: [
            "Würzburg", "Aschaffenburg", "Schweinfurt", 
            "Bad Kissingen", "Rhön-Grabfeld", "Main-Spessart", "Miltenberg"
        ]
    }
    
    if region not in counties_map:
        return json.dumps({
            "error": f"Region '{region}' not found",
            "available_regions": list(counties_map.keys())
        }, indent=2)
    
    return json.dumps({
        "region": region,
        "counties": counties_map[region],
        "total_counties": len(counties_map[region])
    }, indent=2, ensure_ascii=False)


# MCP Tools with Structured Output
@mcp.tool()
async def search_franconian_translation(
    german_word: str,
    limit: int = DEFAULT_RESULTS_LIMIT,
    exact_match: bool = False,
    region: str | None = None,
    county: str | None = None,
    project: str | None = None,
    include_neighboring: bool = False,
    ctx: Context[ServerSession, None] | None = None
) -> TranslationResult:
    """
    Search for Franconian translations with advanced location-based filtering.
    
    Returns structured translation results with metadata.
    """
    try:
        # Validate and convert parameters
        region_enum = BavarianRegion(region) if region else None
        project_enum = BDOProject(project) if project else None
        
        params = SearchParameters(
            german_word=german_word,
            limit=limit,
            exact_match=exact_match,
            region=region_enum,
            county=county,
            project=project_enum,
            include_neighboring=include_neighboring
        )
        
        strategy = SearchStrategyFactory.create_strategy(params)
        result = await strategy.execute_search(params, api_client, ctx)
        
        return result
        
    except ValueError as e:
        return TranslationResult(
            query=german_word,
            total_results=0,
            searched_areas=[],
            translations=[],
            success=False,
            error_message=f"Invalid parameter: {e}"
        )
    except Exception as e:
        if ctx:
            await ctx.error(f"Unexpected error: {e}")
        
        return TranslationResult(
            query=german_word,
            total_results=0,
            searched_areas=[],
            translations=[],
            success=False,
            error_message=f"Unexpected error: {e}"
        )


@mcp.tool()
async def search_ansbach_area(
    german_word: str,
    limit: int = DEFAULT_RESULTS_LIMIT,
    include_neighbors: bool = True,
    ctx: Context[ServerSession, None] | None = None
) -> TranslationResult:
    """Search specifically in Ansbach and optionally neighboring areas."""
    return await search_franconian_translation(
        german_word=german_word,
        limit=limit,
        region=BavarianRegion.MITTELFRANKEN.value,
        county=FranconianTown.ANSBACH.value,
        project=BDOProject.WBF.value,
        include_neighboring=include_neighbors,
        ctx=ctx
    )


@mcp.tool()
async def search_with_neighbors(
    german_word: str,
    town: str,
    limit: int = DEFAULT_RESULTS_LIMIT,
    ctx: Context[ServerSession, None] | None = None
) -> TranslationResult:
    """Search for translations in a town and neighboring areas."""
    try:
        town_enum = FranconianTown(town)
        
        return await search_franconian_translation(
            german_word=german_word,
            limit=limit,
            county=town_enum.value,
            project=BDOProject.WBF.value,
            include_neighboring=True,
            ctx=ctx
        )
    except ValueError:
        return TranslationResult(
            query=german_word,
            total_results=0,
            searched_areas=[],
            translations=[],
            success=False,
            error_message=f"Town '{town}' not found. Available towns: {[t.value for t in FranconianTown]}"
        )


@mcp.tool()
def get_neighboring_areas(town: str) -> NeighboringAreasInfo:
    """Get neighboring areas for a specific town."""
    try:
        town_enum = FranconianTown(town)
        strategy = NeighboringAreasSearchStrategy()
        
        if town_enum not in strategy.NEIGHBORING_AREAS:
            raise ValueError(f"Town '{town}' not found in neighboring areas database")
        
        neighbors = strategy.NEIGHBORING_AREAS[town_enum]
        
        return NeighboringAreasInfo(
            town=town_enum.value,
            neighboring_areas=neighbors,
            total_count=len(neighbors)
        )
        
    except ValueError as e:
        # For structured output, we still need to return the expected type
        # but with error information
        return NeighboringAreasInfo(
            town=town,
            neighboring_areas=[],
            total_count=0
        )


@mcp.tool()
def get_all_neighboring_areas() -> dict[str, list[str]]:
    """Get all available towns and their neighboring areas."""
    strategy = NeighboringAreasSearchStrategy()
    return {town.value: areas for town, areas in strategy.NEIGHBORING_AREAS.items()}


@mcp.tool()
def get_franconian_regions() -> list[str]:
    """Get list of Franconian administrative regions."""
    return [
        BavarianRegion.MITTELFRANKEN.value,
        BavarianRegion.OBERFRANKEN.value,
        BavarianRegion.UNTERFRANKEN.value
    ]


# Cleanup on shutdown
async def cleanup():
    """Cleanup resources on shutdown."""
    await api_client.close()


if __name__ == "__main__":
    try:
        mcp.run()
    finally:
        asyncio.run(cleanup())