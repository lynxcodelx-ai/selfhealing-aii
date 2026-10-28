"""Simulated business workflows with injectable failure points."""

from __future__ import annotations
import asyncio
import time
import traceback
from typing import Any

from models import (
    Workflow, WorkflowStep, WorkflowStatus, StepStatus, ErrorCategory
)
from store import store


# ═══════════════════════════════════════════════════════════════════════
# Workflow Step Functions — each simulates a real business operation
# ═══════════════════════════════════════════════════════════════════════

async def validate_order(data: dict) -> dict:
    """Validate incoming order payload."""
    required = ["order_id", "customer_id", "items", "total_amount"]
    missing = [f for f in required if f not in data]
    if missing:
        raise ValueError(f"Missing required fields: {missing}")
    if not isinstance(data["items"], list) or len(data["items"]) == 0:
        raise TypeError("'items' must be a non-empty list")
    if not isinstance(data["total_amount"], (int, float)):
        raise TypeError(f"'total_amount' must be numeric, got {type(data['total_amount']).__name__}")
    if data["total_amount"] <= 0:
        raise ValueError("total_amount must be positive")
    return {"validated": True, "order_id": data["order_id"]}


async def check_inventory(data: dict) -> dict:
    """Check inventory availability for order items."""
    items = data.get("items", [])
    if not items:
        raise ValueError("No items to check inventory for")
    # Simulate inventory check
    await asyncio.sleep(0.1)
    for item in items:
        if not isinstance(item, dict):
            raise TypeError(f"Each item must be a dict, got {type(item).__name__}")
        if "sku" not in item:
            raise ValueError(f"Item missing 'sku' field: {item}")
        if "quantity" not in item:
            raise ValueError(f"Item missing 'quantity' field: {item}")
    return {"in_stock": True, "items_checked": len(items)}


async def process_payment(data: dict) -> dict:
    """Process payment for the order."""
    total = data.get("total_amount", 0)
    payment_method = data.get("payment_method", "credit_card")
    if total <= 0:
        raise ValueError("Invalid payment amount")
    # Simulate payment gateway
    await asyncio.sleep(0.15)
    return {
        "payment_id": f"PAY-{data.get('order_id', 'unknown')[:8]}",
        "status": "completed",
        "amount": total,
        "method": payment_method,
    }


async def send_confirmation(data: dict) -> dict:
    """Send order confirmation email."""
    customer_id = data.get("customer_id", "")
    email = data.get("email", f"{customer_id}@example.com")
    if not customer_id:
        raise ValueError("No customer_id for confirmation")
    await asyncio.sleep(0.05)
    return {"email_sent": True, "recipient": email}


async def extract_data(data: dict) -> dict:
    """Extract data from source system."""
    source = data.get("source_url", "")
    if not source:
        raise ValueError("No source_url provided")
    # Simulate API call
    await asyncio.sleep(0.2)
    return {
        "records_extracted": data.get("record_count", 100),
        "source": source,
        "format": data.get("format", "json"),
    }


async def transform_data(data: dict) -> dict:
    """Transform extracted data to target schema."""
    records = data.get("records", [])
    schema = data.get("target_schema", {})
    if not schema:
        raise ValueError("No target_schema defined")
    # Simulate transformation
    await asyncio.sleep(0.1)
    return {
        "records_transformed": data.get("records_extracted", len(records)),
        "schema_applied": True,
        "output_format": schema.get("format", "parquet"),
    }


async def validate_schema(data: dict) -> dict:
    """Validate transformed data against expected schema."""
    expected_fields = data.get("expected_fields", [])
    record_sample = data.get("record_sample", {})
    if expected_fields and record_sample:
        missing = [f for f in expected_fields if f not in record_sample]
        if missing:
            raise ValueError(f"Schema validation failed — missing fields: {missing}")
    await asyncio.sleep(0.05)
    return {"schema_valid": True, "fields_validated": len(expected_fields)}


async def load_to_database(data: dict) -> dict:
    """Load validated data into the target database."""
    target = data.get("target_table", "")
    if not target:
        raise ValueError("No target_table specified")
    await asyncio.sleep(0.15)
    return {
        "rows_loaded": data.get("records_transformed", 0),
        "target_table": target,
        "status": "success",
    }


async def validate_user(data: dict) -> dict:
    """Validate user registration data."""
    required = ["username", "email", "password"]
    missing = [f for f in required if f not in data]
    if missing:
        raise ValueError(f"Missing user fields: {missing}")
    email = data.get("email", "")
    if "@" not in email:
        raise ValueError(f"Invalid email format: {email}")
    return {"user_valid": True, "username": data["username"]}


async def create_account(data: dict) -> dict:
    """Create user account in the system."""
    username = data.get("username", "")
    if not username:
        raise ValueError("No username provided")
    await asyncio.sleep(0.1)
    return {
        "account_id": f"USR-{username[:6].upper()}",
        "created": True,
        "tier": data.get("tier", "free"),
    }


async def send_welcome_email(data: dict) -> dict:
    """Send welcome email to new user."""
    email = data.get("email", "")
    if not email:
        raise ValueError("No email for welcome message")
    await asyncio.sleep(0.05)
    return {"welcome_sent": True, "email": email}


async def setup_preferences(data: dict) -> dict:
    """Set up default user preferences."""
    account_id = data.get("account_id", "")
    if not account_id:
        raise ValueError("No account_id for preferences setup")
    await asyncio.sleep(0.05)
    return {
        "preferences_set": True,
        "defaults_applied": ["notifications", "theme", "language"],
    }


# ═══════════════════════════════════════════════════════════════════════
# Workflow Definitions
# ═══════════════════════════════════════════════════════════════════════

WORKFLOW_TEMPLATES: dict[str, dict] = {
    "order_processing": {
        "name": "Order Processing Pipeline",
        "description": "Validates, processes payment, and confirms customer orders",
        "steps": [
            {"name": "Validate Order", "func": validate_order},
            {"name": "Check Inventory", "func": check_inventory},
            {"name": "Process Payment", "func": process_payment},
            {"name": "Send Confirmation", "func": send_confirmation},
        ],
        "default_payload": {
            "order_id": "ORD-20261028-001",
            "customer_id": "CUST-4521",
            "email": "customer@example.com",
            "items": [
                {"sku": "WIDGET-A", "quantity": 2, "price": 29.99},
                {"sku": "GADGET-B", "quantity": 1, "price": 49.99},
            ],
            "total_amount": 109.97,
            "payment_method": "credit_card",
        },
    },
    "data_etl": {
        "name": "Data ETL Pipeline",
        "description": "Extracts, transforms, validates, and loads data between systems",
        "steps": [
            {"name": "Extract Data", "func": extract_data},
            {"name": "Transform Data", "func": transform_data},
            {"name": "Validate Schema", "func": validate_schema},
            {"name": "Load to Database", "func": load_to_database},
        ],
        "default_payload": {
            "source_url": "https://api.datasource.com/v2/records",
            "record_count": 1500,
            "format": "json",
            "target_schema": {"format": "parquet", "version": "2.0"},
            "expected_fields": ["id", "name", "value", "timestamp"],
            "record_sample": {"id": 1, "name": "test", "value": 42, "timestamp": "2026-10-28"},
            "target_table": "analytics.processed_records",
        },
    },
    "user_onboarding": {
        "name": "User Onboarding Pipeline",
        "description": "Registers new users, creates accounts, and sets up profiles",
        "steps": [
            {"name": "Validate User", "func": validate_user},
            {"name": "Create Account", "func": create_account},
            {"name": "Send Welcome Email", "func": send_welcome_email},
            {"name": "Setup Preferences", "func": setup_preferences},
        ],
        "default_payload": {
            "username": "divyansh_dev",
            "email": "divyansh@example.com",
            "password": "secureP@ss123",
            "tier": "pro",
        },
    },
}


# ═══════════════════════════════════════════════════════════════════════
# Workflow Runner
# ═══════════════════════════════════════════════════════════════════════

async def run_workflow(
    workflow_type: str,
    payload: dict[str, Any] | None = None,
    fault_type: str | None = None,
) -> Workflow:
    """Run a workflow with the given payload, optionally injecting a fault."""
    template = WORKFLOW_TEMPLATES.get(workflow_type)
    if not template:
        raise ValueError(f"Unknown workflow type: {workflow_type}")

    # Merge payloads
    effective_payload = {**template["default_payload"], **(payload or {})}

    # Create workflow instance
    workflow = Workflow(
        name=template["name"],
        description=template["description"],
        input_payload=effective_payload,
        status=WorkflowStatus.RUNNING,
        fault_type=fault_type,
    )

    # Create steps
    for step_def in template["steps"]:
        workflow.steps.append(WorkflowStep(
            name=step_def["name"],
            description=f"Execute: {step_def['name']}",
        ))

    store.save_workflow(workflow)
    await store.broadcast("workflow_started", {
        "workflow_id": workflow.id,
        "name": workflow.name,
        "steps": [s.name for s in workflow.steps],
        "fault_type": fault_type,
    })

    # If fault injection requested, modify payload
    if fault_type:
        from fault_injector import inject_fault
        effective_payload = inject_fault(fault_type, effective_payload, workflow_type)
        workflow.input_payload = effective_payload

    # Execute steps sequentially
    step_data = effective_payload.copy()
    failed = False

    for idx, step_def in enumerate(template["steps"]):
        step = workflow.steps[idx]
        step.status = StepStatus.RUNNING
        step.input_data = step_data.copy()
        workflow.current_step_index = idx
        store.save_workflow(workflow)

        await store.broadcast("step_started", {
            "workflow_id": workflow.id,
            "step_index": idx,
            "step_name": step.name,
        })

        start_time = time.time()
        try:
            func = step_def["func"]
            result = await func(step_data)
            elapsed = (time.time() - start_time) * 1000

            step.status = StepStatus.SUCCESS
            step.output_data = result
            step.duration_ms = round(elapsed, 2)
            # Merge result into step_data for next step
            step_data.update(result)

            await store.broadcast("step_completed", {
                "workflow_id": workflow.id,
                "step_index": idx,
                "step_name": step.name,
                "status": "success",
                "duration_ms": step.duration_ms,
                "output": result,
            })

        except Exception as e:
            elapsed = (time.time() - start_time) * 1000
            step.status = StepStatus.FAILED
            step.error = str(e)
            step.duration_ms = round(elapsed, 2)
            failed = True

            tb = traceback.format_exc()
            await store.broadcast("step_failed", {
                "workflow_id": workflow.id,
                "step_index": idx,
                "step_name": step.name,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "traceback": tb,
                "input_data": step.input_data,
                "duration_ms": step.duration_ms,
            })

            # Mark remaining steps as skipped
            for remaining in workflow.steps[idx + 1:]:
                remaining.status = StepStatus.SKIPPED

            workflow.status = WorkflowStatus.FAILED
            store.save_workflow(workflow)

            # Return the failed workflow — monitor will pick it up
            return workflow

    # All steps succeeded
    workflow.status = WorkflowStatus.SUCCESS
    from datetime import datetime, timezone
    workflow.completed_at = datetime.now(timezone.utc)
    store.save_workflow(workflow)

    await store.broadcast("workflow_completed", {
        "workflow_id": workflow.id,
        "name": workflow.name,
        "status": "success",
    })

    store.update_stats()
    return workflow
