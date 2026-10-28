"""Retry pipeline — validates and re-executes healed workflows."""

from __future__ import annotations
import asyncio
import copy
from datetime import datetime, timezone
from typing import Any

import config
from models import (
    Incident, IncidentStatus, Workflow, WorkflowStatus, StepStatus
)
from store import store


async def retry_workflow(incident: Incident) -> bool:
    """
    Apply the healing action and retry the failed workflow.
    Returns True if the retry succeeded, False otherwise.
    """
    if not incident.healing_action:
        raise ValueError("No healing action to apply")

    action = incident.healing_action

    incident.status = IncidentStatus.RETRYING
    incident.retry_count += 1
    incident.add_timeline_event(
        "Retry Started",
        f"Attempt #{incident.retry_count} with patched payload"
    )
    store.save_incident(incident)

    await store.broadcast("retry_started", {
        "incident_id": incident.id,
        "retry_count": incident.retry_count,
        "status": "retrying",
    })

    # Get the original workflow to determine its type
    original_workflow = store.get_workflow(incident.workflow_id)
    if not original_workflow:
        incident.status = IncidentStatus.FAILED
        incident.add_timeline_event("Retry Failed", "Original workflow not found")
        store.save_incident(incident)
        return False

    # Determine workflow type from the name
    from workflow_engine import WORKFLOW_TEMPLATES
    workflow_type = None
    for wtype, template in WORKFLOW_TEMPLATES.items():
        if template["name"] == original_workflow.name:
            workflow_type = wtype
            break

    if not workflow_type:
        incident.status = IncidentStatus.FAILED
        incident.add_timeline_event("Retry Failed", "Could not determine workflow type")
        store.save_incident(incident)
        return False

    # Apply the patched payload
    patched_payload = action.patched_payload

    await store.broadcast("retry_payload", {
        "incident_id": incident.id,
        "original_payload": action.original_payload,
        "patched_payload": patched_payload,
    })

    # Small delay before retry
    await asyncio.sleep(config.RETRY_DELAY_SECONDS)

    # Re-run the workflow WITHOUT fault injection
    try:
        from workflow_engine import run_workflow
        result = await run_workflow(
            workflow_type=workflow_type,
            payload=patched_payload,
            fault_type=None,  # No fault this time!
        )

        if result.status == WorkflowStatus.SUCCESS:
            incident.status = IncidentStatus.RESOLVED
            incident.resolved_at = datetime.now(timezone.utc)
            incident.add_timeline_event(
                "✅ Resolved",
                f"Workflow completed successfully after {incident.retry_count} retry attempt(s)"
            )
            store.save_incident(incident)
            store.update_stats()

            await store.broadcast("incident_resolved", {
                "incident_id": incident.id,
                "retry_count": incident.retry_count,
                "status": "resolved",
                "resolution_time_ms": (
                    (incident.resolved_at - incident.created_at).total_seconds() * 1000
                ),
            })
            return True

        else:
            # Retry failed — check if we should try again
            if incident.retry_count < config.MAX_RETRY_ATTEMPTS:
                incident.status = IncidentStatus.AWAITING_APPROVAL
                incident.add_timeline_event(
                    "Retry Failed",
                    f"Attempt #{incident.retry_count} failed. "
                    f"{config.MAX_RETRY_ATTEMPTS - incident.retry_count} retries remaining."
                )
            else:
                incident.status = IncidentStatus.FAILED
                incident.add_timeline_event(
                    "❌ Max Retries Exceeded",
                    f"All {config.MAX_RETRY_ATTEMPTS} retry attempts exhausted. Manual intervention required."
                )
            store.save_incident(incident)
            store.update_stats()

            await store.broadcast("retry_failed", {
                "incident_id": incident.id,
                "retry_count": incident.retry_count,
                "status": incident.status.value,
                "max_retries": config.MAX_RETRY_ATTEMPTS,
            })
            return False

    except Exception as e:
        incident.status = IncidentStatus.FAILED
        incident.add_timeline_event("Retry Exception", str(e))
        store.save_incident(incident)
        store.update_stats()

        await store.broadcast("retry_failed", {
            "incident_id": incident.id,
            "error": str(e),
            "status": "failed",
        })
        return False
