"""
System metrics collection for Teiken Claw.

This module provides metrics tracking for system monitoring:
- Job counters
- Tool execution metrics
- Ollama request metrics
- Telegram message counts
- Scheduler metrics
- Sub-agent metrics
"""

import logging
import time
from collections import defaultdict
from datetime import datetime
from threading import Lock
from typing import Any, Dict, Optional

from app.config.settings import settings

logger = logging.getLogger(__name__)


class MetricsCollector:
    """
    Metrics collector for tracking system performance and usage.
    
    Provides counters for various system operations and exposes
    them for Prometheus or other monitoring systems.
    """
    
    # Metric names
    JOBS_QUEUED_TOTAL = "jobs_queued_total"
    JOBS_COMPLETED_TOTAL = "jobs_completed_total"
    JOBS_FAILED_TOTAL = "jobs_failed_total"
    TOOL_CALLS_TOTAL = "tool_calls_total"
    TOOL_ERRORS_TOTAL = "tool_errors_total"
    OLLAMA_REQUESTS_TOTAL = "ollama_requests_total"
    OLLAMA_FAILURES_TOTAL = "ollama_failures_total"
    TELEGRAM_MESSAGES_SENT = "telegram_messages_sent"
    SCHEDULER_RUNS_TOTAL = "scheduler_runs_total"
    SUBAGENT_RUNS_TOTAL = "subagent_runs_total"
    
    def __init__(self, enabled: bool = True):
        """
        Initialize the metrics collector.
        
        Args:
            enabled: Whether metrics collection is enabled
        """
        self._enabled = enabled and settings.METRICS_ENABLED
        self._counters: Dict[str, Dict[tuple, int]] = defaultdict(lambda: defaultdict(int))
        self._counters_lock = Lock()
        self._start_time = time.time()
        
        logger.info(f"MetricsCollector initialized (enabled={self._enabled})")
    
    @property
    def is_enabled(self) -> bool:
        """Check if metrics collection is enabled."""
        return self._enabled
    
    @property
    def uptime_seconds(self) -> float:
        """Get system uptime in seconds."""
        return time.time() - self._start_time
    
    def increment(
        self,
        metric_name: str,
        labels: Optional[Dict[str, str]] = None,
        value: int = 1,
    ) -> None:
        """
        Increment a counter metric.
        
        Args:
            metric_name: Name of the metric
            labels: Optional labels for the metric
            value: Value to increment by
        """
        if not self._enabled:
            return
        
        labels_tuple = tuple(sorted((labels or {}).items()))
        
        with self._counters_lock:
            self._counters[metric_name][labels_tuple] += value
    
    def decrement(
        self,
        metric_name: str,
        labels: Optional[Dict[str, str]] = None,
        value: int = 1,
    ) -> None:
        """
        Decrement a counter metric.
        
        Args:
            metric_name: Name of the metric
            labels: Optional labels for the metric
            value: Value to decrement by
        """
        if not self._enabled:
            return
        
        labels_tuple = tuple(sorted((labels or {}).items()))
        
        with self._counters_lock:
            self._counters[metric_name][labels_tuple] -= value
    
    def get_counter(self, metric_name: str, labels: Optional[Dict[str, str]] = None) -> int:
        """
        Get the current value of a counter metric.
        
        Args:
            metric_name: Name of the metric
            labels: Optional labels for the metric
            
        Returns:
            Current counter value
        """
        labels_tuple = tuple(sorted((labels or {}).items()))
        
        with self._counters_lock:
            return self._counters[metric_name].get(labels_tuple, 0)
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        Get all collected metrics.
        
        Returns:
            Dictionary of all metrics with their values
        """
        if not self._enabled:
            return {"enabled": False}
        
        with self._counters_lock:
            # Build metrics dictionary
            metrics = {
                "enabled": True,
                "uptime_seconds": self.uptime_seconds,
                "timestamp": datetime.utcnow().isoformat(),
                "counters": {},
            }
            
            for metric_name, label_values in self._counters.items():
                if label_values:
                    metrics["counters"][metric_name] = {
                        "_total": sum(label_values.values()),
                    }
                    for labels, value in label_values.items():
                        if labels:
                            label_key = ",".join(f'{k}="{v}"' for k, v in labels)
                            metrics["counters"][metric_name][label_key] = value
                        else:
                            metrics["counters"][metric_name]["_total"] = value
                else:
                    metrics["counters"][metric_name] = {"_total": sum(label_values.values())}
            
            return metrics
    
    def get_prometheus_format(self) -> str:
        """
        Get metrics in Prometheus text format.
        
        Returns:
            Metrics in Prometheus exposition format
        """
        if not self._enabled:
            return ""
        
        lines = []
        
        with self._counters_lock:
            for metric_name, label_values in self._counters.items():
                for labels, value in label_values.items():
                    if labels:
                        label_str = ",".join(f'{k}="{v}"' for k, v in labels)
                        lines.append(f"{metric_name}{{{label_str}}} {value}")
                    else:
                        lines.append(f"{metric_name} {value}")
            
            # Add uptime
            lines.append(f"teiken_claw_uptime_seconds {self.uptime_seconds}")
        
        return "\n".join(lines) + "\n"
    
    # Convenience methods for common metrics
    
    def inc_jobs_queued(self, job_type: str = "default") -> None:
        """Increment jobs queued counter."""
        self.increment(self.JOBS_QUEUED_TOTAL, {"job_type": job_type})
    
    def inc_jobs_completed(self, job_type: str = "default") -> None:
        """Increment jobs completed counter."""
        self.increment(self.JOBS_COMPLETED_TOTAL, {"job_type": job_type})
    
    def inc_jobs_failed(self, job_type: str = "default") -> None:
        """Increment jobs failed counter."""
        self.increment(self.JOBS_FAILED_TOTAL, {"job_type": job_type})
    
    def inc_tool_calls(self, tool_name: str, success: bool = True) -> None:
        """Increment tool calls counter."""
        self.increment(
            self.TOOL_CALLS_TOTAL,
            {"tool_name": tool_name, "success": str(success).lower()}
        )
        if not success:
            self.increment(self.TOOL_ERRORS_TOTAL, {"tool_name": tool_name})
    
    def inc_ollama_requests(self, model: str = "default", success: bool = True) -> None:
        """Increment Ollama requests counter."""
        self.increment(
            self.OLLAMA_REQUESTS_TOTAL,
            {"model": model, "success": str(success).lower()}
        )
        if not success:
            self.increment(self.OLLAMA_FAILURES_TOTAL, {"model": model})
    
    def inc_telegram_messages(self) -> None:
        """Increment Telegram messages sent counter."""
        self.increment(self.TELEGRAM_MESSAGES_SENT)
    
    def inc_scheduler_runs(self) -> None:
        """Increment scheduler runs counter."""
        self.increment(self.SCHEDULER_RUNS_TOTAL)
    
    def inc_subagent_runs(self, subagent_type: str = "default") -> None:
        """Increment sub-agent runs counter."""
        self.increment(self.SUBAGENT_RUNS_TOTAL, {"subagent_type": subagent_type})
    
    def reset(self) -> None:
        """Reset all metrics."""
        with self._counters_lock:
            self._counters.clear()
            self._start_time = time.time()


# Global metrics collector instance
_metrics_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    """Get the global metrics collector instance."""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector


def set_metrics_collector(collector: MetricsCollector) -> None:
    """Set the global metrics collector instance."""
    global _metrics_collector
    _metrics_collector = collector


__all__ = [
    "MetricsCollector",
    "get_metrics_collector",
    "set_metrics_collector",
]
