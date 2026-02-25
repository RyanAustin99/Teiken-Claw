"""Skill definitions loader for Teiken Claw.

This module provides the SkillLoader class for loading and managing
skill definitions from YAML files.
"""

import logging
from pathlib import Path
from typing import Any, Optional

import yaml

from app.skills.schema import SkillDefinition, validate_skill_definition, validate_step_type

logger = logging.getLogger(__name__)


class SkillLoader:
    """Loads and manages skill definitions from YAML files."""
    
    def __init__(self, skills_dir: Optional[Path] = None):
        """Initialize the skill loader.
        
        Args:
            skills_dir: Directory containing skill YAML files. 
                        Defaults to app/skills/definitions/
        """
        if skills_dir is None:
            # Default to app/skills/definitions/
            base_dir = Path(__file__).parent
            skills_dir = base_dir / "definitions"
        
        self.skills_dir = Path(skills_dir)
        self._skills: dict[str, SkillDefinition] = {}
        self._loaded = False
        
        logger.info(f"SkillLoader initialized with directory: {self.skills_dir}")
    
    @property
    def skills_dir(self) -> Path:
        """Get the skills directory path."""
        return self._skills_dir
    
    @skills_dir.setter
    def skills_dir(self, value: Path) -> None:
        """Set the skills directory and clear cached skills."""
        self._skills_dir = value
        self._loaded = False
        self._skills.clear()
    
    def get_skill_path(self, name: str) -> Path:
        """Get the file path for a skill by name.
        
        Args:
            name: Name of the skill
            
        Returns:
            Path to the skill YAML file
        """
        return self.skills_dir / f"{name}.yaml"
    
    def load_skill(self, name: str) -> Optional[SkillDefinition]:
        """Load a single skill definition by name.
        
        Args:
            name: Name of the skill to load
            
        Returns:
            SkillDefinition if found, None otherwise
        """
        skill_path = self.get_skill_path(name)
        
        if not skill_path.exists():
            logger.warning(f"Skill file not found: {skill_path}")
            return None
        
        try:
            with open(skill_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            
            if data is None:
                logger.error(f"Empty skill file: {skill_path}")
                return None
            
            skill = validate_skill_definition(data)
            
            # Validate each step has required fields
            for step in skill.steps:
                validate_step_type(step)
            
            logger.info(f"Loaded skill: {skill.name} (version {skill.version})")
            return skill
            
        except yaml.YAMLError as e:
            logger.error(f"YAML parse error in {skill_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error loading skill {name}: {e}")
            return None
    
    def load_all_skills(self) -> dict[str, SkillDefinition]:
        """Load all skill definitions from the skills directory.
        
        Returns:
            Dictionary mapping skill names to their definitions
        """
        if self._loaded and self._skills:
            return self._skills
        
        self._skills.clear()
        
        if not self.skills_dir.exists():
            logger.warning(f"Skills directory does not exist: {self.skills_dir}")
            return self._skills
        
        # Find all YAML files
        yaml_files = list(self.skills_dir.glob("*.yaml")) + list(self.skills_dir.glob("*.yml"))
        
        logger.info(f"Found {len(yaml_files)} potential skill files")
        
        for yaml_file in yaml_files:
            # Extract skill name from filename
            name = yaml_file.stem
            
            # Skip files starting with underscore (private/partials)
            if name.startswith('_'):
                continue
            
            skill = self.load_skill(name)
            if skill:
                self._skills[skill.name] = skill
        
        self._loaded = True
        logger.info(f"Loaded {len(self._skills)} skills")
        
        return self._skills
    
    def validate_skill(self, skill: SkillDefinition) -> bool:
        """Validate a skill definition for correctness.
        
        Args:
            skill: The skill definition to validate
            
        Returns:
            True if valid
            
        Raises:
            ValueError: If validation fails
        """
        # Validate skill name
        if not skill.name:
            raise ValueError("Skill name cannot be empty")
        
        # Validate steps exist
        if not skill.steps:
            raise ValueError(f"Skill '{skill.name}' has no steps")
        
        # Validate step references (on_success/on_failure point to existing steps)
        step_ids = {step.id for step in skill.steps}
        
        for step in skill.steps:
            if step.on_success and step.on_success not in step_ids:
                raise ValueError(
                    f"Step '{step.id}' references non-existent step '{step.on_success}'"
                )
            if step.on_failure and step.on_failure not in step_ids:
                raise ValueError(
                    f"Step '{step.id}' references non-existent step '{step.on_failure}'"
                )
        
        # Validate each step has required fields
        for step in skill.steps:
            validate_step_type(step)
        
        # Validate inputs have unique names
        input_names = [inp.name for inp in skill.inputs]
        if len(input_names) != len(set(input_names)):
            raise ValueError(f"Skill '{skill.name}' has duplicate input names")
        
        # Validate outputs have unique names
        output_names = [out.name for out in skill.outputs]
        if len(output_names) != len(set(output_names)):
            raise ValueError(f"Skill '{skill.name}' has duplicate output names")
        
        logger.info(f"Skill '{skill.name}' validation passed")
        return True
    
    def get_skill(self, name: str) -> Optional[SkillDefinition]:
        """Get a loaded skill by name.
        
        Args:
            name: Name of the skill
            
        Returns:
            SkillDefinition if loaded, None otherwise
        """
        # Ensure skills are loaded
        if not self._loaded:
            self.load_all_skills()
        
        return self._skills.get(name)
    
    def list_skills(self) -> list[str]:
        """Get a list of all loaded skill names.
        
        Returns:
            List of skill names
        """
        if not self._loaded:
            self.load_all_skills()
        
        return list(self._skills.keys())
    
    def get_skills_by_category(self, category: str) -> list[SkillDefinition]:
        """Get all skills in a specific category.
        
        Args:
            category: Category to filter by
            
        Returns:
            List of matching skills
        """
        if not self._loaded:
            self.load_all_skills()
        
        return [
            skill for skill in self._skills.values()
            if skill.category == category
        ]
    
    def search_skills(self, query: str) -> list[SkillDefinition]:
        """Search skills by name, description, or tags.
        
        Args:
            query: Search query string
            
        Returns:
            List of matching skills
        """
        if not self._loaded:
            self.load_all_skills()
        
        query_lower = query.lower()
        results = []
        
        for skill in self._skills.values():
            # Search name
            if query_lower in skill.name.lower():
                results.append(skill)
                continue
            
            # Search description
            if query_lower in skill.description.lower():
                results.append(skill)
                continue
            
            # Search tags
            if any(query_lower in tag.lower() for tag in skill.tags):
                results.append(skill)
                continue
        
        return results
    
    def reload(self) -> dict[str, SkillDefinition]:
        """Force reload all skills from disk.
        
        Returns:
            Dictionary of reloaded skills
        """
        self._loaded = False
        self._skills.clear()
        return self.load_all_skills()
    
    def get_skill_info(self, name: str) -> Optional[dict[str, Any]]:
        """Get summary info about a skill without full loading.
        
        Args:
            name: Name of the skill
            
        Returns:
            Dictionary with skill metadata or None
        """
        skill = self.get_skill(name)
        if not skill:
            return None
        
        return {
            "name": skill.name,
            "version": skill.version,
            "description": skill.description,
            "category": skill.category,
            "tags": skill.tags,
            "triggers": [t.keywords for t in skill.triggers],
            "inputs": [
                {
                    "name": inp.name,
                    "type": inp.type,
                    "required": inp.required,
                    "description": inp.description
                }
                for inp in skill.inputs
            ],
            "outputs": [
                {
                    "name": out.name,
                    "type": out.type,
                    "description": out.description
                }
                for out in skill.outputs
            ],
            "step_count": len(skill.steps),
            "author": skill.author,
        }


# Singleton instance for global access
_default_loader: Optional[SkillLoader] = None


def get_skill_loader() -> SkillLoader:
    """Get the default global skill loader instance.
    
    Returns:
        The global SkillLoader instance
    """
    global _default_loader
    if _default_loader is None:
        _default_loader = SkillLoader()
    return _default_loader


def load_skill(name: str) -> Optional[SkillDefinition]:
    """Convenience function to load a single skill.
    
    Args:
        name: Name of the skill to load
        
    Returns:
        SkillDefinition if found
    """
    return get_skill_loader().load_skill(name)


def load_all_skills() -> dict[str, SkillDefinition]:
    """Convenience function to load all skills.
    
    Returns:
        Dictionary of all loaded skills
    """
    return get_skill_loader().load_all_skills()


__all__ = [
    'SkillLoader',
    'get_skill_loader',
    'load_skill',
    'load_all_skills',
]
