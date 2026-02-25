"""
Tests for observability components.

Tests:
- Health endpoints
- Metrics collection
- Audit logging
- Trace management
"""

import pytest
import time
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime

from app.observability.metrics import MetricsCollector
from app.observability.audit import AuditLogger, AuditEventType
from app.observability.traces import TraceManager, SpanStatus, tracecontext


class TestMetricsCollector:
    """Tests for MetricsCollector."""
    
    def test_initialization(self):
        """Test metrics collector initialization."""
        collector = MetricsCollector(enabled=True)
        assert collector.is_enabled is True
        assert collector.uptime_seconds >= 0
    
    def test_initialization_disabled(self):
        """Test metrics collector when disabled."""
        collector = MetricsCollector(enabled=False)
        assert collector.is_enabled is False
    
    def test_increment_counter(self):
        """Test incrementing a counter."""
        collector = MetricsCollector(enabled=True)
        collector.increment("test_counter")
        assert collector.get_counter("test_counter") == 1
    
    def test_increment_with_labels(self):
        """Test incrementing a counter with labels."""
        collector = MetricsCollector(enabled=True)
        collector.increment("test_counter", {"label1": "value1"})
        assert collector.get_counter("test_counter", {"label1": "value1"}) == 1
    
    def test_increment_multiple(self):
        """Test incrementing counter multiple times."""
        collector = MetricsCollector(enabled=True)
        collector.increment("test_counter", {"label1": "value1"}, 5)
        assert collector.get_counter("test_counter", {"label1": "value1"}) == 5
    
    def test_get_metrics(self):
        """Test getting all metrics."""
        collector = MetricsCollector(enabled=True)
        collector.increment("counter1")
        collector.increment("counter2", {"label": "value"})
        
        metrics = collector.get_metrics()
        
        assert metrics["enabled"] is True
        assert "counters" in metrics
        assert "counter1" in metrics["counters"]
        assert "counter2" in metrics["counters"]
    
    def test_get_metrics_disabled(self):
        """Test getting metrics when disabled."""
        collector = MetricsCollector(enabled=False)
        metrics = collector.get_metrics()
        
        assert metrics["enabled"] is False
    
    def test_prometheus_format(self):
        """Test Prometheus format output."""
        collector = MetricsCollector(enabled=True)
        collector.increment("test_metric", {"env": "test"}, 5)
        
        prometheus_output = collector.get_prometheus_format()
        
        assert "test_metric{env=\"test\"} 5" in prometheus_output
        assert "teiken_claw_uptime_seconds" in prometheus_output
    
    def test_convenience_methods(self):
        """Test convenience increment methods."""
        collector = MetricsCollector(enabled=True)
        
        collector.inc_jobs_queued("test_job")
        collector.inc_jobs_completed("test_job")
        collector.inc_jobs_failed("test_job")
        collector.inc_tool_calls("test_tool", True)
        collector.inc_tool_calls("test_tool", False)
        collector.inc_ollama_requests("llama3.2", True)
        collector.inc_ollama_requests("llama3.2", False)
        collector.inc_telegram_messages()
        collector.inc_scheduler_runs()
        collector.inc_subagent_runs("researcher")
        
        assert collector.get_counter("jobs_queued_total", {"job_type": "test_job"}) == 1
        assert collector.get_counter("jobs_completed_total", {"job_type": "test_job"}) == 1
        assert collector.get_counter("jobs_failed_total", {"job_type": "test_job"}) == 1
        assert collector.get_counter("tool_calls_total", {"tool_name": "test_tool", "success": "true"}) == 1
        assert collector.get_counter("tool_errors_total", {"tool_name": "test_tool"}) == 1
        assert collector.get_counter("ollama_requests_total", {"model": "llama3.2", "success": "true"}) == 1
        assert collector.get_counter("ollama_failures_total", {"model": "llama3.2"}) == 1
        assert collector.get_counter("telegram_messages_sent") == 1
        assert collector.get_counter("scheduler_runs_total") == 1
        assert collector.get_counter("subagent_runs_total", {"subagent_type": "researcher"}) == 1
    
    def test_reset(self):
        """Test resetting metrics."""
        collector = MetricsCollector(enabled=True)
        collector.increment("test_counter")
        
        assert collector.get_counter("test_counter") == 1
        
        collector.reset()
        
        assert collector.get_counter("test_counter") == 0


class TestAuditLogger:
    """Tests for AuditLogger."""
    
    def test_initialization(self):
        """Test audit logger initialization."""
        logger = AuditLogger(enabled=True)
        assert logger.is_enabled is True
    
    def test_initialization_disabled(self):
        """Test audit logger when disabled."""
        logger = AuditLogger(enabled=False)
        assert logger.is_enabled is False
    
    @patch('app.observability.audit.get_db_session')
    def test_log_event(self, mock_db_session):
        """Test logging an event."""
        mock_ctx = Mock()
        mock_ctx.__enter__ = Mock(return_value=mock_ctx)
        mock_ctx.__exit__ = Mock(return_value=False)
        mock_ctx.add = Mock()
        mock_ctx.commit = Mock()
        mock_db_session.return_value = mock_ctx
        
        logger = AuditLogger(enabled=True)
        event_id = logger.log_event(
            event_type=AuditEventType.TOOL_CALL,
            details={"test": "data"},
            component="test",
        )
        
        assert event_id is not None
        mock_ctx.add.assert_called_once()
        mock_ctx.commit.assert_called_once()
    
    @patch('app.observability.audit.get_db_session')
    def test_log_tool_call(self, mock_db_session):
        """Test logging a tool call."""
        mock_ctx = Mock()
        mock_ctx.__enter__ = Mock(return_value=mock_ctx)
        mock_ctx.__exit__ = Mock(return_value=False)
        mock_ctx.add = Mock()
        mock_ctx.commit = Mock()
        mock_db_session.return_value = mock_ctx
        
        logger = AuditLogger(enabled=True)
        event_id = logger.log_tool_call(
            tool_name="test_tool",
            success=True,
            duration_ms=100.0,
        )
        
        assert event_id is not None
    
    @patch('app.observability.audit.get_db_session')
    def test_log_subagent_spawn(self, mock_db_session):
        """Test logging a sub-agent spawn."""
        mock_ctx = Mock()
        mock_ctx.__enter__ = Mock(return_value=mock_ctx)
        mock_ctx.__exit__ = Mock(return_value=False)
        mock_ctx.add = Mock()
        mock_ctx.commit = Mock()
        mock_db_session.return_value = mock_ctx
        
        logger = AuditLogger(enabled=True)
        event_id = logger.log_subagent_spawn(
            subagent_type="researcher",
        )
        
        assert event_id is not None
    
    @patch('app.observability.audit.get_db_session')
    def test_log_scheduler_change(self, mock_db_session):
        """Test logging a scheduler change."""
        mock_ctx = Mock()
        mock_ctx.__enter__ = Mock(return_value=mock_ctx)
        mock_ctx.__exit__ = Mock(return_value=False)
        mock_ctx.add = Mock()
        mock_ctx.commit = Mock()
        mock_db_session.return_value = mock_ctx
        
        logger = AuditLogger(enabled=True)
        event_id = logger.log_scheduler_change(
            action="job_added",
            job_id="test_job",
        )
        
        assert event_id is not None
    
    @patch('app.observability.audit.get_db_session')
    def test_log_pause_mode_change(self, mock_db_session):
        """Test logging pause mode change."""
        mock_ctx = Mock()
        mock_ctx.__enter__ = Mock(return_value=mock_ctx)
        mock_ctx.__exit__ = Mock(return_value=False)
        mock_ctx.add = Mock()
        mock_ctx.commit = Mock()
        mock_db_session.return_value = mock_ctx
        
        logger = AuditLogger(enabled=True)
        event_id = logger.log_pause_mode_change(
            paused=True,
            reason="Testing",
        )
        
        assert event_id is not None
    
    def test_log_event_disabled(self):
        """Test logging when disabled."""
        logger = AuditLogger(enabled=False)
        event_id = logger.log_event(
            event_type=AuditEventType.TOOL_CALL,
            details={"test": "data"},
        )
        
        assert event_id is None


class TestTraceManager:
    """Tests for TraceManager."""
    
    def test_initialization(self):
        """Test trace manager initialization."""
        manager = TraceManager(enabled=True)
        assert manager.is_enabled is True
    
    def test_initialization_disabled(self):
        """Test trace manager when disabled."""
        manager = TraceManager(enabled=False)
        assert manager.is_enabled is False
    
    def test_create_trace_id(self):
        """Test creating a trace ID."""
        manager = TraceManager(enabled=True)
        trace_id = manager.create_trace_id()
        
        assert trace_id is not None
        assert len(trace_id) > 0
    
    def test_create_span_id(self):
        """Test creating a span ID."""
        manager = TraceManager(enabled=True)
        span_id = manager.create_span_id()
        
        assert span_id is not None
        assert len(span_id) > 0
    
    def test_start_trace(self):
        """Test starting a new trace."""
        manager = TraceManager(enabled=True)
        span = manager.start_trace("test_trace")
        
        assert span is not None
        assert span.name == "test_trace"
        assert span.trace_id is not None
        assert span.span_id is not None
    
    def test_start_span(self):
        """Test starting a span."""
        manager = TraceManager(enabled=True)
        
        # Start a trace first
        root_span = manager.start_trace("root_trace")
        
        # Start a child span
        child_span = manager.start_span("child_span")
        
        assert child_span is not None
        assert child_span.parent_span_id == root_span.span_id
    
    def test_end_span(self):
        """Test ending a span."""
        manager = TraceManager(enabled=True)
        span = manager.start_trace("test_trace")
        
        manager.end_span(span)
        
        assert span.end_time is not None
        assert span.duration_ms is not None
    
    def test_trace_context_manager(self):
        """Test trace context manager."""
        with tracecontext("test_span") as span:
            assert span is not None
            span.set_attribute("key", "value")
        
        assert span.end_time is not None
    
    def test_inject_trace_context(self):
        """Test injecting trace context."""
        manager = TraceManager(enabled=True)
        manager.start_trace("test_trace")
        
        context = manager.inject_trace_context()
        
        assert "trace_id" in context
        assert "span_id" in context
    
    def test_extract_trace_context(self):
        """Test extracting trace context."""
        manager = TraceManager(enabled=True)
        
        carrier = {"trace_id": "test-trace-id", "span_id": "test-span-id"}
        extracted = manager.extract_trace_context(carrier)
        
        assert extracted == "test-trace-id"
    
    def test_get_trace(self):
        """Test getting trace spans."""
        manager = TraceManager(enabled=True)
        
        trace_id = manager.create_trace_id()
        manager.start_trace("span1", trace_id=trace_id)
        manager.start_span("span2", trace_id=trace_id)
        
        spans = manager.get_trace(trace_id)
        
        assert len(spans) == 2
    
    def test_end_trace(self):
        """Test ending a trace."""
        manager = TraceManager(enabled=True)
        
        trace_id = manager.create_trace_id()
        manager.start_trace("span1", trace_id=trace_id)
        manager.start_span("span2", trace_id=trace_id)
        
        spans = manager.end_trace(trace_id)
        
        assert len(spans) == 2
        # Trace should be cleaned up
        assert manager.get_trace(trace_id) == []


class TestSpan:
    """Tests for Span dataclass."""
    
    def test_span_creation(self):
        """Test creating a span."""
        span = Span(
            trace_id="trace-1",
            span_id="span-1",
            parent_span_id=None,
            name="test_span",
            start_time=datetime.utcnow(),
        )
        
        assert span.trace_id == "trace-1"
        assert span.span_id == "span-1"
        assert span.name == "test_span"
        assert span.status == SpanStatus.OK
    
    def test_span_duration(self):
        """Test span duration calculation."""
        start = datetime.utcnow()
        time.sleep(0.01)  # Sleep 10ms
        end = datetime.utcnow()
        
        span = Span(
            trace_id="trace-1",
            span_id="span-1",
            parent_span_id=None,
            name="test_span",
            start_time=start,
            end_time=end,
        )
        
        assert span.duration_ms >= 10
    
    def test_span_add_event(self):
        """Test adding an event to a span."""
        span = Span(
            trace_id="trace-1",
            span_id="span-1",
            parent_span_id=None,
            name="test_span",
            start_time=datetime.utcnow(),
        )
        
        span.add_event("test_event", {"key": "value"})
        
        assert len(span.events) == 1
        assert span.events[0]["name"] == "test_event"
    
    def test_span_set_attribute(self):
        """Test setting span attributes."""
        span = Span(
            trace_id="trace-1",
            span_id="span-1",
            parent_span_id=None,
            name="test_span",
            start_time=datetime.utcnow(),
        )
        
        span.set_attribute("key", "value")
        
        assert span.attributes["key"] == "value"
    
    def test_span_set_status(self):
        """Test setting span status."""
        span = Span(
            trace_id="trace-1",
            span_id="span-1",
            parent_span_id=None,
            name="test_span",
            start_time=datetime.utcnow(),
        )
        
        span.set_status(SpanStatus.ERROR)
        
        assert span.status == SpanStatus.ERROR
    
    def test_span_to_dict(self):
        """Test converting span to dictionary."""
        span = Span(
            trace_id="trace-1",
            span_id="span-1",
            parent_span_id=None,
            name="test_span",
            start_time=datetime.utcnow(),
        )
        
        span_dict = span.to_dict()
        
        assert span_dict["trace_id"] == "trace-1"
        assert span_dict["span_id"] == "span-1"
        assert span_dict["name"] == "test_span"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
