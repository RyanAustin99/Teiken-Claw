"""
Health check endpoints for Teiken Claw.

Provides health, readiness, and liveness endpoints for monitoring:
- /health - Basic health check
- /health/ready - Readiness check (DB, Ollama, scheduler)
- /health/live - Liveness check
"""

import time
from fastapi import APIRouter, Depends
from typing import Any, Dict, Optional

from app.config.settings import settings
from app.db import verify_db
from app.agent import get_ollama_client, get_circuit_breaker_metrics

# Global references (set from main.py)
_dispatcher = None
_worker_pool = None
_outbound_queue = None
_scheduler_service = None
_control_state_manager = None
_dead_letter_queue = None


def set_health_dependencies(
    dispatcher=None,
    worker_pool=None,
    outbound_queue=None,
    scheduler_service=None,
    control_state_manager=None,
    dead_letter_queue=None,
):
    """Set dependencies for health checks (called from main.py)."""
    global _dispatcher, _worker_pool, _outbound_queue
    global _scheduler_service, _control_state_manager, _dead_letter_queue
    
    _dispatcher = dispatcher
    _worker_pool = worker_pool
    _outbound_queue = outbound_queue
    _scheduler_service = scheduler_service
    _control_state_manager = control_state_manager
    _dead_letter_queue = dead_letter_queue


router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    Basic health check endpoint.
    
    Returns:
        Dict: Health status and version info.
    """
    start_time = time.time()
    
    # Get circuit breaker metrics
    cb_metrics = get_circuit_breaker_metrics()
    
    return {
        "status": "healthy",
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "circuit_breakers": {
            "total": cb_metrics.total_breakers,
            "healthy": cb_metrics.closed_count,
            "open": cb_metrics.open_count,
            "half_open": cb_metrics.half_open_count,
        },
        "latency_ms": round((time.time() - start_time) * 1000, 2),
    }


@router.get("/health/ready")
async def readiness_check() -> Dict[str, Any]:
    """
    Readiness check endpoint.
    
    Verifies database connectivity, queue system status, and Ollama connectivity.
    
    Returns:
        Dict: Readiness status with component details.
    """
    components: Dict[str, Any] = {}
    overall_status = "healthy"
    
    # Check database with latency
    db_start = time.time()
    try:
        db_result = await verify_db()
        db_latency = (time.time() - db_start) * 1000
        
        components["database"] = {
            "ok": db_result["status"] == "healthy",
            "latency_ms": round(db_latency, 2),
            "issues": db_result.get("issues", []),
        }
        if db_result["status"] != "healthy":
            overall_status = "degraded"
    except Exception as e:
        db_latency = (time.time() - db_start) * 1000
        components["database"] = {
            "ok": False,
            "latency_ms": round(db_latency, 2),
            "error": str(e),
        }
        overall_status = "unhealthy"
    
    # Check Ollama connectivity
    ollama_start = time.time()
    try:
        ollama_client = get_ollama_client()
        ollama_health = await ollama_client.check_health()
        ollama_latency = (time.time() - ollama_start) * 1000
        
        # Get current model from settings
        model = settings.OLLAMA_CHAT_MODEL
        
        components["ollama"] = {
            "ok": ollama_health["status"] == "healthy",
            "model": model,
            "latency_ms": round(ollama_latency, 2),
            "base_url": ollama_health.get("base_url"),
            "model_count": ollama_health.get("model_count", 0),
            "circuit_breaker": ollama_health.get("circuit_breaker", {}).get("state", "unknown"),
        }
        if ollama_health["status"] != "healthy":
            overall_status = "degraded"
    except Exception as e:
        ollama_latency = (time.time() - ollama_start) * 1000
        components["ollama"] = {
            "ok": False,
            "model": settings.OLLAMA_CHAT_MODEL,
            "latency_ms": round(ollama_latency, 2),
            "error": str(e),
        }
        overall_status = "degraded"  # Ollama not critical for basic readiness
    
    # Check queue system
    if _dispatcher:
        components["queue"] = {
            "ok": not _dispatcher.is_shutdown,
            "depth": _dispatcher.queue_depth,
            "pending": _dispatcher.pending_count,
        }
        if _dispatcher.is_shutdown:
            overall_status = "degraded"
    else:
        components["queue"] = {"ok": False, "error": "not_initialized"}
        overall_status = "degraded"
    
    # Check worker pool
    if _worker_pool:
        worker_status = _worker_pool.get_status()
        components["workers"] = {
            "ok": worker_status["running"],
            "alive": worker_status["active_workers"],
            "total_processed": worker_status["total_jobs_processed"],
        }
        if not worker_status["running"]:
            overall_status = "degraded"
    else:
        components["workers"] = {"ok": False, "error": "not_initialized"}
        overall_status = "degraded"
    
    # Check scheduler
    if settings.SCHEDULER_ENABLED:
        if _scheduler_service and _scheduler_service.is_running():
            job_count = len(_scheduler_service.list_jobs())
            components["scheduler"] = {
                "ok": True,
                "jobs_count": job_count,
                "paused": False,
            }
        else:
            components["scheduler"] = {
                "ok": False,
                "jobs_count": 0,
                "paused": True,
                "status": "stopped" if _scheduler_service else "not_initialized",
            }
            overall_status = "degraded"
        
        # Check control state
        if _control_state_manager:
            components["control_state"] = {
                "state": _control_state_manager.get_state(),
            }
    else:
        components["scheduler"] = {"ok": True, "disabled": True}
    
    # Check circuit breaker
    cb_metrics = get_circuit_breaker_metrics()
    components["circuit_breaker"] = {
        "state": "closed" if cb_metrics.closed_count == cb_metrics.total_breakers else "degraded",
        "failure_count": cb_metrics.total_failures,
        "total_breakers": cb_metrics.total_breakers,
    }
    
    return {
        "status": overall_status,
        "version": settings.APP_VERSION,
        "components": components,
    }


@router.get("/health/live")
async def liveness_check() -> Dict[str, Any]:
    """
    Liveness check endpoint.
    
    Simple check to verify the application is running.
    
    Returns:
        Dict: Liveness status.
    """
    return {"status": "alive"}


__all__ = ["router", "set_health_dependencies"]