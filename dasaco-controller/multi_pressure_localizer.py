#!/usr/bin/env python3

import json
from pathlib import Path

from bottleneck_localizer import (
    CPU_REQUESTS,
    HIGH_THRESHOLD,
    cpu_percent,
)

LOG_FILE = Path("logs/monitoring.jsonl")

SCALABLE_FUNCTIONS = {
    "open5glos",
    "amf",
    "ausf",
    "udm",
    "udr",
    "pcf",
}

PROTECTION_ONLY_FUNCTIONS = {
    "mongodb",
}


def classify_all_pressures(snapshot):
    admission = snapshot.get("admission", {})

    if admission.get("mode") == "UNAVAILABLE":
        return {
            "state": "UNSAFE_OR_UNCERTAIN",
            "pressure_functions": [],
            "scale_candidates": [],
            "protection_candidates": [],
            "recommended_action": "HOLD",
        }

    pressured = []
    unhealthy = []

    for name, data in snapshot.get("functions", {}).items():
        if name not in CPU_REQUESTS:
            continue

        if "error" in data:
            unhealthy.append(name)
            continue

        if data.get("ready", 0) < data.get("desired", 0):
            unhealthy.append(name)
            continue

        utilization = cpu_percent(name, data)
        threshold = HIGH_THRESHOLD[name]

        if not utilization < threshold:
            pressured.append(name)

    if unhealthy:
        return {
            "state": "UNSAFE_OR_UNCERTAIN",
            "pressure_functions": [],
            "scale_candidates": [],
            "protection_candidates": [],
            "unhealthy_functions": sorted(unhealthy),
            "recommended_action": "HOLD",
        }

    pressured = sorted(pressured)

    if not pressured:
        return {
            "state": "NORMAL",
            "pressure_functions": [],
            "scale_candidates": [],
            "protection_candidates": [],
            "recommended_action": "HOLD",
        }

    scale_candidates = [
        name
        for name in pressured
        if name in SCALABLE_FUNCTIONS
    ]

    protection_candidates = [
        name
        for name in pressured
        if name in PROTECTION_ONLY_FUNCTIONS
    ]

    if len(pressured) == 1:
        state = pressured[0].upper() + "_PRESSURE"
    else:
        state = "MULTI_NF_PRESSURE"

    if scale_candidates:
        action = "SCALE_MULTIPLE_NFS_CANDIDATE"
    else:
        action = "PROTECT_WITH_ADMISSION"

    return {
        "state": state,
        "pressure_functions": pressured,
        "scale_candidates": scale_candidates,
        "protection_candidates": protection_candidates,
        "recommended_action": action,
    }


def validate_parallel_persistence(snapshots):
    decisions = [
        classify_all_pressures(snapshot)
        for snapshot in snapshots
    ]

    if any(
        item["state"] == "UNSAFE_OR_UNCERTAIN"
        for item in decisions
    ):
        return {
            "state": "UNSAFE_OR_UNCERTAIN",
            "pressure_functions": [],
            "scale_candidates": [],
            "protection_candidates": [],
            "recommended_action": "HOLD",
            "persistent": True,
        }

    pressure_sets = [
        set(item["pressure_functions"])
        for item in decisions
    ]

    persistent = sorted(
        set.intersection(*pressure_sets)
    )

    if not persistent:
        all_normal = all(
            item["state"] == "NORMAL"
            for item in decisions
        )

        return {
            "state": (
                "NORMAL"
                if all_normal
                else "EVIDENCE_PENDING"
            ),
            "pressure_functions": [],
            "scale_candidates": [],
            "protection_candidates": [],
            "recommended_action": "HOLD",
            "persistent": all_normal,
        }

    scale_candidates = [
        name
        for name in persistent
        if name in SCALABLE_FUNCTIONS
    ]

    protection_candidates = [
        name
        for name in persistent
        if name in PROTECTION_ONLY_FUNCTIONS
    ]

    if len(persistent) == 1:
        state = persistent[0].upper() + "_PRESSURE"
    else:
        state = "MULTI_NF_PRESSURE"

    return {
        "state": state,
        "pressure_functions": persistent,
        "scale_candidates": scale_candidates,
        "protection_candidates": protection_candidates,
        "recommended_action": (
            "SCALE_MULTIPLE_NFS_CANDIDATE"
            if scale_candidates
            else "PROTECT_WITH_ADMISSION"
        ),
        "persistent": True,
    }


def load_recent_snapshots(count=2):
    lines = [
        line
        for line in LOG_FILE.read_text().splitlines()
        if line.strip()
    ]

    if len(lines) < count:
        raise SystemExit(
            f"Need {count} monitoring snapshots, found {len(lines)}"
        )

    return [
        json.loads(line)
        for line in lines[-count:]
    ]


def main():
    snapshots = load_recent_snapshots(2)
    decision = validate_parallel_persistence(snapshots)

    output = {
        "timestamp": snapshots[-1]["timestamp"],
        "mode": "READ_ONLY",
        "evidence_window": 2,
        "decision": decision,
    }

    output_file = Path(
        "logs/parallel-localizer-decisions.jsonl"
    )
    output_file.parent.mkdir(exist_ok=True)

    with output_file.open("a") as file:
        file.write(json.dumps(output) + "\n")

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
