#!/usr/bin/env python3

import json
from pathlib import Path

LOG_FILE = Path("logs/monitoring.jsonl")

CPU_REQUESTS = {
    "amf": 100,
    "ausf": 100,
    "udm": 100,
    "udr": 100,
    "mongodb": 100,
}

HIGH_THRESHOLD = {
    "amf": 70,
    "ausf": 75,
    "udm": 75,
    "udr": 75,
    "mongodb": 160,
}


def load_latest():
    if not LOG_FILE.exists():
        raise SystemExit("Monitoring log does not exist")

    lines = [
        line
        for line in LOG_FILE.read_text().splitlines()
        if line.strip()
    ]

    if not lines:
        raise SystemExit("Monitoring log is empty")

    return json.loads(lines[-1])


def cpu_percent(name, data):
    request = CPU_REQUESTS[name]
    return 100 * data.get("cpu_m", 0) / request


def classify(snapshot):
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


def main():
    snapshot = load_latest()
    decision = classify(snapshot)

    output = {
        "timestamp": snapshot["timestamp"],
        "mode": "READ_ONLY",
        "decision": decision,
    }

    print(json.dumps(output, indent=2))

    output_file = Path("logs/localizer-decisions.jsonl")

    with output_file.open("a") as file:
        file.write(json.dumps(output) + "\n")


if __name__ == "__main__":
    main()
