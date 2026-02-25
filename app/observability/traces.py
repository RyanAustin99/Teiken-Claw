"""
Distributed tracing for Teiken Claw.

This module provides distributed tracing for tracking requests
across multiple components:
- Trace ID generation
- Span management
- Trace context propagation
"""

import logging
import uuid
import builtins
from contextvars import ContextVar
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from dataclasses import dataclass, field

from app.config.settings import settings

logger = logging.getLogger(__name__)


class SpanStatus(str, Enum):
    """Span status codes."""
    OK = "ok"
    ERROR = "error"
    TIMEOUT = "timeout"


@dataclass
class Span:
    """Represents a trace span."""
    trace_id: str
    span_id: str
    parent_span_id: Optional[str]
    name: str
    start_time: datetime
    end_time: Optional[datetime] = None
    status: SpanStatus = SpanStatus.OK
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: list = field(default_factory=list)
    
    @property
    def duration_ms(self) -> Optional[float]:
        """Get span duration in milliseconds."""
        if self.end_time and self.start_time:
            return (self.end_time - self.start_time).total_seconds() * 1000
        return None
    
    def add_event(self, name: str, attributes: Optional[Dict[str, Any]] = None) -> None:
        """Add an event to the span."""
        self.events.append({
            "name": name,
            "timestamp": datetime.utcnow().isoformat(),
            "attributes": attributes or {},
        })
    
    def set_attribute(self, key: str, value: Any) -> None:
        """Set a span attribute."""
        self.attributes[key] = value
    
    def set_status(self, status: SpanStatus) -> None:
        """Set span status."""
        self.status = status
    
    def end(self) -> None:
        """End the span."""
        self.end_time = datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert span to dictionary."""
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "name": self.name,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_ms": self.duration_ms,
            "status": self.status.value,
            "attributes": self.attributes,
            "events": self.events,
        }


# Backward-compatible global alias used by some legacy tests/callers.
if not hasattr(builtins, "Span"):
    builtins.Span = Span


class TraceManager:
    """
    Distributed trace manager.
    
    Provides trace and span management for tracking requests
    across multiple components.
    """
    
    # Context variable for current trace
    _current_trace_id: ContextVar[Optional[str]] = ContextVar("current_trace_id", default=None)
    _current_span: ContextVar[Optional[Span]] = ContextVar("current_span", default=None)
    
    def __init__(self, enabled: bool = True):
        """
        Initialize the trace manager.
        
        Args:
            enabled: Whether tracing is enabled
        """
        self._enabled = enabled and settings.TRACING_ENABLED
        self._spans: Dict[str, list] = {}
        self._spans_lock = None
        
        # Import threading only if needed
        import threading
        self._spans_lock = threading.Lock()
        
        logger.info(f"TraceManager initialized (enabled={self._enabled})")
    
    @property
    def is_enabled(self) -> bool:
        """Check if tracing is enabled."""
        return self._enabled
    
    @property
    def current_trace_id(self) -> Optional[str]:
        """Get current trace ID from context."""
        return self._current_trace_id.get()
    
    @property
    def current_span(self) -> Optional[Span]:
        """Get current span from context."""
        return self._current_span.get()
    
    def create_trace_id(self) -> str:
        """
        Create a new trace ID.
        
        Returns:
            UUID string for the trace
        """
        return str(uuid.uuid4())
    
    def create_span_id(self) -> str:
        """
        Create a new span ID.
        
        Returns:
            UUID string for the span
        """
        return str(uuid.uuid4())[:16]  # Shorter ID for spans
    
    def start_trace(self, name: str, trace_id: Optional[str] = None, parent_span_id: Optional[str] = None) -> Span:
        """
        Start a new trace.
        
        Args:
            name: Name of the trace
            trace_id: Existing trace ID or None to create new
            parent_span_id: Parent span ID for nested traces
            
        Returns:
            The root span for the trace
        """
        if not self._enabled:
            return None
        
        trace_id = trace_id or self.create_trace_id()
        span_id = self.create_span_id()
        
        span = Span(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            name=name,
            start_time=datetime.utcnow(),
        )
        
        # Store span
        with self._spans_lock:
            if trace_id not in self._spans:
                self._spans[trace_id] = []
            self._spans[trace_id].append(span)
        
        # Set as current
        self._current_trace_id.set(trace_id)
        self._current_span.set(span)
        
        return span
    
    def start_span(
        self,
        span_name: str,
        trace_id: Optional[str] = None,
        parent_span_id: Optional[str] = None,
    ) -> Optional[Span]:
        """
        Start a new span within a trace.
        
        Args:
            span_name: Name of the span
            trace_id: Trace ID to use (uses current if not provided)
            parent_span_id: Parent span ID (uses current if not provided)
            
        Returns:
            The new span or None if tracing is disabled
        """
        if not self._enabled:
            return None
        
        trace_id = trace_id or self.current_trace_id
        if not trace_id:
            # Start a new trace if none exists
            root_span = self.start_trace(span_name)
            return root_span
        
        parent_span_id = parent_span_id or (self.current_span.span_id if self.current_span else None)
        span_id = self.create_span_id()
        
        span = Span(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            name=span_name,
            start_time=datetime.utcnow(),
        )
        
        # Store span
        with self._spans_lock:
            if trace_id not in self._spans:
                self._spans[trace_id] = []
            self._spans[trace_id].append(span)
        
        # Set as current
        self._current_span.set(span)
        
        return span
    
    def end_span(self, span: Optional[Span]) -> None:
        """
        End a span.
        
        Args:
            span: The span to end
        """
        if not span:
            return
        
        span.end()
        
        # Clear current if this is the current span
        if self.current_span == span:
            self._current_span.set(None)
    
    def end_trace(self, trace_id: Optional[str] = None) -> list[Dict[str, Any]]:
        """
        End a trace and return all spans.
        
        Args:
            trace_id: Trace ID to end (uses current if not provided)
            
        Returns:
            List of span dictionaries
        """
        trace_id = trace_id or self.current_trace_id
        if not trace_id:
            return []
        
        # End current span if any
        if self.current_span:
            self.end_span(self.current_span)
        
        # Clear context
        self._current_trace_id.set(None)
        self._current_span.set(None)
        
        # Get spans
        with self._spans_lock:
            spans = self._spans.get(trace_id, [])
            result = [s.to_dict() for s in spans]
            
            # Clean up
            if trace_id in self._spans:
                del self._spans[trace_id]
        
        return result
    
    def get_trace(self, trace_id: str) -> list[Dict[str, Any]]:
        """
        Get all spans for a trace.
        
        Args:
            trace_id: The trace ID
            
        Returns:
            List of span dictionaries
        """
        with self._spans_lock:
            spans = self._spans.get(trace_id, [])
            return [s.to_dict() for s in spans]
    
    def get_current_trace(self) -> Optional[str]:
        """
        Get the current trace ID.
        
        Returns:
            Current trace ID or None
        """
        return self.current_trace_id
    
    def inject_trace_context(self) -> Dict[str, str]:
        """
        Inject trace context into carrier for propagation.
        
        Returns:
            Dictionary with trace context headers
        """
        trace_id = self.current_trace_id
        span = self.current_span
        
        if not trace_id:
            return {}
        
        context = {
            "trace_id": trace_id,
        }
        
        if span:
            context["span_id"] = span.span_id
        
        return context
    
    def extract_trace_context(self, carrier: Dict[str, str]) -> Optional[str]:
        """
        Extract trace context from carrier.
        
        Args:
            carrier: Dictionary with trace context headers
            
        Returns:
            Extracted trace ID or None
        """
        trace_id = carrier.get("trace_id")
        
        if trace_id and self._enabled:
            self._current_trace_id.set(trace_id)
        
        return trace_id


# Global trace manager instance
_trace_manager: Optional[TraceManager] = None


def get_trace_manager() -> TraceManager:
    """Get the global trace manager instance."""
    global _trace_manager
    if _trace_manager is None:
        _trace_manager = TraceManager()
    return _trace_manager


def set_trace_manager(manager: TraceManager) -> None:
    """Set the global trace manager instance."""
    global _trace_manager
    _trace_manager = manager


# Context manager for spans
class tracecontext:
    """Context manager for trace spans."""
    
    def __init__(self, name: str, trace_id: Optional[str] = None):
        self.name = name
        self.trace_id = trace_id
        self.span: Optional[Span] = None
    
    def __enter__(self):
        manager = get_trace_manager()
        self.span = manager.start_span(self.name, self.trace_id)
        return self.span
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.span:
            if exc_type:
                self.span.set_status(SpanStatus.ERROR)
                self.span.set_attribute("error", str(exc_val))
            manager = get_trace_manager()
            manager.end_span(self.span)


__all__ = [
    "TraceManager",
    "Span",
    "SpanStatus",
    "get_trace_manager",
    "set_trace_manager",
    "tracecontext",
]
