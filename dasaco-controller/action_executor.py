#!/usr/bin/env python3
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

DECISION_LOG = Path("logs/localizer-decisions.jsonl")
ACTION_LOG = Path("logs/action-plans.jsonl")
NAMESPACE = "free5gc"
AMF_DEPLOYMENT = "free5gc-free5gc-amf-amf"
AMF_MAX_REPLICAS = 5
DRY_RUN = True

def run_command(args):
    result = subprocess.run(args, text=True, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    return result.stdout.strip()

def read_latest_decision():
    lines = DECISION_LOG.read_text().splitlines()
    lines = [line for line in lines if line.strip()]
    if not lines:
        raise RuntimeError("Decision log is empty")
    return json.loads(lines[-1])

def current_amf_replicas():
    value = run_command([
        "kubectl", "get", "deployment", AMF_DEPLOYMENT,
        "-n", NAMESPACE,
        "-o", "jsonpath={.spec.replicas}",
    ])
    return int(value)

def create_plan(record):
    decision = record["decision"]
    current = current_amf_replicas()
    plan = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "DRY_RUN" if DRY_RUN else "ACTIVE",
        "source_timestamp": record["timestamp"],
        "source_state": decision["state"],
        "source_action": decision["recommended_action"],
        "persistent": decision.get("persistent", False),
        "current_amf_replicas": current,
        "proposed_amf_replicas": current,
        "action": "HOLD",
        "executed": False,
        "reason": "No safe action candidate",
    }
    candidate = (
        decision["state"] == "AMF_PRESSURE"
        and decision["recommended_action"] == "SCALE_AMF_CANDIDATE"
        and decision.get("persistent") is True
    )
    if candidate:
        if current >= AMF_MAX_REPLICAS:
            plan["reason"] = "AMF maximum replica limit reached"
        else:
            plan["action"] = "SCALE_AMF"
            plan["proposed_amf_replicas"] = current + 1
            plan["reason"] = "Persistent AMF pressure passed safety guards"
            if DRY_RUN:
                plan["reason"] += "; execution blocked by DRY_RUN"
    return plan

def main():
    plan = create_plan(read_latest_decision())
    ACTION_LOG.parent.mkdir(exist_ok=True)
    with ACTION_LOG.open("a") as file:
        file.write(json.dumps(plan) + "\n")
    print(json.dumps(plan, indent=2))

if __name__ == "__main__":
    main()
