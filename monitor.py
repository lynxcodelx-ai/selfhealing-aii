"""Monitor module — detects workflow failures and creates incidents."""

from __future__ import annotations
import traceback
from datetime import datetime, timezone
from typing import Any

from models import (
    Incident, IncidentStatus, Workflow, WorkflowStatus, StepStatus
)
from store import store


async def detect_and_create_incident(workflow: Workflow) -> Incident | None:
    """
    Inspect a failed workflow, create an Incident, and broadcast it.
    Returns the Incident or None if the workflow didn't fail.
    """
    if workflow.status != WorkflowStatus.FAILED:
        return None

    # Find the failed step
    failed_step = None
    for step in workflow.steps:
        if step.status == StepStatus.FAILED:
            failed_step = step
            break

    if not failed_step:
        return None

    # Determine error type
    error_msg = failed_step.error or "Unknown error"
    error_type = _classify_error_type(error_msg)

    # Create incident
    incident = Incident(
        workflow_id=workflow.id,
        workflow_name=workflow.name,
        failed_step=failed_step.name,
        error_type=error_type,
        error_message=error_msg,
        raw_input=failed_step.input_data,
        status=IncidentStatus.DETECTED,
    )
    incident.add_timeline_event(
        "Incident Detected",
        f"Workflow '{workflow.name}' failed at step '{failed_step.name}': {error_msg}"
    )

    store.save_incident(incident)
    store.update_stats()

    await store.broadcast("incident_created", {
        "incident_id": incident.id,
        "workflow_id": workflow.id,
        "workflow_name": workflow.name,
        "failed_step": failed_step.name,
        "error_type": error_type,
        "error_message": error_msg,
        "status": incident.status.value,
        "created_at": incident.created_at.isoformat(),
        "input_data": failed_step.input_data,
    })

    return incident


def _classify_error_type(error_message: str) -> str:
    """Quick heuristic classification of the error."""
    msg = error_message.lower()
    if "missing" in msg and "field" in msg:
        return "MissingFieldError"
    if "schema" in msg:
        return "SchemaValidationError"
    if "type" in msg or "must be" in msg:
        return "TypeError"
    if "timeout" in msg or "timed out" in msg:
        return "TimeoutError"
    if "rate limit" in msg or "429" in msg:
        return "RateLimitError"
    if "auth" in msg or "401" in msg or "403" in msg:
        return "AuthenticationError"
    if "connect" in msg or "unreachable" in msg:
        return "ConnectionError"
    if "invalid" in msg:
        return "ValidationError"
    return "RuntimeError"
