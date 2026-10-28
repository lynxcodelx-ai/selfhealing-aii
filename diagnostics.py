"""AI-powered root cause diagnostic agent."""

from __future__ import annotations
import json
import re
from typing import Any

import config
from models import Diagnosis, ErrorCategory, Incident, IncidentStatus
from store import store


async def diagnose_incident(incident: Incident) -> Diagnosis:
    """
    Analyze an incident and produce a root-cause diagnosis.
    Uses Gemini API if configured, otherwise falls back to rule-based analysis.
    """
    incident.status = IncidentStatus.DIAGNOSING
    incident.add_timeline_event("Diagnosis Started", "Analyzing error logs and payload data...")
    store.save_incident(incident)
    await store.broadcast("incident_updated", {
        "incident_id": incident.id,
        "status": "diagnosing",
    })

    if config.AI_PROVIDER == "gemini" and config.GEMINI_API_KEY:
        diagnosis = await _diagnose_with_gemini(incident)
    else:
        diagnosis = _diagnose_rule_based(incident)

    incident.diagnosis = diagnosis
    incident.status = IncidentStatus.DIAGNOSED
    incident.add_timeline_event(
        "Diagnosis Complete",
        f"Root cause: {diagnosis.root_cause} (confidence: {diagnosis.confidence:.0%})"
    )
    store.save_incident(incident)

    await store.broadcast("incident_diagnosed", {
        "incident_id": incident.id,
        "diagnosis": diagnosis.model_dump(),
        "status": "diagnosed",
    })

    return diagnosis


def _diagnose_rule_based(incident: Incident) -> Diagnosis:
    """Rule-based diagnosis engine — works without an API key."""
    error_msg = incident.error_message.lower()
    input_data = incident.raw_input

    # ── Missing Field Detection ──
    if "missing" in error_msg:
        # Extract field names from error message
        match = re.search(r"missing.*?(?:fields?|columns?)[:\s]*\[?([^\]]+)\]?", error_msg, re.I)
        fields = match.group(1).strip() if match else "unknown"
        # Try to find what the field was renamed to
        return Diagnosis(
            root_cause=f"Required field(s) missing from input payload: {fields}",
            category=ErrorCategory.MISSING_FIELD,
            confidence=0.95,
            explanation=(
                f"The workflow step '{incident.failed_step}' expected certain required fields "
                f"that were not present in the input data. This commonly occurs when upstream "
                f"systems change their API response format, or when data is partially loaded. "
                f"Missing fields: {fields}."
            ),
            affected_field=fields.split(",")[0].strip().strip("'\""),
            suggested_action="Add the missing field(s) with appropriate default values or restore from the expected schema.",
        )

    # ── Schema Mismatch Detection ──
    if "schema" in error_msg or "validation failed" in error_msg:
        return Diagnosis(
            root_cause="Data schema does not match the expected structure",
            category=ErrorCategory.SCHEMA_MISMATCH,
            confidence=0.90,
            explanation=(
                f"The input data at step '{incident.failed_step}' failed schema validation. "
                f"This suggests the upstream data source has changed its schema (e.g., field "
                f"renames, type changes, or structural modifications). Error: {incident.error_message}"
            ),
            affected_field=_guess_affected_field_from_error(incident.error_message),
            suggested_action="Transform the input payload to match the expected schema by renaming or restructuring fields.",
        )

    # ── Type Error Detection ──
    if "type" in error_msg or "must be" in error_msg:
        field = _guess_affected_field_from_error(incident.error_message)
        return Diagnosis(
            root_cause=f"Type mismatch in input data — expected a different data type",
            category=ErrorCategory.TYPE_ERROR,
            confidence=0.92,
            explanation=(
                f"Step '{incident.failed_step}' received data with an incorrect type. "
                f"{incident.error_message}. This typically happens when data serialization "
                f"converts numbers to strings or vice versa, or when API responses change format."
            ),
            affected_field=field,
            suggested_action="Cast or convert the affected field to the correct data type.",
        )

    # ── Invalid Value Detection ──
    if "invalid" in error_msg or "positive" in error_msg or "empty" in error_msg:
        return Diagnosis(
            root_cause="Input data contains invalid or out-of-range values",
            category=ErrorCategory.BAD_PAYLOAD,
            confidence=0.88,
            explanation=(
                f"Step '{incident.failed_step}' rejected the input data due to invalid values. "
                f"Error: {incident.error_message}. The data may have been corrupted, contain "
                f"edge cases, or have failed business rule validation."
            ),
            affected_field=_guess_affected_field_from_error(incident.error_message),
            suggested_action="Replace invalid values with valid defaults or corrected data.",
        )

    # ── Timeout Detection ──
    if "timeout" in error_msg or "timed out" in error_msg:
        return Diagnosis(
            root_cause="Operation timed out waiting for a response",
            category=ErrorCategory.TIMEOUT,
            confidence=0.85,
            explanation=(
                f"Step '{incident.failed_step}' did not complete within the expected timeframe. "
                f"This could be due to network issues, high server load, or the target service being slow."
            ),
            suggested_action="Retry with exponential backoff or increase timeout threshold.",
        )

    # ── Rate Limit Detection ──
    if "rate limit" in error_msg or "429" in error_msg:
        return Diagnosis(
            root_cause="API rate limit exceeded",
            category=ErrorCategory.RATE_LIMIT,
            confidence=0.95,
            explanation=(
                f"Step '{incident.failed_step}' hit the API rate limit. Too many requests were "
                f"sent in a short period. The system needs to implement backoff and retry."
            ),
            suggested_action="Retry after a delay with exponential backoff.",
        )

    # ── Fallback ──
    return Diagnosis(
        root_cause=f"Unexpected error in '{incident.failed_step}'",
        category=ErrorCategory.UNKNOWN,
        confidence=0.60,
        explanation=(
            f"The step '{incident.failed_step}' failed with: {incident.error_message}. "
            f"The error doesn't match known patterns. Manual investigation may be needed."
        ),
        suggested_action="Review the error details and input data for anomalies.",
    )


def _guess_affected_field_from_error(error_message: str) -> str | None:
    """Try to extract a field name from the error message."""
    # Look for quoted field names
    match = re.search(r"['\"](\w+)['\"]", error_message)
    if match:
        return match.group(1)
    # Look for field-like patterns
    match = re.search(r"field\s+(\w+)", error_message, re.I)
    if match:
        return match.group(1)
    return None


async def _diagnose_with_gemini(incident: Incident) -> Diagnosis:
    """Use Gemini API for AI-powered diagnosis."""
    try:
        import google.generativeai as genai

        genai.configure(api_key=config.GEMINI_API_KEY)
        model = genai.GenerativeModel(config.GEMINI_MODEL)

        prompt = f"""You are an AI diagnostic agent for automated workflows.
Analyze this workflow failure and provide a root-cause diagnosis.

WORKFLOW: {incident.workflow_name}
FAILED STEP: {incident.failed_step}
ERROR TYPE: {incident.error_type}
ERROR MESSAGE: {incident.error_message}
INPUT DATA: {json.dumps(incident.raw_input, indent=2, default=str)}

Respond in this exact JSON format:
{{
    "root_cause": "Clear description of what went wrong",
    "category": "one of: schema_mismatch, rate_limit, bad_payload, timeout, missing_field, auth_failure, service_down, type_error, unknown",
    "confidence": 0.0 to 1.0,
    "explanation": "Detailed explanation for the operator",
    "affected_field": "field name or null",
    "suggested_action": "What to do to fix this"
}}

Return ONLY valid JSON, no markdown or extra text."""

        response = await model.generate_content_async(prompt)
        text = response.text.strip()
        # Clean up potential markdown wrapping
        if text.startswith("```"):
            text = re.sub(r"```\w*\n?", "", text).strip()
        data = json.loads(text)

        return Diagnosis(
            root_cause=data.get("root_cause", "Unknown"),
            category=ErrorCategory(data.get("category", "unknown")),
            confidence=float(data.get("confidence", 0.7)),
            explanation=data.get("explanation", ""),
            affected_field=data.get("affected_field"),
            suggested_action=data.get("suggested_action", ""),
        )

    except Exception as e:
        # Fallback to rule-based if Gemini fails
        print(f"[WARN] Gemini diagnosis failed ({e}), falling back to rule-based")
        return _diagnose_rule_based(incident)
