"""
Dataset Manifest Model.

Defines the structure of a dataset version manifest to ensure 
experiment reproducibility. A manifest fingerprints a specific
processed dataset.
"""
import hashlib
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime, UTC
import pandas as pd
from pathlib import Path

@dataclass
class DatasetManifest:
    """
    Structured metadata representing a validated dataset snapshot.
    """
    dataset_id: str
    source: str
    instrument: str
    timeframe: str
    timezone: str
    row_count: int
    min_timestamp: str
    max_timestamp: str
    checksum: str
    creation_timestamp: str
    notes: str = ""
    schema: Dict[str, str] | None = None
    source_files: list[Dict[str, Any]] | None = None
    build_recipe: Dict[str, Any] | None = None
    checksum_version: str = "v2"

    @classmethod
    def create_from_dataframe(
        cls, 
        df: pd.DataFrame, 
        dataset_id: str, 
        source: str, 
        instrument: str, 
        timeframe: str,
        notes: str = ""
    ) -> 'DatasetManifest':
        """
        Derives a manifest directly from a normalized pandas dataframe.
        
        Args:
            df: Normalized dataframe (must contain 'datetime' column).
            dataset_id: Unique logical identifier (e.g., 'gold_1h_v1').
            source: Origin of the data (e.g., 'ibkr').
            instrument: Symbol (e.g., 'XAUUSD').
            timeframe: Aggregation (e.g., '1h').
            notes: Optional contextual details.
            
        Returns:
            DatasetManifest instance populated with metadata and checksum.
        """
        if df.empty or "datetime" not in df.columns:
            raise ValueError("Dataframe must be non-empty and contain 'datetime' column.")
            
        # Extract boundaries
        r_count = len(df)
        min_ts = df["datetime"].min().isoformat()
        max_ts = df["datetime"].max().isoformat()
        tz = str(df["datetime"].dt.tz) if hasattr(df["datetime"].dtype, "tz") else "UTC"
        
        schema = {column: str(dtype) for column, dtype in df.dtypes.items()}
        tail_close = df["close"].iloc[-1] if "close" in df.columns else None
        head_close = df["close"].iloc[0] if "close" in df.columns else None

        # Hash schema, boundaries, and stable head/tail values for stronger identity.
        shape_str = (
            f"{dataset_id}|{source}|{instrument}|{timeframe}|{r_count}|{min_ts}|{max_ts}|"
            f"{head_close}|{tail_close}|{schema}"
        ).encode("utf-8")
        checksum = hashlib.md5(shape_str).hexdigest()
        
        return cls(
            dataset_id=dataset_id,
            source=source,
            instrument=instrument,
            timeframe=timeframe,
            timezone=tz,
            row_count=r_count,
            min_timestamp=min_ts,
            max_timestamp=max_ts,
            checksum=checksum,
            creation_timestamp=datetime.now(UTC).isoformat(),
            notes=notes,
            schema=schema,
            build_recipe={"builder": "create_from_dataframe"},
        )

    @classmethod
    def create_from_parquet(
        cls,
        parquet_path: Path,
        dataset_id: str,
        source: str,
        instrument: str,
        timeframe: str,
        notes: str = "",
    ) -> "DatasetManifest":
        """Build a manifest from a parquet file and capture source file metadata."""
        parquet_path = Path(parquet_path)
        df = pd.read_parquet(parquet_path)
        manifest = cls.create_from_dataframe(
            df=df,
            dataset_id=dataset_id,
            source=source,
            instrument=instrument,
            timeframe=timeframe,
            notes=notes,
        )
        stat = parquet_path.stat()
        manifest.source_files = [
            {
                "path": str(parquet_path),
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
            }
        ]
        manifest.build_recipe = {
            "builder": "create_from_parquet",
            "path": str(parquet_path),
        }
        return manifest

    def to_dict(self) -> Dict[str, Any]:
        """Convert manifest to serializable dictionary."""
        return asdict(self)
