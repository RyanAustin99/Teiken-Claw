"""Typed domain models for Teiken control plane."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class RuntimeStatus(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    DEGRADED = "degraded"
    CRASHED = "crashed"
    STOPPING = "stopping"


class RunnerType(str, Enum):
    INPROCESS = "inprocess"
    SUBPROCESS = "subprocess"


class QueueFullPolicy(str, Enum):
    DENY = "deny"
    DEFER = "defer"
    DROP = "drop"


class OnboardingStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"


class AppConfig(BaseModel):
    """Persisted control-plane user config (small, non-secret)."""

    config_version: int = 1
    configured: bool = False
    data_dir: Optional[str] = None
    ollama_endpoint: str = "http://localhost:11434"
    default_model: str = "llama3.2"
    dev_server_host: str = "0.0.0.0"
    dev_server_port: int = 8000
    log_level: str = "INFO"
    workspace_dir: str = "./data/workspace"
    dangerous_tools_enabled: bool = False
    max_inflight_ollama_requests: int = 2
    max_agent_queue_depth: int = 100
    queue_full_policy: QueueFullPolicy = QueueFullPolicy.DENY
    subprocess_runner_enabled: bool = False
    agent_prompt_template_version: str = "1.0.0"


class AgentOnboardingState(BaseModel):
    user_name: Optional[str] = None
    preferred_agent_name: Optional[str] = None
    purpose: Optional[str] = None
    complete: bool = False


class EffectiveConfig(BaseModel):
    """Layered config with source trace."""

    values: AppConfig
    sources: Dict[str, str] = Field(default_factory=dict)


class AgentRecord(BaseModel):
    """Persistent agent registry record."""

    id: str
    name: str
    description: Optional[str] = None
    model: Optional[str] = None
    tool_profile: str = "safe"
    workspace_path: str
    created_at: datetime
    updated_at: datetime
    status: RuntimeStatus = RuntimeStatus.STOPPED
    last_error: Optional[str] = None
    last_seen_at: Optional[datetime] = None
    is_default: bool = False
    runner_type: Optional[RunnerType] = None
    auto_restart: bool = True
    max_queue_depth: Optional[int] = None
    tool_profile_version: Optional[str] = None
    agent_profile_user_name: Optional[str] = None
    agent_profile_agent_name: Optional[str] = None
    agent_profile_purpose: Optional[str] = None
    onboarding_complete: bool = False
    onboarding_updated_at: Optional[datetime] = None
    prompt_template_version: str = "1.0.0"


class SessionRecord(BaseModel):
    id: str
    agent_id: str
    created_at: datetime
    updated_at: datetime
    title: Optional[str] = None
    onboarding_status: OnboardingStatus = OnboardingStatus.PENDING
    onboarding_step: int = 0


class SessionMessageRecord(BaseModel):
    id: int
    session_id: str
    role: str
    content: str
    created_at: datetime
    tool_name: Optional[str] = None
    tool_ok: Optional[bool] = None
    tool_elapsed_ms: Optional[int] = None


class CheckStatus(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


class DoctorCheck(BaseModel):
    name: str
    status: CheckStatus
    summary: str
    suggestion: Optional[str] = None
    fix_action: Optional[str] = None
    details: Dict[str, str] = Field(default_factory=dict)


class DoctorReport(BaseModel):
    created_at: datetime
    checks: List[DoctorCheck] = Field(default_factory=list)

    @property
    def overall_status(self) -> CheckStatus:
        if any(item.status == CheckStatus.FAIL for item in self.checks):
            return CheckStatus.FAIL
        if any(item.status == CheckStatus.WARN for item in self.checks):
            return CheckStatus.WARN
        return CheckStatus.PASS


class RuntimeEntry(BaseModel):
    agent_id: str
    status: RuntimeStatus
    runner_type: RunnerType
    queued: int = 0
    overflow_count: int = 0
    last_error: Optional[str] = None
    last_heartbeat_at: Optional[datetime] = None


class SupervisorSnapshot(BaseModel):
    dev_server_running: bool = False
    dev_server_url: Optional[str] = None
    global_inflight_ollama: int = 0
    max_inflight_ollama: int = 0
    runtimes: List[RuntimeEntry] = Field(default_factory=list)

