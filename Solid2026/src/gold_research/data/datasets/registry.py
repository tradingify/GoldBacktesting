"""
Dataset Registry System.

Provides IO mechanics to save and lookup DatasetManifests, linking
physical processed Parquet files with their verified metadata.
"""
import json
from pathlib import Path
from typing import List, Optional

from src.gold_research.data.datasets.manifest import DatasetManifest
from src.gold_research.core.paths import ProjectPaths
from src.gold_research.core.logging import logger
from src.gold_research.store.datasets_repo import DatasetsRepository

class DatasetRegistry:
    """
    Manages loading and saving of Dataset Manifests to disk.
    """
    
    def __init__(self, manifests_dir: Optional[Path] = None, db_path: Optional[Path] = None):
        """
        Initialize the registry.
        
        Args:
            manifests_dir: Optional override for the root manifest save directory.
        """
        if manifests_dir is None:
            self.manifests_dir = ProjectPaths.DATA / "manifests" / "dataset_versions"
        else:
            self.manifests_dir = manifests_dir
            
        self.manifests_dir.mkdir(parents=True, exist_ok=True)
        self.datasets_repo = DatasetsRepository(db_path)
            
    def register(self, manifest: DatasetManifest) -> Path:
        """
        Saves a DatasetManifest to the registry as a JSON file.
        
        Args:
            manifest: The manifest structure to save.
            
        Returns:
            The absolute path of the saved registry file.
        """
        file_path = self.manifests_dir / f"{manifest.dataset_id}.json"
        
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(manifest.to_dict(), f, indent=4)

        self.datasets_repo.upsert_dataset(manifest, file_path)
            
        logger.info(f"Registered dataset version: {manifest.dataset_id} [Checksum: {manifest.checksum}]")
        return file_path

    def get_manifest(self, dataset_id: str) -> Optional[DatasetManifest]:
        """
        Retrieves a DatasetManifest from disk by its ID.
        
        Args:
            dataset_id: The explicit versioned identity (e.g., 'gold_1h_v1').
            
        Returns:
            DatasetManifest instance if found, else None.
        """
        file_path = self.manifests_dir / f"{dataset_id}.json"
        
        if not file_path.exists():
            logger.warning(f"Manifest not found for dataset ID: {dataset_id}")
            return None
            
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return DatasetManifest(**data)
            
    def list_datasets(self) -> List[str]:
        """
        Lists all registered dataset IDs available in the system.
        """
        return [p.stem for p in self.manifests_dir.glob("*.json")]
