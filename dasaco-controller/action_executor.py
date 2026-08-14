#!/usr/bin/env python3
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

DECISION_LOG = Path("logs/localizer-decisions.jsonl")
ACTION_LOG = Path("logs/action-plans.jsonl")
STATE_FILE = Path("logs/controller-state.json")
ACTION_STATE_LOG = Path("logs/controller-actions.jsonl")
NAMESPACE = "free5gc"
AMF_DEPLOYMENT = "free5gc-free5gc-amf-amf"
AMF_MAX_REPLICAS = 5
DRY_RUN = os.getenv("DASACO_ACTIVE", "0") != "1"

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

def default_state():
    return {
        "phase": "IDLE",
        "action": None,
        "target_replicas": None,
        "started_at": None,
        "cooldown_until": None,
        "last_error": None,
    }


def read_state():
    if not STATE_FILE.exists():
        return default_state()

    try:
        state = json.loads(STATE_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {
            **default_state(),
            "phase": "FAILED",
            "last_error": "Controller state file is unreadable",
        }

    return {
        **default_state(),
        **state,
    }


def write_state(state):
    STATE_FILE.parent.mkdir(exist_ok=True)
    temporary = STATE_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2) + "\n")
    temporary.replace(STATE_FILE)


def append_action_event(event):
    ACTION_STATE_LOG.parent.mkdir(exist_ok=True)
    with ACTION_STATE_LOG.open("a") as file:
        file.write(json.dumps(event) + "\n")


def create_plan(record):
    decision = record["decision"]
    state = read_state()
    current = current_amf_replicas()
    plan = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "DRY_RUN" if DRY_RUN else "ACTIVE",
        "source_timestamp": record["timestamp"],
        "source_state": decision["state"],
        "source_action": decision["recommended_action"],
        "persistent": decision.get("persistent", False),
        "controller_phase": state["phase"],
        "current_amf_replicas": current,
        "proposed_amf_replicas": current,
        "action": "HOLD",
        "executed": False,
        "reason": "No safe action candidate",
    }
    if state["phase"] != "IDLE":
        plan["reason"] = (
            "Controller action is already pending: "
            + state["phase"]
        )
        return plan

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
