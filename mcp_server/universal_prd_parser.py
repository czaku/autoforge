"""
Universal PRD Parser
====================

Converts PRD JSON files in various formats to AutoForge features.

Supported Formats:
1. Standard AutoForge: { "features": [ { "category", "name", "description", "steps" } ] }
2. Structured PRD: { "features": [ { "id", "name", "description", "acceptanceCriteria"/"tasks"/"stories", "part", "dependencies" } ] }

Example Structured PRD:
{
  "features": [
    {
      "id": "feature-001",
      "name": "Add User Authentication",
      "description": "Implement user login...",
      "acceptanceCriteria": [
        "User can log in with email",
        "User can log in with OAuth"
      ],
      "part": 1,
      "dependencies": []
    }
  ]
}
"""

import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict


@dataclass
class StructuredFeature:
    """Represents a feature from a structured PRD format."""
    id: str
    name: str
    description: str
    part: int
    acceptance_criteria: List[str]
    dependencies: List[str]
    category: str = ""
    
    def to_autoforge_feature(self) -> Dict[str, Any]:
        """Convert to AutoForge feature format."""
        return {
            "category": self.category or f"Part {self.part}",
            "name": f"#{self.id}: {self.name}" if self.id else self.name,
            "description": self.description,
            "steps": self.acceptance_criteria,
            "external_id": self.id,
            "part": self.part,
            "dependencies": self.dependencies
        }


class UniversalPRDParser:
    """Parser for PRD JSON files in various formats."""
    
    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
    
    def parse_prd_file(self, prd_path: Path) -> List[StructuredFeature]:
        """Parse a single PRD JSON file."""
        with open(prd_path) as f:
            data = json.load(f)
        
        features = []
        prd_features = data.get('features', [])
        
        for feature_data in prd_features:
            # Extract acceptance criteria (could be 'acceptanceCriteria', 'tasks', or 'stories')
            criteria = feature_data.get('acceptanceCriteria', [])
            if not criteria:
                criteria = feature_data.get('tasks', [])
            if not criteria:
                criteria = feature_data.get('stories', [])
            
            # Ensure criteria is a list of strings
            if criteria and isinstance(criteria[0], dict):
                # Handle case where criteria is array of objects
                criteria = [c.get('description', str(c)) for c in criteria]
            
            feature = StructuredFeature(
                id=feature_data.get('id', ''),
                name=feature_data.get('name', 'Unnamed Feature'),
                description=feature_data.get('description', ''),
                part=feature_data.get('part', 0),
                acceptance_criteria=criteria,
                dependencies=feature_data.get('dependencies', []),
                category=feature_data.get('category', '')
            )
            features.append(feature)
        
        return features
    
    def parse_all_prds(self, prd_dir: Path) -> List[FitKindFeature]:
        """Parse all PRD JSON files in a directory."""
        all_features = []
        
        if not prd_dir.exists():
            return all_features
        
        for prd_file in prd_dir.rglob("*.json"):
            try:
                features = self.parse_prd_file(prd_file)
                all_features.extend(features)
                print(f"Parsed {len(features)} features from {prd_file}")
            except Exception as e:
                print(f"Error parsing {prd_file}: {e}")
        
        return all_features
    
    def create_autoforge_features(
        self, 
        prd_dir: Path,
        part_filter: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Convert structured PRDs to AutoForge features.
        
        Args:
            prd_dir: Directory containing PRD JSON files
            part_filter: If set, only include features from this part
            
        Returns:
            List of AutoForge feature dictionaries
        """
        structured_features = self.parse_all_prds(prd_dir)
        
        autoforge_features = []
        for feature in structured_features:
            # Apply part filter if specified
            if part_filter is not None and feature.part != part_filter:
                continue
            
            autoforge_features.append(feature.to_autoforge_feature())
        
        return autoforge_features
    
    def import_to_database(
        self,
        prd_dir: Path,
        create_features_func,
        add_dependency_func,
        part_filter: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Import FitKind PRDs into AutoForge database.
        
        Args:
            prd_dir: Directory containing PRD JSON files
            create_features_func: Function to create features in database
            add_dependency_func: Function to add dependencies
            part_filter: Optional part number to filter by
            
        Returns:
            Summary of import
        """
        features = self.create_autoforge_features(prd_dir, part_filter)
        
        if not features:
            return {
                "success": False,
                "error": "No features found in PRD files",
                "features_created": 0
            }
        
        # Create features in database
        result = create_features_func(features)
        
        # Build external_id to internal_id mapping for dependencies
        # This would need to be implemented based on the database schema
        
        return {
            "success": True,
            "features_created": len(features),
            "parts": list(set(f.get('part', 0) for f in features)),
            "features": [f['name'] for f in features[:5]]  # First 5 for summary
        }


def parse_structured_prd(prd_path: str) -> List[Dict[str, Any]]:
    """
    Convenience function to parse a structured PRD file.
    
    Returns list of AutoForge-compatible feature dictionaries.
    """
    parser = UniversalPRDParser(Path.cwd())
    features = parser.parse_prd_file(Path(prd_path))
    return [f.to_autoforge_feature() for f in features]


def parse_structured_prds_directory(prd_dir: str) -> List[Dict[str, Any]]:
    """
    Convenience function to parse all structured PRDs in a directory.
    
    Returns list of AutoForge-compatible feature dictionaries.
    """
    parser = UniversalPRDParser(Path.cwd())
    features = parser.parse_all_prds(Path(prd_dir))
    return [f.to_autoforge_feature() for f in features]
