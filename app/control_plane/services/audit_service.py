"""Audit service for control-plane state-changing operations."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.control_plane.infra.audit_repo import ControlPlaneAuditRepository


class AuditService:
    """Facade over local control-plane audit persistence."""

    def __init__(self, repo: ControlPlaneAuditRepository) -> None:
        self.repo = repo

    def log(self, action: str, target: Optional[str] = None, details: Optional[Dict[str, Any]] = None, actor: str = "system") -> None:
        self.repo.log(action=action, target=target, details=details, actor=actor)

    def list_recent(self, limit: int = 100) -> List[Dict[str, Any]]:
        return self.repo.list_recent(limit=limit)

