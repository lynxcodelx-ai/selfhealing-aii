"""Healing Synthesizer — generates corrective actions and payload patches."""

from __future__ import annotations
import copy
import json
import re
from typing import Any

import config
from models import (
    Diagnosis, ErrorCategory, HealingAction, Incident, IncidentStatus
)
from store import store


async def generate_healing_action(incident: Incident) -> HealingAction:
    """
    Generate a corrective action based on the incident diagnosis.
    Uses Gemini if available, otherwise rule-based synthesis.
    """
    if not incident.diagnosis:
        raise ValueError("Cannot heal without a diagnosis")

    incident.status = IncidentStatus.HEALING
    incident.add_timeline_event("Healing Started", "Synthesizing corrective action...")
    store.save_incident(incident)
    await store.broadcast("incident_updated", {
        "incident_id": incident.id,
        "status": "healing",
    })

    if config.AI_PROVIDER == "gemini" and config.GEMINI_API_KEY:
        action = await _heal_with_gemini(incident)
    else:
        action = _heal_rule_based(incident)

    incident.healing_action = action

    # Decide if auto-approvable
    if action.confidence >= config.AUTO_APPROVE_CONFIDENCE_THRESHOLD:
        action.auto_applicable = True
        incident.add_timeline_event(
            "Auto-Approval Eligible",
            f"Fix confidence ({action.confidence:.0%}) meets threshold "
            f"({config.AUTO_APPROVE_CONFIDENCE_THRESHOLD:.0%})"
        )
    else:
        incident.status = IncidentStatus.AWAITING_APPROVAL
        incident.add_timeline_event(
            "Awaiting Human Approval",
            f"Fix confidence ({action.confidence:.0%}) below auto-approve threshold. "
            f"Human review required."
        )

    store.save_incident(incident)

    await store.broadcast("healing_proposed", {
        "incident_id": incident.id,
        "action": action.model_dump(),
        "status": incident.status.value,
        "auto_applicable": action.auto_applicable,
    })

    return action


def _heal_rule_based(incident: Incident) -> HealingAction:
    """Generate corrective action using rule-based logic."""
    diagnosis = incident.diagnosis
    original = copy.deepcopy(incident.raw_input)
    patched = copy.deepcopy(original)
    category = diagnosis.category

    # ── Missing Field Healing ──
    if category == ErrorCategory.MISSING_FIELD:
        return _heal_missing_field(incident, original, patched)

    # ── Schema Mismatch Healing ──
    if category == ErrorCategory.SCHEMA_MISMATCH:
        return _heal_schema_mismatch(incident, original, patched)

    # ── Type Error Healing ──
    if category == ErrorCategory.TYPE_ERROR:
        return _heal_type_error(incident, original, patched)

    # ── Bad Payload Healing ──
    if category == ErrorCategory.BAD_PAYLOAD:
        return _heal_bad_payload(incident, original, patched)

    # ── Timeout / Rate Limit — retry strategy ──
    if category in (ErrorCategory.TIMEOUT, ErrorCategory.RATE_LIMIT):
        return HealingAction(
            action_type="retry_with_backoff",
            description=f"Retry the operation with exponential backoff (category: {category.value})",
            original_payload=original,
            patched_payload=original,  # No payload change needed
            confidence=0.85,
        )

    # ── Fallback: try comprehensive repair ──
    # Apply all repair strategies as a last resort
    action = _heal_comprehensive(incident, original, patched)
    if action:
        return action

    return HealingAction(
        action_type="manual_review",
        description=f"Unable to auto-generate fix for {category.value}. Manual review recommended.",
        original_payload=original,
        patched_payload=original,
        confidence=0.30,
    )


def _heal_comprehensive(incident: Incident, original: dict, patched: dict) -> HealingAction | None:
    """Apply all repair strategies broadly when category-specific fix isn't enough."""
    patch = {}

    # Fix all known schema renames
    known_renames = {
        "totalAmt": "total_amount", "custId": "customer_id", "line_items": "items",
        "sourceEndpoint": "source_url", "dest_table": "target_table",
        "requiredColumns": "expected_fields", "user_name": "username",
        "email_address": "email", "passwd": "password",
    }
    for wrong, correct in known_renames.items():
        if wrong in patched and correct not in patched:
            patched[correct] = patched.pop(wrong)
            patch[correct] = patched[correct]

    # Fix type issues
    if "total_amount" in patched and not isinstance(patched["total_amount"], (int, float)):
        try:
            patched["total_amount"] = float(str(patched["total_amount"]).replace(",", ""))
        except (ValueError, TypeError):
            patched["total_amount"] = 9.99
        patch["total_amount"] = patched["total_amount"]

    if "total_amount" in patched and isinstance(patched["total_amount"], (int, float)) and patched["total_amount"] <= 0:
        patched["total_amount"] = abs(patched["total_amount"]) or 9.99
        patch["total_amount"] = patched["total_amount"]

    if "items" in patched and not isinstance(patched["items"], list):
        patched["items"] = [{"sku": "RECOVERED", "quantity": 1, "price": 9.99}]
        patch["items"] = patched["items"]

    if "items" in patched and isinstance(patched["items"], list) and len(patched["items"]) == 0:
        patched["items"] = [{"sku": "PLACEHOLDER", "quantity": 1, "price": 9.99}]
        patch["items"] = patched["items"]

    if "email" in patched and (patched["email"] is None or "@" not in str(patched["email"])):
        patched["email"] = "recovered@example.com"
        patch["email"] = patched["email"]

    if "source_url" in patched and not patched["source_url"]:
        patched["source_url"] = "https://api.fallback.example.com/data"
        patch["source_url"] = patched["source_url"]

    for key in ["password", "username"]:
        if key not in patched or not patched.get(key):
            patched[key] = f"recovered_{key}"
            patch[key] = patched[key]

    # Fix record_sample
    if "record_sample" in patched and "expected_fields" in patched:
        sample = patched["record_sample"]
        expected = patched["expected_fields"]
        for field in expected:
            if field not in sample:
                defaults = {"id": 1, "name": "recovered", "value": 0, "timestamp": "2026-01-01"}
                sample[field] = defaults.get(field, f"<auto:{field}>")
                patch.setdefault("record_sample", {})
                patch["record_sample"][field] = sample[field]
        patched["record_sample"] = sample

    # Fix None values
    for key, val in list(patched.items()):
        if val is None and key not in patch:
            defaults = {"email": "recovered@example.com", "username": "recovered_user",
                        "password": "temp_P@ss123", "source_url": "https://fallback.example.com",
                        "customer_id": "CUST-RECOVERED", "target_table": "default.recovered"}
            if key in defaults:
                patched[key] = defaults[key]
                patch[key] = patched[key]

    if patch:
        return HealingAction(
            action_type="payload_patch",
            description=f"Comprehensive repair applied: {list(patch.keys())}",
            payload_patch=patch,
            original_payload=original,
            patched_payload=patched,
            confidence=0.80,
        )
    return None


def _heal_missing_field(incident: Incident, original: dict, patched: dict) -> HealingAction:
    """Restore missing fields with appropriate defaults."""
    error_msg = incident.error_message
    # Find which fields are missing
    match = re.search(r"\[([^\]]+)\]", error_msg)
    missing_fields = []
    if match:
        raw = match.group(1)
        missing_fields = [f.strip().strip("'\"") for f in raw.split(",")]

    # Check if this is a schema validation error (fields missing from record_sample)
    if "schema validation" in error_msg.lower() or incident.failed_step.lower() in ("validate schema",):
        # The missing fields are from record_sample, not top-level
        if "record_sample" in patched:
            sample = patched["record_sample"]
            patch = {}
            defaults = {"id": 1, "name": "recovered", "value": 0, "timestamp": "2026-01-01T00:00:00Z"}
            for field in missing_fields:
                sample[field] = defaults.get(field, f"<auto:{field}>")
            patched["record_sample"] = sample
            patch["record_sample"] = sample
            return HealingAction(
                action_type="payload_patch",
                description=f"Fixed record_sample: added missing fields {missing_fields}",
                payload_patch=patch,
                original_payload=original,
                patched_payload=patched,
                confidence=0.92,
            )

    # Default values for known fields
    defaults = {
        "customer_id": "CUST-DEFAULT-001",
        "items": [{"sku": "DEFAULT-ITEM", "quantity": 1, "price": 9.99}],
        "total_amount": 9.99,
        "source_url": "https://api.fallback.example.com/data",
        "target_schema": {"format": "json", "version": "1.0"},
        "target_table": "default.fallback_table",
        "email": "fallback@example.com",
        "username": "default_user",
        "password": "temp_password_change_me",
        "expected_fields": [],
    }

    patch = {}
    for field in missing_fields:
        if field in defaults:
            patched[field] = defaults[field]
            patch[field] = defaults[field]
        else:
            patched[field] = f"<auto-filled:{field}>"
            patch[field] = f"<auto-filled:{field}>"

    return HealingAction(
        action_type="payload_patch",
        description=f"Added missing field(s): {', '.join(missing_fields)} with default values",
        payload_patch=patch,
        original_payload=original,
        patched_payload=patched,
        confidence=0.92,
    )


def _heal_schema_mismatch(incident: Incident, original: dict, patched: dict) -> HealingAction:
    """Fix schema mismatches by renaming fields back to expected names."""
    # Known field mappings (wrong → correct)
    known_renames = {
        "totalAmt": "total_amount",
        "custId": "customer_id",
        "line_items": "items",
        "sourceEndpoint": "source_url",
        "dest_table": "target_table",
        "requiredColumns": "expected_fields",
        "user_name": "username",
        "email_address": "email",
        "passwd": "password",
    }

    patch = {}
    for wrong_name, correct_name in known_renames.items():
        if wrong_name in patched and correct_name not in patched:
            patched[correct_name] = patched.pop(wrong_name)
            patch[correct_name] = patched[correct_name]

    if not patch:
        # Try analyzing which fields are extra (possibly renamed)
        error_msg = incident.error_message
        match = re.search(r"missing.*?[:\s]+\[?([^\]]+)\]?", error_msg, re.I)
        if match:
            missing = [f.strip().strip("'\"") for f in match.group(1).split(",")]
            for field in missing:
                # Look for similar keys in the payload
                for key in list(patched.keys()):
                    if field.lower() in key.lower() or key.lower() in field.lower():
                        patched[field] = patched.pop(key)
                        patch[field] = patched[field]
                        break

    return HealingAction(
        action_type="schema_transform",
        description=f"Renamed mismatched fields to expected schema: {patch}",
        payload_patch=patch,
        original_payload=original,
        patched_payload=patched,
        confidence=0.88,
    )


def _heal_type_error(incident: Incident, original: dict, patched: dict) -> HealingAction:
    """Fix type mismatches by casting values to expected types."""
    error_msg = incident.error_message
    patch = {}

    # Detect and fix common type issues
    if "total_amount" in error_msg or "numeric" in error_msg or "total_amount" in str(patched.get("total_amount", "")):
        if "total_amount" in patched and not isinstance(patched["total_amount"], (int, float)):
            try:
                patched["total_amount"] = float(str(patched["total_amount"]).replace(",", ""))
            except (ValueError, TypeError):
                patched["total_amount"] = 0.01
            patch["total_amount"] = patched["total_amount"]

    if "items" in error_msg and "list" in error_msg:
        if "items" in patched and not isinstance(patched["items"], list):
            patched["items"] = [{"sku": "RECOVERED-ITEM", "quantity": 1, "price": 0.0}]
            patch["items"] = patched["items"]

    # Fix None email or invalid email
    if "email" in patched and (patched["email"] is None or (isinstance(patched["email"], str) and "@" not in patched["email"])):
        username = patched.get("username", "user")
        patched["email"] = f"{username}@recovered.example.com"
        patch["email"] = patched["email"]

    # Fix non-string username (e.g. int)
    if "username" in patched and not isinstance(patched["username"], str):
        patched["username"] = str(patched["username"])
        patch["username"] = patched["username"]

    # Fix non-string values that should be strings
    string_fields = ["username", "email", "password", "order_id", "customer_id"]
    for field in string_fields:
        if field in patched and patched[field] is not None and not isinstance(patched[field], str):
            patched[field] = str(patched[field])
            if field not in patch:
                patch[field] = patched[field]

    # Fix empty items list
    if "items" in patched and isinstance(patched["items"], list) and len(patched["items"]) == 0:
        patched["items"] = [{"sku": "RECOVERED-ITEM", "quantity": 1, "price": 9.99}]
        patch["items"] = patched["items"]

    # Fix negative / zero total_amount
    if "total_amount" in patched and isinstance(patched["total_amount"], (int, float)) and patched["total_amount"] <= 0:
        patched["total_amount"] = abs(patched["total_amount"]) or 9.99
        patch["total_amount"] = patched["total_amount"]

    # Fix None/invalid values generically
    for key, val in list(patched.items()):
        if val is None and key not in patch:
            defaults = {
                "email": "recovered@example.com",
                "username": "recovered_user",
                "password": "temp_P@ss123",
                "source_url": "https://api.fallback.example.com/data",
            }
            if key in defaults:
                patched[key] = defaults[key]
                patch[key] = patched[key]

    # Generic: try to detect the problematic field
    if not patch and incident.diagnosis and incident.diagnosis.affected_field:
        field = incident.diagnosis.affected_field
        if field in patched:
            val = patched[field]
            if isinstance(val, str):
                try:
                    patched[field] = float(val)
                    patch[field] = patched[field]
                except ValueError:
                    pass

    return HealingAction(
        action_type="payload_patch",
        description=f"Fixed type mismatch(es): {list(patch.keys())}",
        payload_patch=patch,
        original_payload=original,
        patched_payload=patched,
        confidence=0.90,
    )


def _heal_bad_payload(incident: Incident, original: dict, patched: dict) -> HealingAction:
    """Fix corrupted or invalid payload data."""
    error_msg = incident.error_message
    patch = {}

    # Fix items being wrong type
    if "items" in patched and not isinstance(patched["items"], list):
        patched["items"] = [{"sku": "RECOVERED-ITEM", "quantity": 1, "price": 29.99}]
        patch["items"] = patched["items"]

    # Fix empty items
    if "items" in patched and isinstance(patched["items"], list) and len(patched["items"]) == 0:
        patched["items"] = [{"sku": "PLACEHOLDER-ITEM", "quantity": 1, "price": 9.99}]
        patch["items"] = patched["items"]

    # Fix negative or zero amounts
    if "total_amount" in patched and isinstance(patched["total_amount"], (int, float)):
        if patched["total_amount"] <= 0:
            patched["total_amount"] = abs(patched["total_amount"]) or 9.99
            patch["total_amount"] = patched["total_amount"]

    # Fix non-numeric total_amount
    if "total_amount" in patched and not isinstance(patched["total_amount"], (int, float)):
        try:
            patched["total_amount"] = float(patched["total_amount"])
        except (ValueError, TypeError):
            patched["total_amount"] = 9.99
        patch["total_amount"] = patched["total_amount"]

    # Fix invalid email
    if "email" in patched:
        email_val = patched.get("email")
        if email_val is None or (isinstance(email_val, str) and "@" not in email_val):
            username = patched.get("username", "user")
            patched["email"] = f"{username}@recovered.example.com"
            patch["email"] = patched["email"]

    # Fix missing schema validation fields in record_sample
    if "record_sample" in patched and "expected_fields" in patched:
        sample = patched["record_sample"]
        expected = patched["expected_fields"]
        for field in expected:
            if field not in sample:
                defaults = {"id": 1, "name": "recovered", "value": 0, "timestamp": "2026-01-01T00:00:00Z"}
                sample[field] = defaults.get(field, f"<auto:{field}>")
                patch.setdefault("record_sample", {})
                patch["record_sample"][field] = sample[field]
        patched["record_sample"] = sample

    # Fix empty source_url
    if "source_url" in patched and not patched["source_url"]:
        patched["source_url"] = "https://api.fallback.example.com/data"
        patch["source_url"] = patched["source_url"]

    # Fix missing password
    if "password" not in patched or not patched.get("password"):
        patched["password"] = "temp_secure_P@ss1"
        patch["password"] = patched["password"]

    # Fix None values in common fields
    for key in list(patched.keys()):
        if patched[key] is None and key not in patch:
            defaults = {
                "email": "recovered@example.com",
                "username": "recovered_user",
                "password": "temp_P@ss123",
                "source_url": "https://api.fallback.example.com/data",
                "customer_id": "CUST-RECOVERED",
                "target_table": "default.recovered_table",
            }
            if key in defaults:
                patched[key] = defaults[key]
                patch[key] = patched[key]

    return HealingAction(
        action_type="payload_patch",
        description=f"Repaired corrupted payload data: {list(patch.keys())}",
        payload_patch=patch,
        original_payload=original,
        patched_payload=patched,
        confidence=0.85,
    )


async def _heal_with_gemini(incident: Incident) -> HealingAction:
    """Use Gemini to generate a corrective action."""
    try:
        import google.generativeai as genai

        genai.configure(api_key=config.GEMINI_API_KEY)
        model = genai.GenerativeModel(config.GEMINI_MODEL)

        prompt = f"""You are an AI healing agent that generates corrective actions for failed workflows.

INCIDENT DETAILS:
- Workflow: {incident.workflow_name}
- Failed Step: {incident.failed_step}
- Error: {incident.error_message}
- Root Cause: {incident.diagnosis.root_cause if incident.diagnosis else 'Unknown'}
- Category: {incident.diagnosis.category.value if incident.diagnosis else 'unknown'}
- Input Data: {json.dumps(incident.raw_input, indent=2, default=str)}

Generate a corrective action. Respond in this exact JSON format:
{{
    "action_type": "payload_patch or schema_transform or retry_with_backoff",
    "description": "Human-readable description of the fix",
    "patched_payload": {{ ... the corrected full payload ... }},
    "confidence": 0.0 to 1.0
}}

Return ONLY valid JSON, no markdown."""

        response = await model.generate_content_async(prompt)
        text = response.text.strip()
        if text.startswith("```"):
            text = re.sub(r"```\w*\n?", "", text).strip()
        data = json.loads(text)

        return HealingAction(
            action_type=data.get("action_type", "payload_patch"),
            description=data.get("description", "AI-generated fix"),
            original_payload=incident.raw_input,
            patched_payload=data.get("patched_payload", incident.raw_input),
            confidence=float(data.get("confidence", 0.7)),
        )

    except Exception as e:
        print(f"[WARN] Gemini healing failed ({e}), falling back to rule-based")
        return _heal_rule_based(incident)
