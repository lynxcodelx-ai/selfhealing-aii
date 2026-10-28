"""In-memory data store and event bus for the system."""

from __future__ import annotations
import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from models import Incident, Workflow, SystemStats, IncidentStatus


class EventBus:
    """Simple pub-sub event bus for WebSocket broadcasting."""

    def __init__(self):
        self._subscribers: list[asyncio.Queue] = []

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue):
        if queue in self._subscribers:
            self._subscribers.remove(queue)

    async def publish(self, event_type: str, data: dict[str, Any]):
        message = json.dumps({
            "type": event_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        dead_queues = []
        for queue in self._subscribers:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                dead_queues.append(queue)
        for q in dead_queues:
            self._subscribers.remove(q)


class DataStore:
    """In-memory store for workflows and incidents."""

    def __init__(self):
        self.workflows: dict[str, Workflow] = {}
        self.incidents: dict[str, Incident] = {}
        self.stats = SystemStats()
        self.event_bus = EventBus()
        self._history: list[dict[str, Any]] = []

    # ── Workflow CRUD ──
    def save_workflow(self, workflow: Workflow):
        self.workflows[workflow.id] = workflow

    def get_workflow(self, workflow_id: str) -> Workflow | None:
        return self.workflows.get(workflow_id)

    def list_workflows(self) -> list[Workflow]:
        return sorted(self.workflows.values(), key=lambda w: w.created_at, reverse=True)

    # ── Incident CRUD ──
    def save_incident(self, incident: Incident):
        self.incidents[incident.id] = incident

    def get_incident(self, incident_id: str) -> Incident | None:
        return self.incidents.get(incident_id)

    def list_incidents(self) -> list[Incident]:
        return sorted(self.incidents.values(), key=lambda i: i.created_at, reverse=True)

    # ── Stats ──
    def update_stats(self):
        incidents = list(self.incidents.values())
        self.stats.total_workflows_run = len(self.workflows)
        self.stats.total_incidents = len(incidents)
        self.stats.total_resolved = sum(
            1 for i in incidents if i.status == IncidentStatus.RESOLVED
        )
        self.stats.total_failed = sum(
            1 for i in incidents if i.status == IncidentStatus.FAILED
        )
        self.stats.auto_healed = sum(
            1 for i in incidents
            if i.status == IncidentStatus.RESOLVED
            and i.healing_action
            and i.healing_action.auto_applicable
        )

        resolved = [i for i in incidents if i.resolved_at and i.created_at]
        if resolved:
            total_ms = sum(
                (i.resolved_at - i.created_at).total_seconds() * 1000
                for i in resolved
            )
            self.stats.avg_resolution_time_ms = total_ms / len(resolved)

        total = self.stats.total_workflows_run
        if total > 0:
            failed_unresolved = sum(
                1 for i in incidents if i.status == IncidentStatus.FAILED
            )
            self.stats.uptime_percentage = round(
                ((total - failed_unresolved) / total) * 100, 1
            )

    # ── Event Broadcasting ──
    async def broadcast(self, event_type: str, data: dict[str, Any]):
        self._history.append({"type": event_type, "data": data})
        await self.event_bus.publish(event_type, data)


# Global singleton
store = DataStore()
