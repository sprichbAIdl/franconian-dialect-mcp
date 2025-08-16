
from enum import StrEnum

from pydantic import BaseModel, Field


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


class NeighboringAreasInfo(BaseModel):
    """Information about neighboring areas for a town."""
    town: str = Field(description="Main town name")
    neighboring_areas: list[str] = Field(description="List of neighboring areas")
    total_count: int = Field(description="Total number of neighboring areas")