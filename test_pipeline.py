"""End-to-end test of the self-healing pipeline."""
import asyncio
from workflow_engine import run_workflow
from monitor import detect_and_create_incident
from diagnostics import diagnose_incident
from healer import generate_healing_action
from retry_pipeline import retry_workflow
from store import store


async def test():
    print("=== STEP 1: Run workflow with fault ===")
    wf = await run_workflow("order_processing", fault_type="missing_field")
    print(f"Workflow status: {wf.status.value}")
    for s in wf.steps:
        err = s.error or ""
        print(f"  Step: {s.name} -> {s.status.value} {err}")

    print("\n=== STEP 2: Detect incident ===")
    incident = await detect_and_create_incident(wf)
    print(f"Incident: {incident.id} | Error: {incident.error_message}")

    print("\n=== STEP 3: Diagnose ===")
    diag = await diagnose_incident(incident)
    print(f"Root cause: {diag.root_cause}")
    print(f"Category: {diag.category.value} | Confidence: {diag.confidence:.0%}")

    print("\n=== STEP 4: Generate healing action ===")
    action = await generate_healing_action(incident)
    print(f"Action: {action.action_type} | {action.description}")
    print(f"Confidence: {action.confidence:.0%} | Auto-approvable: {action.auto_applicable}")

    print("\n=== STEP 5: Retry ===")
    success = await retry_workflow(incident)
    print(f"Retry success: {success}")
    print(f"Final status: {incident.status.value}")

    print("\n=== SUMMARY ===")
    store.update_stats()
    s = store.stats
    print(f"Workflows: {s.total_workflows_run} | Incidents: {s.total_incidents} | Resolved: {s.total_resolved}")
    print("\n=== ALL FAULT TYPES TEST ===")

    for fault in ["schema_mismatch", "bad_payload", "type_error", "invalid_value"]:
        for wtype in ["order_processing", "data_etl", "user_onboarding"]:
            wf2 = await run_workflow(wtype, fault_type=fault)
            if wf2.status.value == "failed":
                inc2 = await detect_and_create_incident(wf2)
                if inc2:
                    d2 = await diagnose_incident(inc2)
                    a2 = await generate_healing_action(inc2)
                    ok = await retry_workflow(inc2)
                    status = "HEALED" if ok else "FAILED"
                    print(f"  {wtype:20s} + {fault:18s} -> {d2.category.value:18s} -> {status}")

    store.update_stats()
    s = store.stats
    print(f"\nFinal: {s.total_workflows_run} runs | {s.total_incidents} incidents | {s.total_resolved} resolved | {s.total_failed} failed")


asyncio.run(test())
