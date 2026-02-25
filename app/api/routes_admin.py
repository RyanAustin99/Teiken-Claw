"""
Admin endpoints for Teiken Claw.

Provides administrative control endpoints:
- /admin/pause - Pause system
- /admin/resume - Resume system
- /admin/jobs/dead-letter - List dead-letter jobs
- /admin/jobs/replay/{id} - Replay a dead-letter job
- /admin/metrics - Get metrics
- /admin/audit - Query audit logs
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Any, Dict, List, Optional

from app.config.settings import settings
from app.observability.metrics import get_metrics_collector
from app.observability.audit import get_audit_logger, AuditEventType

# Global references (set from main.py)
_control_state_manager = None
_dead_letter_queue = None
_dispatcher = None


def set_admin_dependencies(
    control_state_manager=None,
    dead_letter_queue=None,
    dispatcher=None,
):
    """Set dependencies for admin endpoints (called from main.py)."""
    global _control_state_manager, _dead_letter_queue, _dispatcher
    
    _control_state_manager = control_state_manager
    _dead_letter_queue = dead_letter_queue
    _dispatcher = dispatcher


router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/pause")
async def pause_system(reason: Optional[str] = None) -> Dict[str, Any]:
    """
    Pause the system (stop processing new jobs).
    
    Args:
        reason: Optional reason for pausing
    
    Returns:
        Dict: Result of pause operation
    """
    if not _control_state_manager:
        raise HTTPException(status_code=500, detail="Control state manager not initialized")
    
    try:
        _control_state_manager.pause(reason or "Manual pause via admin API")
        return {
            "success": True,
            "state": "paused",
            "reason": reason,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to pause: {str(e)}")


@router.post("/resume")
async def resume_system(reason: Optional[str] = None) -> Dict[str, Any]:
    """
    Resume the system (resume processing jobs).
    
    Args:
        reason: Optional reason for resuming
    
    Returns:
        Dict: Result of resume operation
    """
    if not _control_state_manager:
        raise HTTPException(status_code=500, detail="Control state manager not initialized")
    
    try:
        _control_state_manager.resume(reason or "Manual resume via admin API")
        return {
            "success": True,
            "state": "running",
            "reason": reason,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to resume: {str(e)}")


@router.get("/state")
async def get_state() -> Dict[str, Any]:
    """
    Get current system state.
    
    Returns:
        Dict: Current system state
    """
    if not _control_state_manager:
        raise HTTPException(status_code=500, detail="Control state manager not initialized")
    
    return {
        "state": _control_state_manager.get_state(),
        "reason": _control_state_manager.get_pause_reason(),
    }


@router.get("/jobs/dead-letter")
async def list_dead_letter_jobs(
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
        raise HTTPException(status_code=500, detail="Dead-letter queue not initialized")
    
    try:
        entries = await _dead_letter_queue.list(limit=limit, offset=offset)
        count = await _dead_letter_queue.count()
        
        return {
            "entries": entries,
            "total": count,
            "limit": limit,
            "offset": offset,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list dead-letter: {str(e)}")


@router.post("/jobs/dead-letter/{job_id}/replay")
async def replay_dead_letter_job(job_id: str) -> Dict[str, Any]:
    """
    Replay a dead-letter job.
    
    Args:
        job_id: The ID of the job to replay
    
    Returns:
        Dict: Result of replay operation
    """
    if not _dead_letter_queue:
        raise HTTPException(status_code=500, detail="Dead-letter queue not initialized")
    
    if not _dispatcher:
        raise HTTPException(status_code=500, detail="Dispatcher not initialized")
    
    try:
        # Get the job from dead letter
        entries = await _dead_letter_queue.list(limit=1000, offset=0)
        job = None
        for entry in entries:
            if str(entry.get("id")) == str(job_id):
                job = entry
                break
        
        if not job:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found in dead-letter queue")
        
        # Re-queue the job
        await _dead_letter_queue.remove(int(job_id))
        await _dispatcher.enqueue(job.get("job_type", "default"), job.get("payload", {}))
        
        return {
            "success": True,
            "job_id": job_id,
            "message": "Job requeued successfully",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to replay job: {str(e)}")


@router.delete("/jobs/dead-letter/{job_id}")
async def delete_dead_letter_job(job_id: str) -> Dict[str, Any]:
    """
    Delete a dead-letter job.
    
    Args:
        job_id: The ID of the job to delete
    
    Returns:
        Dict: Result of delete operation
    """
    if not _dead_letter_queue:
        raise HTTPException(status_code=500, detail="Dead-letter queue not initialized")
    
    try:
        await _dead_letter_queue.remove(int(job_id))
        return {
            "success": True,
            "job_id": job_id,
            "message": "Job deleted successfully",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete job: {str(e)}")


@router.get("/metrics")
async def get_metrics() -> Dict[str, Any]:
    """
    Get system metrics.
    
    Returns:
        Dict: System metrics
    """
    metrics = get_metrics_collector()
    return metrics.get_metrics()


@router.get("/metrics/prometheus")
async def get_metrics_prometheus() -> str:
    """
    Get system metrics in Prometheus format.
    
    Returns:
        str: Metrics in Prometheus exposition format
    """
    metrics = get_metrics_collector()
    return metrics.get_prometheus_format()


@router.get("/audit")
async def get_audit_logs(
    event_type: Optional[str] = Query(None),
    session_id: Optional[int] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> Dict[str, Any]:
    """
    Query audit logs.
    
    Args:
        event_type: Filter by event type
        session_id: Filter by session ID
        limit: Maximum number of entries to return
        offset: Number of entries to skip
    
    Returns:
        Dict: Audit log entries
    """
    audit = get_audit_logger()
    
    if not audit.is_enabled:
        return {"enabled": False, "events": []}
    
    # Parse event type
    audit_event_type = None
    if event_type:
        try:
            audit_event_type = AuditEventType(event_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid event type: {event_type}")
    
    try:
        events = audit.get_events(
            event_type=audit_event_type,
            session_id=session_id,
            limit=limit,
            offset=offset,
        )
        
        return {
            "enabled": True,
            "events": events,
            "limit": limit,
            "offset": offset,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to query audit logs: {str(e)}")


__all__ = ["router", "set_admin_dependencies"]