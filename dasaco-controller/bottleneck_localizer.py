#!/usr/bin/env python3

import json
from pathlib import Path

LOG_FILE = Path("logs/monitoring.jsonl")

CPU_REQUESTS = {
    "amf": 100,
    "ausf": 100,
    "udm": 100,
    "udr": 100,
    "mongodb": 500,
}

HIGH_THRESHOLD = {
    "amf": 70,
    "ausf": 75,
    "udm": 75,
    "udr": 75,
    "mongodb": 75,
}


def load_recent(count=2):
    if not LOG_FILE.exists():
        raise SystemExit("Monitoring log does not exist")

    lines = [
        line
        for line in LOG_FILE.read_text().splitlines()
        if line.strip()
    ]

    if len(lines) < count:
        raise SystemExit(
            f"Need {count} snapshots, found {len(lines)}"
        )

    return [
        json.loads(line)
        for line in lines[-count:]
    ]


def cpu_percent(name, data):
    request = CPU_REQUESTS[name]
    return 100 * data.get("cpu_m", 0) / request


def classify(snapshot):
    admission = snapshot.get("admission", {})
    if admission.get("mode") == "UNAVAILABLE":
        return {
            "state": "UNSAFE_OR_UNCERTAIN",
            "reason": "Admission control evidence is unavailable",
            "functions": ["open5glos"],
            "recommended_action": "HOLD",
        }

    functions = snapshot["functions"]
    unhealthy = []
    pressured = []

    for name, data in functions.items():
        if "error" in data:
            unhealthy.append(name)
            continue

        if data["ready"] < data["desired"]:
            unhealthy.append(name)
            continue

        utilization = cpu_percent(name, data)

        if utilization >= HIGH_THRESHOLD[name]:
            pressured.append(name)

    if unhealthy:
        return {
            "state": "UNSAFE_OR_UNCERTAIN",
            "reason": "Unhealthy or incomplete workload evidence",
            "functions": unhealthy,
            "recommended_action": "HOLD",
        }

    if "mongodb" in pressured:
        return {
            "state": "DOWNSTREAM_PRESSURE",
            "reason": "MongoDB pressure requires path protection",
            "functions": pressured,
            "recommended_action": "PROTECT_WITH_ADMISSION",
        }

    downstream = [
        name
        for name in pressured
        if name in {"ausf", "udm", "udr"}
    ]

    if downstream:
        return {
            "state": "DOWNSTREAM_PRESSURE",
            "reason": "Downstream registration dependency pressure",
            "functions": downstream,
            "recommended_action": "COLLECT_MORE_EVIDENCE",
        }

    if "amf" in pressured:
        return {
            "state": "AMF_PRESSURE",
            "reason": "AMF CPU pressure detected",
            "functions": ["amf"],
            "recommended_action": "SCALE_AMF_CANDIDATE",
        }

    return {
        "state": "NORMAL",
        "reason": "No persistent pressure confirmed",
        "functions": [],
        "recommended_action": "HOLD",
    }



def validate_persistence(snapshots):
    decisions = [
        classify(snapshot)
        for snapshot in snapshots
    ]

    states = [
        decision["state"]
        for decision in decisions
    ]

    latest = decisions[-1]

    persistent = len(set(states)) == 1

    if not persistent:
        return {
            "state": "EVIDENCE_PENDING",
            "reason": (
                "Pressure was not present in two "
                "consecutive snapshots"
            ),
            "observed_states": states,
            "functions": [],
            "recommended_action": "HOLD",
            "persistent": False,
        }

    latest["observed_states"] = states
    latest["persistent"] = True
    return latest

def main():
    snapshots = load_recent(2)
    decision = validate_persistence(snapshots)

    output = {
        "timestamp": snapshots[-1]["timestamp"],
        "mode": "READ_ONLY",
        "evidence_window": 2,
        "decision": decision,
    }

    print(json.dumps(output, indent=2))

    output_file = Path("logs/localizer-decisions.jsonl")

    with output_file.open("a") as file:
        file.write(json.dumps(output) + "\n")


if __name__ == "__main__":
    main()
