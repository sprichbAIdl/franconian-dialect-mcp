#!/usr/bin/env python3
"""
MCP Tool for Franconian Translation using BDO API

Refactored with modern Python 3.13+ patterns, proper separation of concerns,
and strategic design patterns for maintainability.
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
from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.models import (
    Resource,
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource,
)
from mcp.types import (
    CallToolRequest,
    CallToolResult,
    ListResourcesRequest,
    ListResourcesResult,
    ListToolsRequest,
    ListToolsResult,
    ReadResourceRequest,
    ReadResourceResult,
)
from pydantic import BaseModel, Field, field_validator, model_validator


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


class BavarianRegion(StrEnum):
    """Bavarian administrative regions (Regierungsbezirke)."""
    MITTELFRANKEN = "Mittelfranken"
    OBERFRANKEN = "Oberfranken"
    UNTERFRANKEN = "Unterfranken"
    OBERPFALZ = "Oberpfalz"
    NIEDERBAYERN = "Niederbayern"
    OBERBAYERN = "Oberbayern"
    SCHWABEN = "Schwaben"


class FranconianTown(StrEnum):
    """Major Franconian towns with neighboring area data."""
    ANSBACH = "Ansbach"
    NUERNBERG = "Nürnberg"
    BAMBERG = "Bamberg"
    WUERZBURG = "Würzburg"
    BAYREUTH = "Bayreuth"
    ERLANGEN = "Erlangen"
    COBURG = "Coburg"


class BDOApiError(Exception):
    """Custom exception for BDO API related errors."""
    
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


# Modern Pydantic Models (No more barbaric dataclasses!)
class SearchParameters(BaseModel):
    """Search parameters with proper validation at system boundary."""
    german_word: str = Field(min_length=1, description="German word to translate")
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


class SearchResult(BaseModel):
    """Search result with comprehensive metadata."""
    success: bool
    query: str
    results: list[dict[str, Any]] = Field(default_factory=list)
    count: int = 0
    searched_areas: list[str] = Field(default_factory=list)
    error: str | None = None
    debug_info: str | None = None
    parameters_used: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode='after')
    def validate_count(self) -> Self:
        """Auto-calculate count if not provided."""
        if self.count == 0:
            self.count = len(self.results)
        return self


# Strategy Pattern Implementation
class SearchStrategy(ABC):
    """Abstract base class for search strategies."""
    
    @abstractmethod
    async def execute_search(
        self, 
        params: SearchParameters, 
        api_client: 'BDOApiClient'
    ) -> SearchResult:
        """Execute the search strategy."""
        pass


class BasicSearchStrategy(SearchStrategy):
    """Basic search without neighboring areas."""
    
    async def execute_search(
        self, 
        params: SearchParameters, 
        api_client: 'BDOApiClient'
    ) -> SearchResult:
        """Execute basic search strategy."""
        api_params = BDOApiParams.from_search_params(params)
        
        try:
            response_data = await api_client.make_request(api_params)
            results = api_client.extract_results(response_data)
            
            return SearchResult(
                success=True,
                query=params.german_word,
                results=results,
                searched_areas=[params.county or "all"],
                parameters_used=api_params.model_dump(exclude_none=True)
            )
        except BDOApiError as e:
            return SearchResult(
                success=False,
                query=params.german_word,
                error=str(e),
                debug_info="API request failed",
                parameters_used=api_params.model_dump(exclude_none=True)
            )


class NeighboringAreasSearchStrategy(SearchStrategy):
    """Search strategy that includes neighboring areas."""
    
    # Neighboring areas mapping
    NEIGHBORING_AREAS: Final[dict[str, list[str]]] = {
        FranconianTown.ANSBACH: ["Ansbach", "Neustadt a.d. Aisch", "Weißenburg", "Rothenburg ob der Tauber"],
        FranconianTown.NUERNBERG: ["Nürnberg", "Fürth", "Erlangen", "Schwabach", "Neumarkt"],
        FranconianTown.BAMBERG: ["Bamberg", "Forchheim", "Coburg", "Lichtenfels"],
        FranconianTown.WUERZBURG: ["Würzburg", "Schweinfurt", "Bad Kissingen", "Main-Spessart"],
        FranconianTown.BAYREUTH: ["Bayreuth", "Kulmbach", "Hof", "Kronach"],
        FranconianTown.ERLANGEN: ["Erlangen", "Nürnberg", "Fürth", "Forchheim"],
        FranconianTown.COBURG: ["Coburg", "Bamberg", "Lichtenfels", "Kronach"]
    }
    
    async def execute_search(
        self, 
        params: SearchParameters, 
        api_client: 'BDOApiClient'
    ) -> SearchResult:
        """Execute neighboring areas search strategy."""
        counties_to_search = self._get_counties_to_search(params)
        
        all_results: list[dict[str, Any]] = []
        search_areas: list[str] = []
        
        for search_county in counties_to_search:
            # Create new parameters for each county search
            county_params = params.model_copy(
                update={
                    'county': search_county,
                    'include_neighboring': False  # Prevent recursion
                }
            )
            
            try:
                api_params = BDOApiParams.from_search_params(county_params)
                response_data = await api_client.make_request(api_params)
                results = api_client.extract_results(response_data)
                
                all_results.extend(results)
                search_areas.append(search_county or "all")
                
                # Break early if we have enough results
                if len(all_results) >= params.limit:
                    all_results = all_results[:params.limit]
                    break
                    
            except BDOApiError:
                # Continue with other counties if one fails
                continue
        
        return SearchResult(
            success=True,
            query=params.german_word,
            results=all_results,
            searched_areas=search_areas,
            parameters_used={"strategy": "neighboring_areas", "counties": counties_to_search}
        )
    
    def _get_counties_to_search(self, params: SearchParameters) -> list[str]:
        """Get list of counties to search based on parameters."""
        if not params.include_neighboring or not params.county:
            return [params.county] if params.county else [None]
        
        town_key = next(
            (town for town in FranconianTown if town.value == params.county),
            None
        )
        
        if town_key and town_key in self.NEIGHBORING_AREAS:
            return self.NEIGHBORING_AREAS[town_key]
        
        return [params.county]


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


# Main Tool Class (Now Much Cleaner!)
class FranconianTranslationTool:
    """
    Modern Franconian translation tool using strategy and factory patterns.
    
    This refactored version follows proper separation of concerns and
    eliminates the monolithic class problem described in the design patterns.
    """
    
    def __init__(self) -> None:
        """Initialize the translation tool."""
        self.api_client = BDOApiClient()
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def search_translation(self, params: SearchParameters) -> SearchResult:
        """
        Search for Franconian translations using appropriate strategy.
        
        This method delegates to the appropriate strategy based on parameters,
        following the Strategy pattern to avoid bloated conditional logic.
        """
        try:
            strategy = SearchStrategyFactory.create_strategy(params)
            return await strategy.execute_search(params, self.api_client)
        except Exception as e:
            self.logger.exception(f"Unexpected error searching for {params.german_word}")
            return SearchResult(
                success=False,
                query=params.german_word,
                error=f"Unexpected error: {e}",
                debug_info="Unexpected error during search"
            )
    
    async def search_ansbach_area(
        self, 
        german_word: str, 
        limit: int = DEFAULT_RESULTS_LIMIT, 
        include_neighbors: bool = True
    ) -> SearchResult:
        """Convenience method for searching in Ansbach area."""
        params = SearchParameters(
            german_word=german_word,
            limit=limit,
            region=BavarianRegion.MITTELFRANKEN,
            county=FranconianTown.ANSBACH.value,
            project=BDOProject.WBF,
            include_neighboring=include_neighbors
        )
        return await self.search_translation(params)
    
    async def search_with_neighbors(
        self, 
        german_word: str, 
        town: FranconianTown, 
        limit: int = DEFAULT_RESULTS_LIMIT
    ) -> SearchResult:
        """Search for translations in a town and neighboring areas."""
        params = SearchParameters(
            german_word=german_word,
            limit=limit,
            county=town.value,
            project=BDOProject.WBF,
            include_neighboring=True
        )
        return await self.search_translation(params)
    
    def get_neighboring_areas(self, town: FranconianTown) -> dict[str, Any]:
        """Get neighboring areas for a specific town."""
        strategy = NeighboringAreasSearchStrategy()
        
        if town not in strategy.NEIGHBORING_AREAS:
            return {
                'success': False,
                'error': f"Town '{town.value}' not found",
                'available_towns': [t.value for t in FranconianTown]
            }
        
        return {
            'success': True,
            'town': town.value,
            'neighbors': strategy.NEIGHBORING_AREAS[town],
            'total_areas': len(strategy.NEIGHBORING_AREAS[town])
        }
    
    def get_all_neighboring_areas(self) -> dict[str, list[str]]:
        """Get all available towns and their neighboring areas."""
        strategy = NeighboringAreasSearchStrategy()
        return {town.value: areas for town, areas in strategy.NEIGHBORING_AREAS.items()}
    
    def get_franconian_regions(self) -> list[str]:
        """Get list of Franconian regions."""
        return [
            BavarianRegion.MITTELFRANKEN.value,
            BavarianRegion.OBERFRANKEN.value,
            BavarianRegion.UNTERFRANKEN.value
        ]
    
    def get_common_counties(self) -> dict[str, list[str]]:
        """Get common counties for each Franconian region."""
        return {
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
    
    def format_translation_result(self, result: SearchResult) -> str:
        """Format a translation result for display."""
        if not result.success:
            error_msg = f"Error: {result.error}"
            if result.debug_info:
                error_msg += f"\nDebug: {result.debug_info}"
            return error_msg
        
        if result.count == 0:
            return f"No Franconian translations found for '{result.query}'"
        
        output_lines = [
            f"Franconian translations for '{result.query}' ({result.count} results):",
            "=" * 50
        ]
        
        if result.searched_areas != ['all']:
            output_lines.append(f"Search areas: {', '.join(result.searched_areas)}")
            output_lines.append("")
        
        for i, doc in enumerate(result.results[:10], 1):
            if isinstance(doc, dict):
                franconian = doc.get('franconian', 
                    doc.get('translation', 
                        doc.get('word', 
                            doc.get('lemma', 'N/A'))))
                german = doc.get('german', 
                    doc.get('source', result.query))
                definition = doc.get('definition', 
                    doc.get('meaning', 
                        doc.get('bedeutung', '')))
                location = doc.get('location', 
                    doc.get('region', 
                        doc.get('ort', '')))
                
                output_lines.append(f"{i}. {franconian}")
                if german != result.query:
                    output_lines.append(f"   German: {german}")
                if definition:
                    output_lines.append(f"   Definition: {definition}")
                if location:
                    output_lines.append(f"   Location: {location}")
                output_lines.append("")
            else:
                output_lines.append(f"{i}. {str(doc)}")
        
        return "\n".join(output_lines)
    
    async def close(self) -> None:
        """Close resources."""
        await self.api_client.close()


# Initialize MCP server and tool instance
app = Server("franconian-translation-tool")
translation_tool = FranconianTranslationTool()


@app.list_tools()
async def handle_list_tools() -> list[Tool]:
    """List available tools with comprehensive type safety."""
    return [
        Tool(
            name="search_franconian_translation",
            description="Search for Franconian translations with advanced location-based filtering",
            inputSchema={
                "type": "object",
                "properties": {
                    "german_word": {
                        "type": "string",
                        "description": "German word to translate to Franconian",
                        "minLength": 1
                    },
                    "limit": {
                        "type": "integer",
                        "description": f"Maximum results to return (1-{MAX_RESULTS_PER_QUERY})",
                        "default": DEFAULT_RESULTS_LIMIT,
                        "minimum": 1,
                        "maximum": MAX_RESULTS_PER_QUERY
                    },
                    "exact_match": {
                        "type": "boolean",
                        "description": "Search for exact matches only",
                        "default": False
                    },
                    "region": {
                        "type": "string",
                        "description": "Administrative region filter",
                        "enum": [r.value for r in BavarianRegion]
                    },
                    "county": {
                        "type": "string", 
                        "description": "County/district filter (historical pre-1970s boundaries)"
                    },
                    "project": {
                        "type": "string",
                        "description": "Dictionary project to search",
                        "enum": [p.value for p in BDOProject]
                    },
                    "include_neighboring": {
                        "type": "boolean",
                        "description": "Include neighboring counties in search",
                        "default": False
                    }
                },
                "required": ["german_word"],
                "additionalProperties": False
            }
        ),
        Tool(
            name="search_ansbach_area",
            description="Search specifically in Ansbach and optionally neighboring areas",
            inputSchema={
                "type": "object", 
                "properties": {
                    "german_word": {
                        "type": "string",
                        "description": "German word to translate",
                        "minLength": 1
                    },
                    "limit": {
                        "type": "integer",
                        "description": f"Maximum results (1-{MAX_RESULTS_PER_QUERY})",
                        "default": DEFAULT_RESULTS_LIMIT,
                        "minimum": 1,
                        "maximum": MAX_RESULTS_PER_QUERY
                    },
                    "include_neighbors": {
                        "type": "boolean", 
                        "description": "Include neighboring areas",
                        "default": True
                    }
                },
                "required": ["german_word"],
                "additionalProperties": False
            }
        ),
        Tool(
            name="search_with_neighbors",
            description="Search in specific town and neighboring areas",
            inputSchema={
                "type": "object",
                "properties": {
                    "german_word": {
                        "type": "string",
                        "description": "German word to translate",
                        "minLength": 1
                    },
                    "town": {
                        "type": "string",
                        "description": "Main town to search around",
                        "enum": [t.value for t in FranconianTown]
                    },
                    "limit": {
                        "type": "integer",
                        "description": f"Maximum results (1-{MAX_RESULTS_PER_QUERY})",
                        "default": DEFAULT_RESULTS_LIMIT,
                        "minimum": 1,
                        "maximum": MAX_RESULTS_PER_QUERY
                    }
                },
                "required": ["german_word", "town"],
                "additionalProperties": False
            }
        ),
        Tool(
            name="get_franconian_regions",
            description="Get available Franconian administrative regions",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False
            }
        ),
        Tool(
            name="get_neighboring_areas",
            description="Get neighboring areas for specific town",
            inputSchema={
                "type": "object",
                "properties": {
                    "town": {
                        "type": "string", 
                        "description": "Town to get neighbors for",
                        "enum": [t.value for t in FranconianTown]
                    }
                },
                "required": ["town"],
                "additionalProperties": False
            }
        ),
        Tool(
            name="get_all_neighboring_areas",
            description="Get all towns and their neighboring areas",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False
            }
        )
    ]


@app.call_tool()
async def handle_call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls with comprehensive error handling and type safety."""
    try:
        match name:
            case "search_franconian_translation":
                params = SearchParameters(**arguments)
                result = await translation_tool.search_translation(params)
                formatted_result = translation_tool.format_translation_result(result)
                return [TextContent(type="text", text=formatted_result)]
            
            case "search_ansbach_area":
                result = await translation_tool.search_ansbach_area(
                    arguments["german_word"],
                    arguments.get("limit", DEFAULT_RESULTS_LIMIT),
                    arguments.get("include_neighbors", True)
                )
                
                neighbors_text = " and neighboring areas" if arguments.get("include_neighbors", True) else " area only"
                formatted_result = translation_tool.format_translation_result(result)
                
                return [TextContent(
                    type="text", 
                    text=f"Franconian words from Ansbach{neighbors_text}:\n{formatted_result}"
                )]
            
            case "search_with_neighbors":
                town = FranconianTown(arguments["town"])
                result = await translation_tool.search_with_neighbors(
                    arguments["german_word"],
                    town,
                    arguments.get("limit", DEFAULT_RESULTS_LIMIT)
                )
                
                formatted_result = translation_tool.format_translation_result(result)
                return [TextContent(
                    type="text",
                    text=f"Franconian words from {town.value} and neighboring areas:\n{formatted_result}"
                )]
            
            case "get_franconian_regions":
                regions = translation_tool.get_franconian_regions()
                regions_text = "Franconian Regions (Regierungsbezirke):\n" + "\n".join(f"• {region}" for region in regions)
                return [TextContent(type="text", text=regions_text)]
            
            case "get_neighboring_areas":
                town = FranconianTown(arguments["town"])
                result = translation_tool.get_neighboring_areas(town)
                
                if not result['success']:
                    error_text = f"Error: {result['error']}\n\nAvailable towns: {', '.join(result['available_towns'])}"
                    return [TextContent(type="text", text=error_text)]
                
                neighbors_text = (f"Neighboring areas for {result['town']}:\n" +
                                "\n".join(f"• {area}" for area in result['neighbors']) +
                                f"\n\nTotal areas: {result['total_areas']}")
                
                return [TextContent(type="text", text=neighbors_text)]
            
            case "get_all_neighboring_areas":
                areas = translation_tool.get_all_neighboring_areas()
                result_text = "All available towns with neighboring areas:\n\n"
                
                for town, neighbors in areas.items():
                    result_text += f"🏘️  {town}:\n   {', '.join(neighbors)}\n\n"
                
                return [TextContent(type="text", text=result_text.strip())]
            
            case _:
                return [TextContent(type="text", text=f"Unknown tool: {name}")]
    
    except ValueError as e:
        return [TextContent(type="text", text=f"Invalid parameter: {e}")]
    except KeyError as e:
        return [TextContent(type="text", text=f"Missing required parameter: {e}")]
    except Exception as e:
        logging.exception(f"Unexpected error in tool {name}")
        return [TextContent(type="text", text=f"Unexpected error: {e}")]


async def main() -> None:
    """Main entry point with proper resource management."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    try:
        from mcp.server.stdio import stdio_server
        
        async with stdio_server() as (read_stream, write_stream):
            await app.run(
                read_stream, 
                write_stream, 
                InitializationOptions(
                    server_name="franconian-translation-tool",
                    server_version="2.0.0",
                    capabilities=app.get_capabilities(
                        notification_options=None,
                        experimental_capabilities={},
                    ),
                ),
            )
    except KeyboardInterrupt:
        logging.info("Shutting down gracefully...")
    except Exception:
        logging.exception("Fatal error occurred")
        raise
    finally:
        await translation_tool.close()


if __name__ == "__main__":
    asyncio.run(main())