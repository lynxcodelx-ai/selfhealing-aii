"""Fault injection module — introduces realistic failures into workflows."""

from __future__ import annotations
import copy
import random
from typing import Any


def inject_fault(fault_type: str, payload: dict[str, Any], workflow_type: str) -> dict[str, Any]:
    """Inject a specific fault into the workflow payload."""
    injectors = {
        "missing_field": _inject_missing_field,
        "schema_mismatch": _inject_schema_mismatch,
        "bad_payload": _inject_bad_payload,
        "type_error": _inject_type_error,
        "invalid_value": _inject_invalid_value,
    }

    injector = injectors.get(fault_type)
    if not injector:
        raise ValueError(
            f"Unknown fault type: {fault_type}. "
            f"Available: {list(injectors.keys())}"
        )

    corrupted = copy.deepcopy(payload)
    return injector(corrupted, workflow_type)


def _inject_missing_field(payload: dict, workflow_type: str) -> dict:
    """Remove a required field from the payload."""
    removable = {
        "order_processing": ["customer_id", "items", "total_amount"],
        "data_etl": ["source_url", "target_schema", "target_table"],
        "user_onboarding": ["email", "username", "password"],
    }
    fields = removable.get(workflow_type, list(payload.keys()))
    if fields:
        field = random.choice(fields)
        payload.pop(field, None)
    return payload


def _inject_schema_mismatch(payload: dict, workflow_type: str) -> dict:
    """Rename fields to simulate schema changes (e.g., API version mismatch)."""
    renames = {
        "order_processing": {"total_amount": "totalAmt", "customer_id": "custId", "items": "line_items"},
        "data_etl": {"source_url": "sourceEndpoint", "target_table": "dest_table", "expected_fields": "requiredColumns"},
        "user_onboarding": {"username": "user_name", "email": "email_address", "password": "passwd"},
    }
    mapping = renames.get(workflow_type, {})
    if mapping:
        # Pick one rename to apply
        old_key, new_key = random.choice(list(mapping.items()))
        if old_key in payload:
            payload[new_key] = payload.pop(old_key)
    return payload


def _inject_bad_payload(payload: dict, workflow_type: str) -> dict:
    """Corrupt the payload data to simulate data quality issues."""
    if workflow_type == "order_processing":
        if "items" in payload:
            payload["items"] = "not-a-list"  # Should be a list
    elif workflow_type == "data_etl":
        if "record_sample" in payload:
            # Remove fields that are expected during validation
            payload["record_sample"] = {"id": 1}  # Missing name, value, timestamp
    elif workflow_type == "user_onboarding":
        if "email" in payload:
            payload["email"] = "invalid-email-format"  # No @ symbol
    return payload


def _inject_type_error(payload: dict, workflow_type: str) -> dict:
    """Change field types to cause type errors."""
    if workflow_type == "order_processing":
        payload["total_amount"] = "one-hundred"  # Should be numeric
    elif workflow_type == "data_etl":
        payload["record_count"] = "many"  # Should be int
    elif workflow_type == "user_onboarding":
        payload["username"] = 12345  # Should be string (still works but demonstrates)
        payload["email"] = None  # Will fail @ check
    return payload


def _inject_invalid_value(payload: dict, workflow_type: str) -> dict:
    """Set fields to invalid/edge-case values."""
    if workflow_type == "order_processing":
        payload["total_amount"] = -50.00  # Negative amount
        payload["items"] = []  # Empty items list
    elif workflow_type == "data_etl":
        payload["source_url"] = ""  # Empty source
    elif workflow_type == "user_onboarding":
        payload["password"] = ""  # Empty password (missing)
        payload.pop("password", None)
    return payload


# ── Available Faults Registry ──

AVAILABLE_FAULTS = {
    "missing_field": {
        "name": "Missing Field",
        "description": "Removes a required field from the payload",
        "icon": "🗑️",
    },
    "schema_mismatch": {
        "name": "Schema Mismatch",
        "description": "Renames fields to simulate API version changes",
        "icon": "🔀",
    },
    "bad_payload": {
        "name": "Bad Payload",
        "description": "Corrupts data types or structure",
        "icon": "💥",
    },
    "type_error": {
        "name": "Type Error",
        "description": "Changes field types (string→number, etc.)",
        "icon": "🔤",
    },
    "invalid_value": {
        "name": "Invalid Value",
        "description": "Sets fields to invalid/edge-case values",
        "icon": "⚠️",
    },
}
