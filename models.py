"""Data models for the Self-Healing AI Automation System."""

from __future__ import annotations
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────────────────────

class ErrorCategory(str, Enum):
    SCHEMA_MISMATCH = "schema_mismatch"
    RATE_LIMIT = "rate_limit"
    BAD_PAYLOAD = "bad_payload"
    TIMEOUT = "timeout"
    MISSING_FIELD = "missing_field"
    AUTH_FAILURE = "auth_failure"
    SERVICE_DOWN = "service_down"
    TYPE_ERROR = "type_error"
    UNKNOWN = "unknown"


class IncidentStatus(str, Enum):
    DETECTED = "detected"
    DIAGNOSING = "diagnosing"
    DIAGNOSED = "diagnosed"
    HEALING = "healing"
    AWAITING_APPROVAL = "awaiting_approval"
    RETRYING = "retrying"
    RESOLVED = "resolved"
    FAILED = "failed"


class WorkflowStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    HEALING = "healing"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


# ── Workflow Models ────────────────────────────────────────────────────

class WorkflowStep(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str
    description: str = ""
    status: StepStatus = StepStatus.PENDING
    input_data: dict[str, Any] = {}
    output_data: dict[str, Any] = {}
    error: Optional[str] = None
    duration_ms: Optional[float] = None


class Workflow(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str
    description: str = ""
    steps: list[WorkflowStep] = []
    status: WorkflowStatus = WorkflowStatus.IDLE
    input_payload: dict[str, Any] = {}
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    current_step_index: int = 0
    fault_type: Optional[str] = None


# ── Incident & Diagnosis Models ────────────────────────────────────────

class Diagnosis(BaseModel):
    root_cause: str
    category: ErrorCategory
    confidence: float = Field(ge=0.0, le=1.0)
    explanation: str
    affected_field: Optional[str] = None
    suggested_action: str = ""


class HealingAction(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    action_type: str  # "payload_patch", "retry_with_backoff", "schema_transform", "fallback"
    description: str
    payload_patch: dict[str, Any] = {}
    original_payload: dict[str, Any] = {}
    patched_payload: dict[str, Any] = {}
    auto_applicable: bool = False
    confidence: float = 0.0


class Incident(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    workflow_id: str
    workflow_name: str
    failed_step: str
    error_type: str
    error_message: str
    traceback: str = ""
    raw_input: dict[str, Any] = {}
    status: IncidentStatus = IncidentStatus.DETECTED
    diagnosis: Optional[Diagnosis] = None
    healing_action: Optional[HealingAction] = None
    retry_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: Optional[datetime] = None
    timeline: list[dict[str, Any]] = []

    def add_timeline_event(self, event: str, details: str = ""):
        self.timeline.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "details": details,
        })


# ── API Models ─────────────────────────────────────────────────────────

class RunWorkflowRequest(BaseModel):
    workflow_type: str
    payload: dict[str, Any] = {}


class InjectFaultRequest(BaseModel):
    workflow_type: str
    fault_type: str
    payload: dict[str, Any] = {}


class SystemStats(BaseModel):
    total_workflows_run: int = 0
    total_incidents: int = 0
    total_resolved: int = 0
    total_failed: int = 0
    auto_healed: int = 0
    avg_resolution_time_ms: float = 0.0
    uptime_percentage: float = 100.0
