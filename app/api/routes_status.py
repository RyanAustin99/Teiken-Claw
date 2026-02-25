"""
Status endpoints for Teiken Claw.

Provides comprehensive system status information:
- /status - Full system status
- /status/queue - Queue system status
- /status/dead-letter - Dead letter queue status
"""

from fastapi import APIRouter, Query
from typing import Any, Dict, Optional

from app.config.settings import settings
from app.agent import get_circuit_breaker_metrics
from app.observability.metrics import get_metrics_collector

# Global references (set from main.py)
_dispatcher = None
_worker_pool = None
_outbound_queue = None
_lock_manager = None
_dead_letter_queue = None
_scheduler_service = None
_control_state_manager = None


def set_status_dependencies(
    dispatcher=None,
    worker_pool=None,
    outbound_queue=None,
    lock_manager=None,
    dead_letter_queue=None,
    scheduler_service=None,
    control_state_manager=None,
):
    """Set dependencies for status checks (called from main.py)."""
    global _dispatcher, _worker_pool, _outbound_queue
    global _lock_manager, _dead_letter_queue
    global _scheduler_service, _control_state_manager
    
    _dispatcher = dispatcher
    _worker_pool = worker_pool
    _outbound_queue = outbound_queue
    _lock_manager = lock_manager
    _dead_letter_queue = dead_letter_queue
    _scheduler_service = scheduler_service
    _control_state_manager = control_state_manager


router = APIRouter(tags=["status"])


@router.get("/status")
async def get_status() -> Dict[str, Any]:
    """
    Get full application status.
    
    Returns:
        Dict: Comprehensive application status.
    """
    # Get circuit breaker metrics
    cb_metrics = get_circuit_breaker_metrics()
    
    # Get metrics collector
    metrics = get_metrics_collector()
    metrics_data = metrics.get_metrics() if metrics.is_enabled else {"enabled": False}
    
    # Build status
    status = {
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "debug": settings.DEBUG,
        "uptime_seconds": metrics.uptime_seconds if metrics.is_enabled else 0,
        "features": {
            "cli_enabled": settings.ENABLE_CLI,
            "telegram_enabled": settings.ENABLE_TELEGRAM,
            "memory_enabled": settings.AUTO_MEMORY_ENABLED,
            "scheduler_enabled": settings.SCHEDULER_ENABLED,
            "audit_enabled": settings.AUDIT_ENABLED,
            "metrics_enabled": settings.METRICS_ENABLED,
            "tracing_enabled": settings.TRACING_ENABLED,
        },
        "circuit_breakers": {
            "total": cb_metrics.total_breakers,
            "healthy": cb_metrics.closed_count,
            "open": cb_metrics.open_count,
            "half_open": cb_metrics.half_open_count,
            "total_failures": cb_metrics.total_failures,
        },
    }
    
    # Add queue status
    if _dispatcher:
        status["dispatcher"] = _dispatcher.get_stats()
    else:
        status["dispatcher"] = None
    
    if _worker_pool:
        status["workers"] = _worker_pool.get_status()
    else:
        status["workers"] = None
    
    if _outbound_queue:
        status["outbound"] = _outbound_queue.get_stats()
    else:
        status["outbound"] = None
    
    if _lock_manager:
        status["locks"] = {"count": _lock_manager.get_lock_count()}
    else:
        status["locks"] = None
    
    if _dead_letter_queue:
        status["dead_letter"] = _dead_letter_queue.get_stats()
    else:
        status["dead_letter"] = None
    
    # Add scheduler status
    if settings.SCHEDULER_ENABLED:
        if _scheduler_service:
            status["scheduler"] = {
                "running": _scheduler_service.is_running(),
                "jobs_count": len(_scheduler_service.list_jobs()),
            }
        else:
            status["scheduler"] = {"running": False, "jobs_count": 0}
        
        if _control_state_manager:
            status["control_state"] = {
                "state": _control_state_manager.get_state(),
            }
    else:
        status["scheduler"] = {"enabled": False}
    
    # Add metrics
    status["metrics"] = metrics_data
    
    return status


@router.get("/status/queue")
async def get_queue_status() -> Dict[str, Any]:
    """
    Get queue system status.
    
    Returns:
        Dict: Detailed queue system status.
    """
    return {
        "dispatcher": _dispatcher.get_stats() if _dispatcher else None,
        "workers": _worker_pool.get_status() if _worker_pool else None,
        "outbound": _outbound_queue.get_stats() if _outbound_queue else None,
        "locks": {"count": _lock_manager.get_lock_count()} if _lock_manager else None,
        "dead_letter": _dead_letter_queue.get_stats() if _dead_letter_queue else None,
    }


@router.get("/status/dead-letter")
async def list_dead_letter(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> Dict[str, Any]:
    """
    List dead-letter queue entries.
    
    Args:
        limit: Maximum number of entries to return
        offset: Number of entries to skip
    
    Returns:
        Dict: List of dead-letter entries
    """
    if not _dead_letter_queue:
        return {"error": "Dead-letter queue not initialized", "entries": []}
    
    entries = await _dead_letter_queue.list(limit=limit, offset=offset)
    count = await _dead_letter_queue.count()
    
    return {
        "entries": entries,
        "total": count,
        "limit": limit,
        "offset": offset,
    }


__all__ = ["router", "set_status_dependencies"]