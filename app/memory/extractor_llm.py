"""
LLM-based memory extraction for Teiken Claw.

This module provides intelligent memory extraction using Ollama LLM to
analyze conversation content and extract structured memory records.

Key Features:
    - Structured memory extraction with JSON schema
    - Confidence threshold enforcement
    - Category allowlist validation
    - Size limits and sensitivity detection
    - Server-side validation
"""

import json
import logging
import hashlib
from datetime import datetime
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from pydantic import BaseModel, Field, field_validator

from app.config.settings import settings
from app.agent.ollama_client import OllamaClient, get_ollama_client

logger = logging.getLogger(__name__)


# Valid memory types (category allowlist)
VALID_MEMORY_TYPES = frozenset([
    "preference",
    "project", 
    "workflow",
    "environment",
    "schedule_pattern",
    "fact",
    "note",
])

# Valid scope values
VALID_SCOPES = frozenset([
    "global",
    "project",
    "thread",
    "user",
])

# Default confidence threshold
DEFAULT_CONFIDENCE_THRESHOLD = 0.7

# Maximum content size for extraction (in characters)
MAX_CONTENT_SIZE = 10000

# Extraction prompt template
EXTRACTION_PROMPT = """You are a memory extraction system. Analyze the following content and extract structured memory records.

Content to analyze:
{content}

{context_section}

Extract any important information that should be remembered. For each piece of information, provide:
1. memory_type: One of {memory_types}
2. content: The actual memory content (concise and clear)
3. tags: Relevant tags for categorization
4. confidence: Your confidence level (0.0 to 1.0)
5. scope: One of {scopes}
6. ttl_days: Time-to-live in days if this is temporary information (null for permanent)
7. sensitive: Whether this contains sensitive information
8. justification: Why this memory should be stored

Respond ONLY with a valid JSON object containing an "extractions" array. Each item in the array should be a memory record.

Example response format:
{{
  "extractions": [
    {{
      "memory_type": "preference",
      "content": "User prefers dark mode for code editors",
      "tags": ["preference", "ui", "editor"],
      "confidence": 0.95,
      "scope": "user",
      "ttl_days": null,
      "sensitive": false,
      "justification": "Clear user preference stated that should be remembered for future interactions"
    }}
  ]
}}

If no important information should be remembered, return:
{{
  "extractions": []
}}

Remember: Only extract information that is genuinely useful to remember. Quality over quantity."""


class ExtractedMemory(BaseModel):
    """Schema for a single extracted memory."""
    
    memory_type: str = Field(..., description="Type of memory")
    content: str = Field(..., description="The memory content")
    tags: List[str] = Field(default_factory=list, description="Tags for categorization")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence level")
    scope: str = Field(default="user", description="Memory scope")
    ttl_days: Optional[int] = Field(default=None, ge=1, le=365, description="Time-to-live in days")
    sensitive: bool = Field(default=False, description="Whether content is sensitive")
    justification: str = Field(default="", description="Why this was extracted")
    
    @field_validator("memory_type")
    @classmethod
    def validate_memory_type(cls, v: str) -> str:
        """Validate memory type is in allowlist."""
        if v not in VALID_MEMORY_TYPES:
            raise ValueError(f"Invalid memory type: {v}. Must be one of {VALID_MEMORY_TYPES}")
        return v
    
    @field_validator("scope")
    @classmethod
    def validate_scope(cls, v: str) -> str:
        """Validate scope is valid."""
        if v not in VALID_SCOPES:
            raise ValueError(f"Invalid scope: {v}. Must be one of {VALID_SCOPES}")
        return v


class ExtractionResult(BaseModel):
    """Schema for extraction result."""
    
    extractions: List[ExtractedMemory] = Field(default_factory=list)
    raw_response: Optional[str] = None
    extraction_time: datetime = Field(default_factory=datetime.utcnow)
    model_used: str = ""
    tokens_used: int = 0


@dataclass
class ExtractionConfig:
    """Configuration for memory extraction."""
    
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD
    max_content_size: int = MAX_CONTENT_SIZE
    enabled: bool = True
    model: str = ""
    
    def __post_init__(self):
        if not self.model:
            self.model = getattr(settings, "OLLAMA_CHAT_MODEL", "llama3.2")


class LLMMemoryExtractor:
    """
    LLM-based memory extractor.
    
    Uses Ollama to extract structured memory records from conversation content.
    Implements server-side validation and confidence threshold enforcement.
    
    Attributes:
        config: Extraction configuration
        ollama_client: Ollama API client
        _enabled: Whether extraction is enabled
    """
    
    def __init__(
        self,
        ollama_client: Optional[OllamaClient] = None,
        config: Optional[ExtractionConfig] = None,
    ):
        """
        Initialize the LLM memory extractor.
        
        Args:
            ollama_client: Ollama client (uses global if None)
            config: Extraction configuration (uses defaults if None)
        """
        self._ollama_client = ollama_client or get_ollama_client()
        self._config = config or ExtractionConfig()
        self._enabled = self._config.enabled
        
        logger.info(
            f"LLMMemoryExtractor initialized: enabled={self._enabled}, "
            f"model={self._config.model}, threshold={self._config.confidence_threshold}"
        )
    
    @property
    def is_enabled(self) -> bool:
        """Check if LLM extraction is enabled."""
        return self._enabled
    
    def enable(self) -> None:
        """Enable LLM extraction."""
        self._enabled = True
        logger.info("LLM extraction enabled")
    
    def disable(self) -> None:
        """Disable LLM extraction."""
        self._enabled = False
        logger.info("LLM extraction disabled")
    
    def extract_memory(
        self,
        content: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Extract structured memory from content using LLM.
        
        Args:
            content: The content to analyze
            context: Optional context for extraction (e.g., conversation history)
            
        Returns:
            Dictionary with extraction results:
                - memory_type: Type of memory
                - content: The memory content
                - tags: List of tags
                - confidence: Confidence score
                - scope: Memory scope
                - ttl_days: Time-to-live if applicable
                - sensitive: Whether content is sensitive
                - justification: Why this was extracted
                - extraction_time: When extraction occurred
                - model_used: Model used for extraction
        """
        if not self._enabled:
            return self._empty_result("LLM extraction disabled")
        
        # Validate content size
        if len(content) > self._config.max_content_size:
            logger.warning(
                f"Content size {len(content)} exceeds max {self._config.max_content_size}, truncating"
            )
            content = content[:self._config.max_content_size]
        
        if not content.strip():
            return self._empty_result("Empty content")
        
        try:
            # Build the extraction prompt
            prompt = self._build_prompt(content, context)
            
            # Call Ollama for extraction
            response = self._call_ollama(prompt)
            
            if not response:
                return self._empty_result("No response from LLM")
            
            # Parse and validate the response
            result = self._parse_response(response)
            
            # Apply server-side validation
            validated = self._validate_extraction(result)
            
            if validated:
                return {
                    "memory_type": validated.memory_type,
                    "content": validated.content,
                    "tags": validated.tags,
                    "confidence": validated.confidence,
                    "scope": validated.scope,
                    "ttl_days": validated.ttl_days,
                    "sensitive": validated.sensitive,
                    "justification": validated.justification,
                    "extraction_time": datetime.utcnow().isoformat(),
                    "model_used": self._config.model,
                }
            
            return self._empty_result("No valid extractions after validation")
            
        except Exception as e:
            logger.error(f"Memory extraction failed: {e}", exc_info=True)
            return self._empty_result(f"Extraction error: {str(e)}")
    
    def extract_multiple(
        self,
        contents: List[str],
        context: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Extract memories from multiple contents.
        
        Args:
            contents: List of content strings to analyze
            context: Optional context for extraction
            
        Returns:
            List of extraction results
        """
        results = []
        for content in contents:
            result = self.extract_memory(content, context)
            if result.get("memory_type"):  # Only include non-empty results
                results.append(result)
        return results
    
    def extract_from_conversation(
        self,
        messages: List[Dict[str, str]],
        context: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Extract memories from a conversation.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            context: Optional context for extraction
            
        Returns:
            List of extraction results
        """
        # Format conversation for extraction
        formatted = "\n".join([
            f"{msg.get('role', 'unknown')}: {msg.get('content', '')}"
            for msg in messages
        ])
        
        return self.extract_multiple([formatted], context)
    
    def _build_prompt(
        self,
        content: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Build the extraction prompt."""
        context_section = ""
        if context:
            context_items = []
            if context.get("conversation_topic"):
                context_items.append(f"Conversation topic: {context['conversation_topic']}")
            if context.get("user_intent"):
                context_items.append(f"User intent: {context['user_intent']}")
            if context.get("previous_memories"):
                context_items.append(f"Related memories: {', '.join(context['previous_memories'][:3])}")
            
            if context_items:
                context_section = "Context:\n" + "\n".join(context_items)
        
        return EXTRACTION_PROMPT.format(
            content=content,
            context_section=context_section,
            memory_types=list(VALID_MEMORY_TYPES),
            scopes=list(VALID_SCOPES),
        )
    
    def _call_ollama(self, prompt: str) -> Optional[str]:
        """Call Ollama for extraction."""
        try:
            # Use the chat endpoint for better results
            response = self._ollama_client.chat(
                messages=[{"role": "user", "content": prompt}],
                model=self._config.model,
                options={
                    "temperature": 0.3,  # Lower temperature for more consistent extraction
                    "num_predict": 1024,  # Limit response size
                },
            )
            
            if response and hasattr(response, "message"):
                return response.message.get("content", "")
            elif response and isinstance(response, dict):
                return response.get("message", {}).get("content", "")
            
            return None
            
        except Exception as e:
            logger.error(f"Ollama call failed: {e}")
            return None
    
    def _parse_response(self, response: str) -> ExtractionResult:
        """Parse LLM response into structured result."""
        try:
            # Try to extract JSON from response
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            
            if json_start == -1 or json_end == 0:
                logger.warning("No JSON found in response")
                return ExtractionResult(raw_response=response)
            
            json_str = response[json_start:json_end]
            data = json.loads(json_str)
            
            extractions = []
            for item in data.get("extractions", []):
                try:
                    memory = ExtractedMemory(**item)
                    extractions.append(memory)
                except Exception as e:
                    logger.warning(f"Failed to parse extraction item: {e}")
                    continue
            
            return ExtractionResult(
                extractions=extractions,
                raw_response=response,
                model_used=self._config.model,
            )
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON response: {e}")
            return ExtractionResult(raw_response=response)
        except Exception as e:
            logger.error(f"Response parsing error: {e}")
            return ExtractionResult(raw_response=response)
    
    def _validate_extraction(
        self,
        result: ExtractionResult,
    ) -> Optional[ExtractedMemory]:
        """
        Apply server-side validation to extraction result.
        
        Validates:
        - Confidence threshold
        - Category allowlist
        - Size limits
        - Sensitivity policy
        
        Args:
            result: The extraction result to validate
            
        Returns:
            First valid extraction, or None if none pass validation
        """
        for extraction in result.extractions:
            # Check confidence threshold
            if extraction.confidence < self._config.confidence_threshold:
                logger.debug(
                    f"Extraction below confidence threshold: {extraction.confidence} < {self._config.confidence_threshold}"
                )
                continue
            
            # Check content size
            if len(extraction.content) > MAX_CONTENT_SIZE:
                logger.debug(f"Extraction content too large: {len(extraction.content)}")
                continue
            
            # Check for empty content
            if not extraction.content.strip():
                logger.debug("Extraction has empty content")
                continue
            
            # Validate memory type (already validated by Pydantic, but double-check)
            if extraction.memory_type not in VALID_MEMORY_TYPES:
                logger.debug(f"Invalid memory type: {extraction.memory_type}")
                continue
            
            # Validate scope
            if extraction.scope not in VALID_SCOPES:
                logger.debug(f"Invalid scope: {extraction.scope}")
                continue
            
            # Apply sensitivity policy (can be extended)
            if extraction.sensitive:
                # For now, we still store sensitive memories but flag them
                # In production, you might want to apply additional handling
                logger.info(f"Sensitive memory detected: {extraction.memory_type}")
            
            return extraction
        
        return None
    
    def _empty_result(self, reason: str = "") -> Dict[str, Any]:
        """Return an empty extraction result."""
        return {
            "memory_type": "",
            "content": "",
            "tags": [],
            "confidence": 0.0,
            "scope": "user",
            "ttl_days": None,
            "sensitive": False,
            "justification": reason,
            "extraction_time": datetime.utcnow().isoformat(),
            "model_used": self._config.model,
        }
    
    def hash_content(self, content: str) -> str:
        """
        Generate a hash for content deduplication.
        
        Args:
            content: Content to hash
            
        Returns:
            SHA-256 hash of the content
        """
        return hashlib.sha256(content.encode()).hexdigest()


# Singleton instance
_extractor_instance: Optional[LLMMemoryExtractor] = None


def get_llm_extractor() -> LLMMemoryExtractor:
    """
    Get the global LLM memory extractor instance.
    
    Returns:
        LLMMemoryExtractor instance
    """
    global _extractor_instance
    if _extractor_instance is None:
        _extractor_instance = LLMMemoryExtractor()
    return _extractor_instance


def set_llm_extractor(extractor: LLMMemoryExtractor) -> None:
    """
    Set the global LLM memory extractor instance.
    
    Args:
        extractor: The extractor instance to use
    """
    global _extractor_instance
    _extractor_instance = extractor


__all__ = [
    "LLMMemoryExtractor",
    "ExtractionConfig",
    "ExtractionResult",
    "ExtractedMemory",
    "VALID_MEMORY_TYPES",
    "VALID_SCOPES",
    "DEFAULT_CONFIDENCE_THRESHOLD",
    "MAX_CONTENT_SIZE",
    "get_llm_extractor",
    "set_llm_extractor",
]
