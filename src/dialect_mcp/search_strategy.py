

# Strategy Pattern Implementation
from abc import ABC, abstractmethod
from typing import Any, Final
from mcp import ServerSession

from mcp.server.fastmcp import Context, FastMCP

from src.dialect_mcp.error import BDOApiError
from src.dialect_mcp.geography import FranconianTown
from src.dialect_mcp.mcp import BDOApiClient, BDOApiParams, SearchParameters, TranslationEntry, TranslationResult


class SearchStrategy(ABC):
    """Abstract base class for search strategies."""
    
    @abstractmethod
    async def execute_search(
        self, 
        params: SearchParameters, 
        api_client: 'BDOApiClient',
        ctx: Context[ServerSession, None] | None = None
    ) -> TranslationResult:
        """Execute the search strategy."""
        pass


class BasicSearchStrategy(SearchStrategy):
    """Basic search without neighboring areas."""
    
    async def execute_search(
        self, 
        params: SearchParameters, 
        api_client: 'BDOApiClient',
        ctx: Context[ServerSession, None] | None = None
    ) -> TranslationResult:
        """Execute basic search strategy."""
        try:
            if ctx:
                await ctx.info(f"Searching for '{params.german_word}' in BDO database")
            
            api_params = BDOApiParams.from_search_params(params)
            response_data = await api_client.make_request(api_params)
            raw_results = api_client.extract_results(response_data)
            
            # Convert raw results to structured format
            translations = []
            for raw_result in raw_results[:params.limit]:
                translation = self._convert_raw_result(raw_result, params.german_word)
                translations.append(translation)
            
            if ctx:
                await ctx.info(f"Found {len(translations)} translations")
            
            return TranslationResult(
                query=params.german_word,
                total_results=len(translations),
                searched_areas=[params.county or "all"],
                translations=translations,
                success=True
            )
            
        except BDOApiError as e:
            error_msg = f"API error: {e}"
            if ctx:
                await ctx.error(error_msg)
            
            return TranslationResult(
                query=params.german_word,
                total_results=0,
                searched_areas=[],
                translations=[],
                success=False,
                error_message=error_msg
            )
        except Exception as e:
            error_msg = f"Unexpected error: {e}"
            if ctx:
                await ctx.error(error_msg)
            
            return TranslationResult(
                query=params.german_word,
                total_results=0,
                searched_areas=[],
                translations=[],
                success=False,
                error_message=error_msg
            )
    
    def _convert_raw_result(self, raw_result: dict[str, Any], query: str) -> TranslationEntry:
        """Convert raw API result to structured TranslationEntry."""
        if isinstance(raw_result, dict):
            franconian = raw_result.get('franconian', 
                raw_result.get('translation', 
                    raw_result.get('word', 
                        raw_result.get('lemma', 'N/A'))))
            german = raw_result.get('german', 
                raw_result.get('source', query))
            definition = raw_result.get('definition', 
                raw_result.get('meaning', 
                    raw_result.get('bedeutung', '')))
            location = raw_result.get('location', 
                raw_result.get('region', 
                    raw_result.get('ort', '')))
            project = raw_result.get('project', '')
            
            return TranslationEntry(
                franconian_word=franconian,
                german_word=german,
                definition=definition if definition else None,
                location=location if location else None,
                source_project=project if project else None
            )
        else:
            return TranslationEntry(
                franconian_word=str(raw_result),
                german_word=query
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
        api_client: 'BDOApiClient',
        ctx: Context[ServerSession, None] | None = None
    ) -> TranslationResult:
        """Execute neighboring areas search strategy."""
        counties_to_search = self._get_counties_to_search(params)
        
        if ctx:
            await ctx.info(f"Searching in {len(counties_to_search)} areas: {', '.join(counties_to_search)}")
        
        all_translations: list[TranslationEntry] = []
        search_areas: list[str] = []
        basic_strategy = BasicSearchStrategy()
        
        for i, search_county in enumerate(counties_to_search):
            if ctx:
                progress = (i + 1) / len(counties_to_search)
                await ctx.report_progress(
                    progress=progress,
                    total=1.0,
                    message=f"Searching in {search_county or 'all areas'}"
                )
            
            # Create new parameters for each county search
            county_params = params.model_copy(
                update={
                    'county': search_county,
                    'include_neighboring': False  # Prevent recursion
                }
            )
            
            try:
                result = await basic_strategy.execute_search(county_params, api_client)
                if result.success:
                    all_translations.extend(result.translations)
                    search_areas.append(search_county or "all")
                
                # Break early if we have enough results
                if len(all_translations) >= params.limit:
                    all_translations = all_translations[:params.limit]
                    break
                    
            except Exception:
                # Continue with other counties if one fails
                continue
        
        if ctx:
            await ctx.info(f"Completed search across {len(search_areas)} areas")
        
        return TranslationResult(
            query=params.german_word,
            total_results=len(all_translations),
            searched_areas=search_areas,
            translations=all_translations,
            success=True
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
