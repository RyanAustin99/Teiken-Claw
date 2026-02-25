"""
Soul configuration loader - loads soul files and mode configurations.
"""
import os
from pathlib import Path
from typing import Optional, Dict
import yaml
import logging

from app.soul.models import (
    SoulConfig,
    ModeConfig,
    GuardrailsConfig,
    GoalsConfig,
    ModeType
)

logger = logging.getLogger(__name__)


class SoulLoader:
    """Loads and manages soul configuration."""
    
    def __init__(self, base_path: Optional[str] = None):
        """
        Initialize the SoulLoader.
        
        Args:
            base_path: Base path for soul files. Defaults to project root.
        """
        if base_path is None:
            # Find project root (where soul/ directory should be)
            self.base_path = Path.cwd()
        else:
            self.base_path = Path(base_path)
        
        self._soul_config: Optional[SoulConfig] = None
        logger.info(f"SoulLoader initialized with base_path: {self.base_path}")
    
    def load_soul(self) -> SoulConfig:
        """
        Load complete soul configuration.
        
        Returns:
            Complete SoulConfig with all loaded components
        """
        logger.info("Loading complete soul configuration...")
        
        # Create base config
        self._soul_config = SoulConfig(
            name="Teiken Claw",
            version="1.0.0",
            core_file="soul/core.md",
            style_file="soul/style.md",
            goals_file="soul/goals.yaml",
            guardrails_file="soul/guardrails.yaml",
            default_mode=ModeType.DEFAULT,
            modes_directory="soul/modes"
        )
        
        # Load components
        self._soul_config.core = self.load_core()
        self._soul_config.style = self.load_style()
        self._soul_config.guardrails = self.load_guardrails()
        self._soul_config.goals = self.load_goals()
        
        # Load all modes
        self._soul_config.modes = self.load_all_modes()
        
        logger.info(f"Soul loaded successfully: {self._soul_config.name} v{self._soul_config.version}")
        return self._soul_config
    
    def load_core(self) -> str:
        """
        Load core.md identity file.
        
        Returns:
            Core identity text
        """
        core_path = self.base_path / self._soul_config.core_file if self._soul_config else self.base_path / "soul/core.md"
        
        try:
            if core_path.exists():
                content = core_path.read_text(encoding="utf-8")
                logger.debug(f"Loaded core from {core_path}")
                return content
            else:
                logger.warning(f"Core file not found: {core_path}")
                return self._get_default_core()
        except Exception as e:
            logger.error(f"Error loading core: {e}")
            return self._get_default_core()
    
    def load_style(self) -> str:
        """
        Load style.md formatting file.
        
        Returns:
            Style guide text
        """
        style_path = self.base_path / "soul/style.md"
        
        try:
            if style_path.exists():
                content = style_path.read_text(encoding="utf-8")
                logger.debug(f"Loaded style from {style_path}")
                return content
            else:
                logger.warning(f"Style file not found: {style_path}")
                return self._get_default_style()
        except Exception as e:
            logger.error(f"Error loading style: {e}")
            return self._get_default_style()
    
    def load_guardrails(self) -> GuardrailsConfig:
        """
        Load guardrails.yaml safety configuration.
        
        Returns:
            Guardrails configuration
        """
        guardrails_path = self.base_path / "soul/guardrails.yaml"
        
        try:
            if guardrails_path.exists():
                with open(guardrails_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                logger.debug(f"Loaded guardrails from {guardrails_path}")
                return GuardrailsConfig(**data)
            else:
                logger.warning(f"Guardrails file not found: {guardrails_path}")
                return GuardrailsConfig()
        except Exception as e:
            logger.error(f"Error loading guardrails: {e}")
            return GuardrailsConfig()
    
    def load_goals(self) -> GoalsConfig:
        """
        Load goals.yaml operational goals.
        
        Returns:
            Goals configuration
        """
        goals_path = self.base_path / "soul/goals.yaml"
        
        try:
            if goals_path.exists():
                with open(goals_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                logger.debug(f"Loaded goals from {goals_path}")
                return GoalsConfig(**data)
            else:
                logger.warning(f"Goals file not found: {goals_path}")
                return GoalsConfig()
        except Exception as e:
            logger.error(f"Error loading goals: {e}")
            return GoalsConfig()
    
    def load_mode(self, mode_name: str) -> ModeConfig:
        """
        Load a specific mode configuration.
        
        Args:
            mode_name: Name of the mode to load
            
        Returns:
            Mode configuration
        """
        mode_path = self.base_path / "soul/modes" / f"{mode_name}.yaml"
        
        try:
            if mode_path.exists():
                with open(mode_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                logger.debug(f"Loaded mode '{mode_name}' from {mode_path}")
                return ModeConfig(**data)
            else:
                logger.warning(f"Mode file not found: {mode_path}, using default")
                return self._get_default_mode_config(mode_name)
        except Exception as e:
            logger.error(f"Error loading mode '{mode_name}': {e}")
            return self._get_default_mode_config(mode_name)
    
    def load_all_modes(self) -> Dict[str, ModeConfig]:
        """
        Load all available mode configurations.
        
        Returns:
            Dictionary of mode name to ModeConfig
        """
        modes_dir = self.base_path / "soul/modes"
        modes: Dict[str, ModeConfig] = {}
        
        try:
            if modes_dir.exists():
                for mode_file in modes_dir.glob("*.yaml"):
                    mode_name = mode_file.stem
                    modes[mode_name] = self.load_mode(mode_name)
                    logger.debug(f"Loaded mode: {mode_name}")
            else:
                logger.warning(f"Modes directory not found: {modes_dir}")
        except Exception as e:
            logger.error(f"Error loading modes: {e}")
        
        # Ensure default mode exists
        if "default" not in modes:
            modes["default"] = self._get_default_mode_config("default")
        
        return modes
    
    def get_config(self) -> Optional[SoulConfig]:
        """Get the loaded soul configuration."""
        return self._soul_config
    
    @staticmethod
    def _get_default_core() -> str:
        """Get default core identity if file not found."""
        return """# Teiken Claw - Identity

## Core Identity
You are Teiken Claw, an elite software architect and AI assistant designed for technical excellence.

## Core Values
- Precision and accuracy in all operations
- Security-first approach to development
- Clean, maintainable code patterns
- Continuous learning and adaptation

## Operational Philosophy
You operate with methodical precision, breaking complex tasks into smaller, manageable components. You prioritize correctness, security, and maintainability in all outputs.

## Expertise Areas
- Full-stack software architecture
- Python, JavaScript, TypeScript, C++ development
- Cloud infrastructure (AWS, Azure, GCP)
- Database design and optimization
- Security best practices
"""
    
    @staticmethod
    def _get_default_style() -> str:
        """Get default style guide if file not found."""
        return """# Teiken Claw - Style Guide

## Response Format
- Use clear, professional language
- Provide structured responses with headers
- Include code blocks with language annotations
- Use bullet points for lists
- Be concise but complete

## Technical Formatting
- Use markdown for all formatting
- Include file paths as clickable links when possible
- Show line numbers for code references
- Use fenced code blocks with syntax highlighting

## Communication Style
- Professional and direct
- Explain "what" and "why", not just "how"
- Provide context for decisions
- Acknowledge limitations and uncertainties
"""
    
    @staticmethod
    def _get_default_mode_config(mode_name: str) -> ModeConfig:
        """Get default mode configuration."""
        return ModeConfig(
            name=mode_name,
            description=f"Default {mode_name} mode configuration",
            verbosity="normal",
            output_format="markdown",
            tool_proactiveness="balanced",
            response_style="professional",
            include_reasoning=True,
            include_alternatives=False,
            max_iterations=10,
            timeout_seconds=300
        )


# Global singleton instance
_soul_loader: Optional[SoulLoader] = None


def get_soul_loader() -> SoulLoader:
    """Get the global soul loader instance."""
    global _soul_loader
    if _soul_loader is None:
        _soul_loader = SoulLoader()
    return _soul_loader


def load_soul() -> SoulConfig:
    """Load the soul configuration using the global loader."""
    return get_soul_loader().load_soul()
