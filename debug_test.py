"""Debug the remaining failing cases."""
import asyncio
import json
from workflow_engine import run_workflow
from monitor import detect_and_create_incident
from diagnostics import diagnose_incident
from healer import generate_healing_action
from retry_pipeline import retry_workflow
from store import store

async def debug():
    failing = [
        ("data_etl", "bad_payload"),
        ("user_onboarding", "type_error"),
        ("order_processing", "invalid_value"),
    ]
    for wtype, fault in failing:
        print(f"\n{'='*60}")
        print(f"DEBUG: {wtype} + {fault}")
        print(f"{'='*60}")
        wf = await run_workflow(wtype, fault_type=fault)
        if wf.status.value != "failed":
            print("  DID NOT FAIL")
            continue
        inc = await detect_and_create_incident(wf)
        if not inc:
            print("  NO INCIDENT")
            continue
        print(f"  Error: {inc.error_message}")
        print(f"  Input keys: {list(inc.raw_input.keys())}")
        diag = await diagnose_incident(inc)
        print(f"  Diagnosis: {diag.category.value} - {diag.root_cause}")
        action = await generate_healing_action(inc)
        print(f"  Action: {action.action_type} - {action.description}")
        print(f"  Patch: {json.dumps(action.payload_patch, indent=2)}")
        print(f"  Patched payload: {json.dumps(action.patched_payload, indent=2, default=str)[:500]}")
        ok = await retry_workflow(inc)
        print(f"  Result: {'HEALED' if ok else 'FAILED'}")
        if not ok:
            # Check what the retry workflow looked like
            for w in store.list_workflows():
                for s in w.steps:
                    if s.status.value == "failed":
                        print(f"  Retry fail at: {s.name} -> {s.error}")
                        print(f"  Retry input: {json.dumps(s.input_data, indent=2, default=str)[:400]}")

asyncio.run(debug())
