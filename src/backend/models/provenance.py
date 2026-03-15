"""
DrugTree - Provenance Tracking Models

Tracks data sources, retrieval timestamps, and confidence scores for drug data.
Uses JSONB field in database (not separate table) for flexibility.
"""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class ProvenanceSource(BaseModel):
    """Single data source with retrieval metadata"""

    source: str = Field(
        ...,
        description="Source identifier (e.g., 'chembl', 'pubchem', 'who_atc', 'kegg')",
        min_length=1,
        max_length=50,
    )
    url: Optional[str] = Field(
        None, description="URL or API endpoint where data was retrieved"
    )
    retrieved_at: datetime = Field(
        default_factory=datetime.utcnow, description="Timestamp when data was retrieved"
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence score (0.0-1.0) for this source's data quality",
    )
    notes: Optional[str] = Field(
        None, description="Optional notes about data quality or retrieval context"
    )

    @field_validator("source")
    @classmethod
    def validate_source(cls, v: str) -> str:
        """Ensure source is lowercase alphanumeric with underscores"""
        import re

        if not re.match(r"^[a-z0-9_]+$", v):
            raise ValueError(
                f"Source must be lowercase alphanumeric with underscores: {v}"
            )
        return v


class Provenance(BaseModel):
    """
    Complete provenance record for a drug

    Tracks all data sources, last update time, and version for audit trails.
    Stored as JSONB field in drugs table.
    """

    sources: List[ProvenanceSource] = Field(
        default_factory=list, description="List of data sources with retrieval metadata"
    )
    last_updated: datetime = Field(
        default_factory=datetime.utcnow, description="Most recent update timestamp"
    )
    version: int = Field(
        default=1, ge=1, description="Version number for this provenance record"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When this provenance record was first created",
    )

    @field_validator("sources")
    @classmethod
    def validate_unique_sources(
        cls, v: List[ProvenanceSource]
    ) -> List[ProvenanceSource]:
        """Ensure no duplicate source identifiers"""
        source_ids = [s.source for s in v]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("Duplicate source identifiers not allowed")
        return v

    def get_source(self, source_id: str) -> Optional[ProvenanceSource]:
        """Get a specific source by ID"""
        for source in self.sources:
            if source.source == source_id:
                return source
        return None

    def has_source(self, source_id: str) -> bool:
        """Check if a source exists"""
        return self.get_source(source_id) is not None

    def get_highest_confidence(self) -> float:
        """Get the highest confidence score across all sources"""
        if not self.sources:
            return 0.0
        return max(s.confidence for s in self.sources)

    def get_average_confidence(self) -> float:
        """Get average confidence score across all sources"""
        if not self.sources:
            return 0.0
        return sum(s.confidence for s in self.sources) / len(self.sources)


def add_provenance(
    provenance: Optional[Provenance],
    source: str,
    url: Optional[str] = None,
    confidence: float = 1.0,
    notes: Optional[str] = None,
) -> Provenance:
    """
    Add or update a source in a provenance record

    Args:
        provenance: Existing provenance record (or None to create new)
        source: Source identifier (e.g., 'chembl', 'pubchem')
        url: Optional URL or API endpoint
        confidence: Confidence score (0.0-1.0)
        notes: Optional notes about data quality

    Returns:
        Updated provenance record with new source added/updated

    Example:
        >>> prov = None
        >>> prov = add_provenance(prov, "chembl", "https://ebi.ac.uk/chembl", 0.95)
        >>> prov = add_provenance(prov, "pubchem", "https://pubchem.ncbi.nlm.nih.gov", 0.9)
        >>> prov.has_source("chembl")
        True
    """
    # Create new provenance if None
    if provenance is None:
        provenance = Provenance()

    # Create new source
    new_source = ProvenanceSource(
        source=source,
        url=url,
        confidence=confidence,
        notes=notes,
        retrieved_at=datetime.utcnow(),
    )

    # Remove existing source with same ID (if exists)
    provenance.sources = [s for s in provenance.sources if s.source != source]

    # Add new source
    provenance.sources.append(new_source)

    # Update timestamps and version
    provenance.last_updated = datetime.utcnow()
    provenance.version += 1

    return provenance


def merge_provenance(
    primary: Provenance, secondary: Provenance, keep_highest_confidence: bool = True
) -> Provenance:
    """
    Merge two provenance records

    Args:
        primary: Primary provenance record (takes precedence for conflicts)
        secondary: Secondary provenance record to merge
        keep_highest_confidence: If True, keep highest confidence for duplicate sources

    Returns:
        Merged provenance record

    Example:
        >>> prov1 = Provenance(sources=[ProvenanceSource(source="chembl", confidence=0.9)])
        >>> prov2 = Provenance(sources=[ProvenanceSource(source="pubchem", confidence=0.95)])
        >>> merged = merge_provenance(prov1, prov2)
        >>> len(merged.sources)
        2
    """
    # Start with primary sources
    source_map = {s.source: s for s in primary.sources}

    # Add or merge secondary sources
    for sec_source in secondary.sources:
        if sec_source.source in source_map:
            if keep_highest_confidence:
                # Keep the source with higher confidence
                if sec_source.confidence > source_map[sec_source.source].confidence:
                    source_map[sec_source.source] = sec_source
            # Otherwise keep primary
        else:
            # Add new source
            source_map[sec_source.source] = sec_source

    # Create merged provenance
    merged = Provenance(
        sources=list(source_map.values()),
        last_updated=datetime.utcnow(),
        version=max(primary.version, secondary.version) + 1,
        created_at=min(primary.created_at, secondary.created_at),
    )

    return merged


def create_provenance_from_dict(data: dict) -> Provenance:
    """
    Create provenance from dictionary (for loading from JSONB)

    Args:
        data: Dictionary with provenance fields

    Returns:
        Provenance object

    Example:
        >>> data = {
        ...     "sources": [
        ...         {"source": "chembl", "url": "https://ebi.ac.uk", "confidence": 0.95}
        ...     ],
        ...     "version": 1
        ... }
        >>> prov = create_provenance_from_dict(data)
        >>> prov.sources[0].source
        'chembl'
    """
    # Parse sources
    sources = []
    for source_data in data.get("sources", []):
        sources.append(ProvenanceSource(**source_data))

    # Create provenance
    return Provenance(
        sources=sources,
        last_updated=data.get("last_updated", datetime.utcnow()),
        version=data.get("version", 1),
        created_at=data.get("created_at", datetime.utcnow()),
    )
