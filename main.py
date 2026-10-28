"""Self-Healing AI Automation System — FastAPI Application."""

from __future__ import annotations
import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse

import config
from models import (
    InjectFaultRequest, IncidentStatus
)
from store import store
from workflow_engine import run_workflow, WORKFLOW_TEMPLATES
from fault_injector import AVAILABLE_FAULTS
from monitor import detect_and_create_incident
from diagnostics import diagnose_incident
from healer import generate_healing_action
from retry_pipeline import retry_workflow


# ═══════════════════════════════════════════════════════════════════════
# Application Setup
# ═══════════════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("=" * 62)
    print("  Self-Healing AI Automation System")
    print("  Code-E-Fiesta 2026 -- Problem Statement 4")
    print(f"  Dashboard: http://localhost:{config.PORT}")
    print(f"  AI Provider: {config.AI_PROVIDER}")
    print("=" * 62)
    yield


app = FastAPI(
    title="Self-Healing AI Automation System",
    description="AI-powered workflow monitoring, failure detection, diagnosis, and automated recovery",
    version="1.0.0",
    lifespan=lifespan,
)

# Mount static files
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ═══════════════════════════════════════════════════════════════════════
# Dashboard
# ═══════════════════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return FileResponse(str(STATIC_DIR / "index.html"))


# ═══════════════════════════════════════════════════════════════════════
# WebSocket — Real-time Event Stream
# ═══════════════════════════════════════════════════════════════════════

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    queue = store.event_bus.subscribe()
    try:
        while True:
            message = await queue.get()
            await ws.send_text(message)
    except WebSocketDisconnect:
        store.event_bus.unsubscribe(queue)
    except Exception:
        store.event_bus.unsubscribe(queue)


# ═══════════════════════════════════════════════════════════════════════
# REST API Endpoints
# ═══════════════════════════════════════════════════════════════════════

@app.get("/api/workflows/templates")
async def list_workflow_templates():
    """List available workflow templates."""
    templates = []
    for key, tmpl in WORKFLOW_TEMPLATES.items():
        templates.append({
            "id": key,
            "name": tmpl["name"],
            "description": tmpl["description"],
            "steps": [s["name"] for s in tmpl["steps"]],
            "default_payload": tmpl["default_payload"],
        })
    return {"templates": templates}


@app.get("/api/faults")
async def list_faults():
    """List available fault injection types."""
    return {"faults": AVAILABLE_FAULTS}


@app.get("/api/workflows")
async def list_workflows():
    """List all workflow runs."""
    workflows = store.list_workflows()
    return {"workflows": [w.model_dump() for w in workflows[:50]]}


@app.get("/api/incidents")
async def list_incidents():
    """List all incidents."""
    incidents = store.list_incidents()
    return {"incidents": [i.model_dump() for i in incidents[:50]]}


@app.get("/api/incidents/{incident_id}")
async def get_incident(incident_id: str):
    """Get incident details."""
    incident = store.get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident.model_dump()


@app.get("/api/stats")
async def get_stats():
    """Get system statistics."""
    store.update_stats()
    return store.stats.model_dump()


# ── Run a workflow normally ──

@app.post("/api/workflows/run")
async def run_workflow_endpoint(request: InjectFaultRequest):
    """Run a workflow, optionally injecting a fault."""
    workflow_type = request.workflow_type
    if workflow_type not in WORKFLOW_TEMPLATES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown workflow type: {workflow_type}"
        )

    fault_type = request.fault_type if request.fault_type else None
    payload = request.payload if request.payload else None

    # Run the workflow
    workflow = await run_workflow(
        workflow_type=workflow_type,
        payload=payload,
        fault_type=fault_type,
    )

    response_data = {
        "workflow_id": workflow.id,
        "status": workflow.status.value,
        "name": workflow.name,
    }

    # If it failed, trigger the healing pipeline
    if workflow.status.value == "failed":
        incident = await detect_and_create_incident(workflow)
        if incident:
            response_data["incident_id"] = incident.id

            # Run diagnosis + healing in background
            asyncio.create_task(_healing_pipeline(incident))

    return response_data


async def _healing_pipeline(incident):
    """Full healing pipeline: diagnose → heal → (auto-approve?) → retry."""
    try:
        # Step 1: Diagnose
        await asyncio.sleep(0.5)  # Brief delay for visual effect
        diagnosis = await diagnose_incident(incident)

        # Step 2: Generate healing action
        await asyncio.sleep(0.5)
        action = await generate_healing_action(incident)

        # Step 3: Auto-retry if confidence is high enough
        if action.auto_applicable:
            await asyncio.sleep(0.5)
            await retry_workflow(incident)

    except Exception as e:
        print(f"[ERROR] Healing pipeline failed: {e}")
        incident.status = IncidentStatus.FAILED
        incident.add_timeline_event("Pipeline Error", str(e))
        store.save_incident(incident)
        await store.broadcast("incident_updated", {
            "incident_id": incident.id,
            "status": "failed",
            "error": str(e),
        })


# ── Manual Approval ──

@app.post("/api/incidents/{incident_id}/approve")
async def approve_incident(incident_id: str):
    """Approve a healing action and trigger retry."""
    incident = store.get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    if incident.status != IncidentStatus.AWAITING_APPROVAL:
        raise HTTPException(
            status_code=400,
            detail=f"Incident not awaiting approval (status: {incident.status.value})"
        )

    incident.add_timeline_event("Human Approved", "Fix approved by operator — initiating retry")
    store.save_incident(incident)

    await store.broadcast("incident_updated", {
        "incident_id": incident.id,
        "status": "approved",
    })

    # Retry in background
    success = await retry_workflow(incident)
    return {"success": success, "status": incident.status.value}


@app.post("/api/incidents/{incident_id}/reject")
async def reject_incident(incident_id: str):
    """Reject a healing action."""
    incident = store.get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    incident.status = IncidentStatus.FAILED
    incident.add_timeline_event("Human Rejected", "Fix rejected by operator — marking as failed")
    store.save_incident(incident)
    store.update_stats()

    await store.broadcast("incident_updated", {
        "incident_id": incident.id,
        "status": "failed",
    })

    return {"status": "rejected"}


# ── Full Demo: inject → detect → diagnose → heal → retry ──

@app.post("/api/demo/full-cycle")
async def run_full_demo(workflow_type: str = "order_processing", fault_type: str = "missing_field"):
    """Run a complete demo cycle: inject fault → detect → diagnose → heal → retry."""
    if workflow_type not in WORKFLOW_TEMPLATES:
        raise HTTPException(status_code=400, detail=f"Unknown workflow type: {workflow_type}")
    if fault_type not in AVAILABLE_FAULTS:
        raise HTTPException(status_code=400, detail=f"Unknown fault type: {fault_type}")

    await store.broadcast("demo_started", {
        "workflow_type": workflow_type,
        "fault_type": fault_type,
        "message": f"Starting full demo: {WORKFLOW_TEMPLATES[workflow_type]['name']} with {AVAILABLE_FAULTS[fault_type]['name']}",
    })

    # Run workflow with fault
    workflow = await run_workflow(
        workflow_type=workflow_type,
        fault_type=fault_type,
    )

    if workflow.status.value != "failed":
        return {"message": "Workflow succeeded despite fault injection (edge case)", "status": "success"}

    # Detect incident
    incident = await detect_and_create_incident(workflow)
    if not incident:
        return {"message": "No incident detected", "status": "error"}

    # Run healing pipeline
    await _healing_pipeline(incident)

    return {
        "workflow_id": workflow.id,
        "incident_id": incident.id,
        "final_status": incident.status.value,
    }


# ═══════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=config.HOST,
        port=config.PORT,
        reload=True,
    )
