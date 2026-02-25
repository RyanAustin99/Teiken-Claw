"""
Deterministic memory extraction rules for Teiken Claw.

This module provides:
- Content classification and filtering
- Category detection
- Sensitive content detection
- Deterministic extraction rules
- Confidence scoring
"""

import re
from typing import List, Dict, Optional, Tuple
from datetime import datetime


class MemoryExtractionRules:
    """Deterministic memory extraction rules."""
    
    def __init__(self):
        # Configuration
        self._allowed_categories = {
            "preference", "project", "workflow", "environment", 
            "schedule_pattern", "fact", "note"
        }
        self._sensitive_patterns = [
            r'password', r'secret', r'api[_-]?key', r'token', r'private',
            r'auth', r'credential', r'login', r'passphrase', r'private[_-]?key'
        ]
        self._category_patterns = {
            "preference": [
                r'I prefer', r'I like', r'I dislike', r'I hate', r'I love',
                r'best', r'favorite', r'favourite', r'worst', r'most', r'least'
            ],
            "project": [
                r'project', r'task', r'assignment', r'initiative', r'campaign',
                r'work', r'job', r'deliverable', r'goal', r'objective'
            ],
            "workflow": [
                r'process', r'workflow', r'procedure', r'routine', r'habit',
                r'step', r'stage', r'phase', r'cycle', r'method'
            ],
            "environment": [
                r'environment', r'setup', r'configuration', r'config', r'install',
                r'dev', r'development', r'prod', r'production', r'staging', r'test'
            ],
            "schedule_pattern": [
                r'every', r'always', r'usually', r'often', r'sometimes',
                r'never', r'weekly', r'monthly', r'daily', r'hourly', r'regularly'
            ],
            "fact": [
                r'is', r'are', r'was', r'were', r'will be', r'has', r'have', r'had'
            ],
            "note": [
                r'note', r'remember', r'important', r'key', r'critical', r'essential',
                r'vital', r'must', r'need', r'should', r'could', r'would'
            ]
        }
        self._reject_patterns = [
            r'^/thread\s+', r'^/mode\s+', r'^/help', r'^/start', r'^/ping',
            r'^/status', r'^/admin', r'^/pause', r'^/resume', r'^/jobs',
            r'^https?://', r'^www\.', r'^@', r'^#', r'^$', r'^\s*$'
        ]
    
    # =========================================================================
    # Classification
    # =========================================================================
    
    def classify_candidates(self, candidates: List[str]) -> List[Dict]:
        """Classify and filter candidate memories."""
        classified = []
        
        for candidate in candidates:
            # Skip empty or whitespace-only content
            if not candidate or not candidate.strip():
                continue
            
            # Check for rejection patterns
            if self._is_rejected_content(candidate):
                continue
            
            # Check for sensitive content
            if self._is_sensitive_content(candidate):
                continue
            
            # Classify category
            category = self._get_category(candidate)
            if not category:
                continue
            
            # Extract facts and preferences
            facts = self._extract_facts(candidate)
            preferences = self._extract_preferences(candidate)
            
            # Calculate confidence
            confidence = self._calculate_confidence(candidate, category)
            
            classified.append({
                "content": candidate.strip(),
                "category": category,
                "facts": facts,
                "preferences": preferences,
                "confidence": confidence,
                "timestamp": datetime.now().isoformat()
            })
        
        return classified
    
    def _is_allowed_category(self, category: str) -> bool:
        """Check if category is allowed."""
        return category in self._allowed_categories
    
    def _is_sensitive_content(self, content: str) -> bool:
        """Check if content contains sensitive information."""
        content_lower = content.lower()
        
        for pattern in self._sensitive_patterns:
            if re.search(pattern, content_lower):
                return True
        
        # Check for common sensitive patterns
        if any(keyword in content_lower for keyword in [
            'password', 'secret', 'key', 'token', 'private',
            'auth', 'credential', 'login', 'passphrase'
        ]):
            return True
        
        return False
    
    def _get_category(self, content: str) -> Optional[str]:
        """Get category for content."""
        content_lower = content.lower()
        
        # Check category patterns in priority order
        for category, patterns in self._category_patterns.items():
            for pattern in patterns:
                if re.search(pattern, content_lower):
                    return category
        
        # Default to 'note' if no specific category found
        return "note"
    
    def _extract_facts(self, content: str) -> List[str]:
        """Extract facts from content."""
        facts = []
        
        # Simple fact extraction - look for declarative statements
        # This is a placeholder for more sophisticated extraction
        
        # Split into sentences
        sentences = re.split(r'[.!?]+', content)
        
        for sentence in sentences:
            sentence = sentence.strip()
            if sentence and len(sentence) > 10:  # Minimum length for a fact
                # Check if it looks like a fact (declarative statement)
                if sentence.endswith(('is', 'are', 'was', 'were', 'has', 'have', 'had')):
                    facts.append(sentence)
                elif sentence.count(' ') > 5:  # At least 6 words
                    facts.append(sentence)
        
        return facts[:3]  # Return up to 3 facts
    
    def _extract_preferences(self, content: str) -> List[str]:
        """Extract preferences from content."""
        preferences = []
        
        # Look for preference indicators
        preference_indicators = [
            r'I prefer', r'I like', r'I dislike', r'I hate', r'I love',
            r'best', r'favorite', r'favourite', r'worst', r'most', r'least'
        ]
        
        content_lower = content.lower()
        
        for indicator in preference_indicators:
            match = re.search(indicator, content_lower)
            if match:
                # Extract the preference phrase
                start = match.end()
                # Look for end of preference (next sentence or end)
                end_match = re.search(r'[.!?]', content_lower[start:])
                if end_match:
                    end = start + end_match.start()
                else:
                    end = len(content)
                
                preference = content[match.start():end].strip()
                if preference:
                    preferences.append(preference)
        
        return preferences[:2]  # Return up to 2 preferences
    
    # =========================================================================
    # Filtering
    # =========================================================================
    
    def _is_rejected_content(self, content: str) -> bool:
        """Check if content should be rejected."""
        content_lower = content.lower()
        
        # Check reject patterns
        for pattern in self._reject_patterns:
            if re.match(pattern, content_lower):
                return True
        
        # Check for very short content
        if len(content.strip()) < 10:
            return True
        
        # Check for too many special characters
        special_char_ratio = sum(1 for c in content if not c.isalnum()) / len(content)
        if special_char_ratio > 0.5:
            return True
        
        return False
    
    def _calculate_confidence(self, content: str, category: str) -> float:
        """Calculate confidence score for content."""
        confidence = 0.5  # Base confidence
        
        # Boost confidence for clear category matches
        if category in ['preference', 'project', 'workflow']:
            confidence += 0.2
        
        # Boost for longer, more detailed content
        if len(content) > 50:
            confidence += 0.1
        elif len(content) > 100:
            confidence += 0.2
        
        # Reduce confidence for content with many special characters
        special_char_ratio = sum(1 for c in content if not c.isalnum()) / len(content)
        if special_char_ratio > 0.3:
            confidence -= 0.1
        
        # Reduce confidence for content that looks like commands
        if any(content.lower().startswith(cmd) for cmd in ['/thread', '/mode', '/help']):
            confidence -= 0.3
        
        return max(0.0, min(1.0, confidence))


# =============================================================================
# Global Extraction Rules Instance
# =============================================================================

_extraction_rules: Optional[MemoryExtractionRules] = None


def get_extraction_rules() -> MemoryExtractionRules:
    """Get or create the global extraction rules instance."""
    global _extraction_rules
    
    if _extraction_rules is None:
        _extraction_rules = MemoryExtractionRules()
    
    return _extraction_rules


def set_extraction_rules(rules: MemoryExtractionRules) -> None:
    """Set the global extraction rules instance (for testing or DI)."""
    global _extraction_rules
    _extraction_rules = rules