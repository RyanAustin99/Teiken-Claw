"""Skill routing for Teiken Claw.

This module provides the SkillRouter class for detecting skill triggers
and routing user intents to appropriate skills.
"""

import logging
import re
from typing import Any, Optional
from dataclasses import dataclass

from app.skills.loader import SkillLoader, get_skill_loader
from app.skills.schema import SkillDefinition, SkillTrigger

logger = logging.getLogger(__name__)


@dataclass
class SkillMatch:
    """Represents a matched skill trigger."""
    skill_name: str
    trigger: SkillTrigger
    confidence: float  # 0.0 to 1.0
    extracted_params: dict[str, Any]
    matched_keyword: str


class SkillRouter:
    """Routes user messages to appropriate skills."""
    
    def __init__(self, loader: Optional[SkillLoader] = None):
        """Initialize the skill router.
        
        Args:
            loader: SkillLoader instance to use. Defaults to global loader.
        """
        self.loader = loader or get_skill_loader()
        self._trigger_cache: dict[str, list[SkillMatch]] = {}
        
        logger.info("SkillRouter initialized")
    
    def route_intent(self, user_message: str) -> Optional[tuple[str, dict[str, Any]]]:
        """Route a user message to a skill if triggered.
        
        Args:
            user_message: The user's message
            
        Returns:
            Tuple of (skill_name, extracted_params) if triggered, None otherwise
        """
        message = user_message.strip()
        
        # Check for direct invocation: /skill <name> ...
        direct_match = self._check_direct_invocation(message)
        if direct_match:
            logger.info(f"Direct skill invocation: {direct_match[0]}")
            return direct_match
        
        # Check for keyword triggers
        match = self._match_trigger(message)
        if match:
            logger.info(f"Skill triggered: {match.skill_name} (confidence: {match.confidence})")
            return (match.skill_name, match.extracted_params)
        
        return None
    
    def _check_direct_invocation(self, message: str) -> Optional[tuple[str, dict[str, Any]]]:
        """Check for direct skill invocation syntax.
        
        Supports formats:
        - /skill <name> <params>
        - /run <name> <params>
        - skill:<name> <params>
        
        Args:
            message: The user's message
            
        Returns:
            Tuple of (skill_name, params) if direct invocation detected
        """
        # Pattern: /skill <name> [params...]
        direct_pattern = r'^(?:/skill|/run|skill:)\s+(\w+)(?:\s+(.+))?$'
        match = re.match(direct_pattern, message, re.IGNORECASE)
        
        if match:
            skill_name = match.group(1).lower()
            params_str = match.group(2) or ""
            
            # Parse simple key=value pairs from params
            params = self._parse_params_string(params_str)
            
            return (skill_name, params)
        
        return None
    
    def _parse_params_string(self, params_str: str) -> dict[str, Any]:
        """Parse parameter string into dictionary.
        
        Supports formats:
        - key1=value1 key2=value2
        - "quoted value" key=value
        
        Args:
            params_str: Parameter string
            
        Returns:
            Dictionary of parsed parameters
        """
        if not params_str.strip():
            return {}
        
        params = {}
        
        # Match key=value patterns
        pattern = r'(\w+)=("[^"]+"|\S+)'
        matches = re.findall(pattern, params_str)
        
        for key, value in matches:
            # Remove quotes from values
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            params[key] = value
        
        return params
    
    def _match_trigger(self, message: str) -> Optional[SkillMatch]:
        """Match message against skill triggers.
        
        Args:
            message: The user's message
            
        Returns:
            SkillMatch if a trigger matches, None otherwise
        """
        message_lower = message.lower()
        
        # Load all skills and check their triggers
        skills = self.loader.load_all_skills()
        
        best_match: Optional[SkillMatch] = None
        
        for skill in skills.values():
            for trigger in skill.triggers:
                # Check keyword matches
                for keyword in trigger.keywords:
                    keyword_lower = keyword.lower()
                    
                    # Exact match
                    if keyword_lower == message_lower:
                        match = SkillMatch(
                            skill_name=skill.name,
                            trigger=trigger,
                            confidence=1.0,
                            extracted_params={},
                            matched_keyword=keyword
                        )
                        if best_match is None or match.confidence > best_match.confidence:
                            best_match = match
                    
                    # Word boundary match
                    elif re.search(r'\b' + re.escape(keyword_lower) + r'\b', message_lower):
                        match = SkillMatch(
                            skill_name=skill.name,
                            trigger=trigger,
                            confidence=0.9,
                            extracted_params={},
                            matched_keyword=keyword
                        )
                        if best_match is None or match.confidence > best_match.confidence:
                            best_match = match
                    
                    # Contains match
                    elif keyword_lower in message_lower:
                        match = SkillMatch(
                            skill_name=skill.name,
                            trigger=trigger,
                            confidence=0.7,
                            extracted_params={},
                            matched_keyword=keyword
                        )
                        if best_match is None or match.confidence > best_match.confidence:
                            best_match = match
                
                # Check regex pattern match
                if trigger.pattern:
                    pattern_match = re.search(trigger.pattern, message, re.IGNORECASE)
                    if pattern_match:
                        extracted = pattern_match.groupdict() if pattern_match.groups() else {}
                        match = SkillMatch(
                            skill_name=skill.name,
                            trigger=trigger,
                            confidence=0.95,
                            extracted_params=extracted,
                            matched_keyword=trigger.pattern
                        )
                        if best_match is None or match.confidence > best_match.confidence:
                            best_match = match
        
        return best_match
    
    def match_trigger(
        self, 
        triggers: list[SkillTrigger], 
        message: str
    ) -> Optional[dict[str, Any]]:
        """Match a message against specific triggers.
        
        Args:
            triggers: List of triggers to match against
            message: The user's message
            
        Returns:
            Dictionary of extracted parameters if matched, None otherwise
        """
        message_lower = message.lower()
        
        for trigger in triggers:
            # Check keywords
            for keyword in trigger.keywords:
                keyword_lower = keyword.lower()
                
                if (keyword_lower == message_lower or
                    re.search(r'\b' + re.escape(keyword_lower) + r'\b', message_lower) or
                    keyword_lower in message_lower):
                    
                    # Extract basic parameters from message
                    params = self._extract_params_from_message(message, trigger)
                    return params
            
            # Check regex pattern
            if trigger.pattern:
                pattern_match = re.search(trigger.pattern, message, re.IGNORECASE)
                if pattern_match:
                    return pattern_match.groupdict() if pattern_match.groups() else {}
        
        return None
    
    def _extract_params_from_message(
        self, 
        message: str, 
        trigger: SkillTrigger
    ) -> dict[str, Any]:
        """Extract parameters from message based on trigger keywords.
        
        Args:
            message: The user's message
            trigger: The matched trigger
            
        Returns:
            Dictionary of extracted parameters
        """
        params = {}
        
        # Get the first matched keyword
        message_lower = message.lower()
        for keyword in trigger.keywords:
            if keyword.lower() in message_lower:
                # Everything after the keyword is potential params
                idx = message_lower.find(keyword.lower())
                after_keyword = message[idx + len(keyword):].strip()
                
                if after_keyword:
                    # Try to parse as key=value
                    params = self._parse_params_string(after_keyword)
                
                break
        
        return params
    
    def list_available_skills(self) -> list[dict[str, Any]]:
        """Get list of all available skills with trigger info.
        
        Returns:
            List of skill info dictionaries
        """
        skills = self.loader.load_all_skills()
        
        result = []
        for skill in skills.values():
            result.append({
                "name": skill.name,
                "description": skill.description,
                "triggers": [
                    {
                        "keywords": t.keywords,
                        "pattern": t.pattern,
                        "priority": t.priority
                    }
                    for t in skill.triggers
                ],
                "category": skill.category,
                "inputs": [inp.name for inp in skill.inputs],
            })
        
        return result
    
    def get_skill_by_keyword(self, keyword: str) -> Optional[SkillDefinition]:
        """Get a skill by trigger keyword.
        
        Args:
            keyword: Keyword to search for
            
        Returns:
            SkillDefinition if found, None otherwise
        """
        keyword_lower = keyword.lower()
        skills = self.loader.load_all_skills()
        
        for skill in skills.values():
            for trigger in skill.triggers:
                if keyword_lower in [k.lower() for k in trigger.keywords]:
                    return skill
        
        return None
    
    def suggest_skills(self, message: str, limit: int = 5) -> list[dict[str, Any]]:
        """Suggest skills that might be relevant to a message.
        
        Args:
            message: The user's message
            limit: Maximum number of suggestions
            
        Returns:
            List of suggested skills with relevance scores
        """
        skills = self.loader.load_all_skills()
        message_lower = message.lower()
        
        suggestions = []
        
        for skill in skills.values():
            score = 0
            
            # Check name match
            if message_lower in skill.name.lower():
                score += 10
            
            # Check description match
            if message_lower in skill.description.lower():
                score += 5
            
            # Check tag match
            for tag in skill.tags:
                if message_lower in tag.lower():
                    score += 3
            
            # Check keyword match
            for trigger in skill.triggers:
                for keyword in trigger.keywords:
                    if message_lower in keyword.lower():
                        score += 7
            
            if score > 0:
                suggestions.append({
                    "name": skill.name,
                    "description": skill.description,
                    "score": score,
                    "category": skill.category,
                })
        
        # Sort by score and limit
        suggestions.sort(key=lambda x: x["score"], reverse=True)
        return suggestions[:limit]


# Global router instance
_default_router: Optional[SkillRouter] = None


def get_skill_router() -> SkillRouter:
    """Get the default global skill router instance.
    
    Returns:
        The global SkillRouter instance
    """
    global _default_router
    if _default_router is None:
        _default_router = SkillRouter()
    return _default_router


def route_intent(message: str) -> Optional[tuple[str, dict[str, Any]]]:
    """Convenience function to route a user message.
    
    Args:
        message: The user's message
        
    Returns:
        Tuple of (skill_name, params) if routed, None otherwise
    """
    return get_skill_router().route_intent(message)


__all__ = [
    'SkillRouter',
    'SkillMatch',
    'get_skill_router',
    'route_intent',
]
