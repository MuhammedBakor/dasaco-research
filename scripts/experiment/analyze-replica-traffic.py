#!/usr/bin/env python3

import argparse
import csv
import json
import re
from pathlib import Path


IDENTIFIER_PATTERNS = [
    re.compile(r"imsi[-:]?(\d{10,18})", re.IGNORECASE),
    re.compile(r"\bSUPI[:\s-]*(?:imsi[-:]?)?(\d{10,18})", re.IGNORECASE),
    re.compile(r"\bueId[=:\"\s]+(?:imsi[-:]?)?(\d{10,18})", re.IGNORECASE),
]

EVENT_PATTERNS = [
    re.compile(r"InitialRegistration", re.IGNORECASE),
    re.compile(r"Authentication", re.IGNORECASE),
    re.compile(r"Registration Accept", re.IGNORECASE),
    re.compile(r"Registration Complete", re.IGNORECASE),
    re.compile(r"UeAuthentications", re.IGNORECASE),
    re.compile(r"subscription-data", re.IGNORECASE),
    re.compile(r"policy", re.IGNORECASE),
    re.compile(r"nudm", re.IGNORECASE),
    re.compile(r"nudr", re.IGNORECASE),
    re.compile(r"nausf", re.IGNORECASE),
    re.compile(r"npcf", re.IGNORECASE),
]


def identifiers_from_line(line):
    identifiers = set()

    for pattern in IDENTIFIER_PATTERNS:
        for match in pattern.finditer(line):
            identifiers.add(match.group(1))

    return identifiers


def is_request_event(line):
    return any(pattern.search(line) for pattern in EVENT_PATTERNS)


def parse_log_name(path):
    stem = path.stem

    if "__" not in stem:
        return "unknown", stem

    function, pod = stem.split("__", 1)
    return function, pod


def load_capacity_idle_pods(actions_path):
    """Return new replicas explicitly classified as idle."""
    idle_pods = set()

    if not actions_path.exists():
        return idle_pods

    for line in actions_path.read_text(
        errors="replace"
    ).splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue

        if record.get("phase") != "CAPACITY_IDLE":
            continue

        for pod in record.get("new_pods") or []:
            idle_pods.add(pod)

        traffic_use = record.get("traffic_use") or {}

        for replica in traffic_use.get("replicas") or []:
            if not isinstance(replica, dict):
                continue

            if replica.get("used") is False and replica.get("pod"):
                idle_pods.add(replica["pod"])

    return idle_pods


def load_open5glos_admission(actions_path):
    """Return the latest per-Pod Open5GLoS admission counters."""
    counters = {}

    if not actions_path.exists():
        return counters

    for line in actions_path.read_text(
        errors="replace"
    ).splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue

        admission = record.get("admission") or {}
        pods = admission.get("pods") or {}

        for pod, runtime in pods.items():
            if not isinstance(runtime, dict):
                continue

            admitted = runtime.get("admitted")

            if isinstance(admitted, int):
                counters[pod] = max(
                    counters.get(pod, 0),
                    admitted,
                )

    return counters


def load_original_pods_from_timeline(timeline_path):
    """Return the first observed Pod for each function.

    The collector starts before the workload and before scale-out.
    Therefore, the first observed Pod for a function is its baseline
    replica. Pods appearing later are classified as new replicas.
    """
    originals = {}

    if not timeline_path.exists():
        return originals

    for line in timeline_path.read_text(
        errors="replace"
    ).splitlines():
        fields = line.split("\t")

        if len(fields) < 5:
            continue

        timestamp, function, pod, phase, ready = fields[:5]

        if function and pod:
            originals.setdefault(function, pod)

    return originals


def load_original_pods(actions_path):
    originals = {}

    if not actions_path.exists():
        return originals

    for line in actions_path.read_text(errors="replace").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue

        function = record.get("target_function")
        original_replicas = record.get("original_replicas")

        verification = record.get("verification") or {}
        running_pods = verification.get("running_pods") or []

        if function and original_replicas == 1 and running_pods:
            originals.setdefault(function, running_pods[-1])

    return originals


parser = argparse.ArgumentParser()
parser.add_argument("--run-dir", required=True)
args = parser.parse_args()

run_dir = Path(args.run_dir)
pod_logs = run_dir / "pod-logs"
actions_path = run_dir / "controller-actions.jsonl"
timeline_path = (
    run_dir
    / "replica-snapshots"
    / "timeline.tsv"
)

if not pod_logs.exists():
    raise SystemExit(f"Pod log directory not found: {pod_logs}")

capacity_idle_pods = load_capacity_idle_pods(
    actions_path
)

open5glos_admission = load_open5glos_admission(
    actions_path
)

original_pods = load_original_pods_from_timeline(
    timeline_path
)

if not original_pods:
    original_pods = load_original_pods(actions_path)
rows = []

for path in sorted(pod_logs.glob("*.log")):
    function, pod = parse_log_name(path)

    identifiers = set()
    request_events = 0
    unique_lines = set()

    for line in path.read_text(errors="replace").splitlines():
        if line.startswith("===== SNAPSHOT"):
            continue

        if line in unique_lines:
            continue

        unique_lines.add(line)
        identifiers.update(identifiers_from_line(line))

        if is_request_event(line):
            request_events += 1

    original_pod = original_pods.get(function)

    if original_pod:
        replica_role = "original" if pod == original_pod else "new"
    else:
        replica_role = "unknown"

    admitted_registrations = (
        open5glos_admission.get(pod, 0)
        if function == "open5glos"
        else 0
    )

    controller_capacity_idle = (
        replica_role == "new"
        and pod in capacity_idle_pods
        and not identifiers
        and admitted_registrations == 0
    )

    if controller_capacity_idle:
        used = False
        measurement_source = "controller-capacity-idle"
    else:
        used = bool(
            identifiers
            or request_events
            or admitted_registrations
        )

        if function == "open5glos" and admitted_registrations:
            measurement_source = "runtime-admission-counter"
        elif identifiers:
            measurement_source = "unique-identifiers-in-pod-log"
        elif request_events:
            measurement_source = "request-events-in-pod-log"
        else:
            measurement_source = "no-traffic-evidence"

    rows.append(
        {
            "function": function,
            "pod": pod,
            "replica_role": replica_role,
            "unique_ues": len(identifiers),
            "admitted_registrations": admitted_registrations,
            "request_events": request_events,
            "used": str(used).lower(),
            "measurement_source": measurement_source,
            "identifiers": ",".join(sorted(identifiers)),
        }
    )

csv_path = run_dir / "per-replica-traffic.csv"

with csv_path.open("w", newline="") as file:
    writer = csv.DictWriter(
        file,
        fieldnames=[
            "function",
            "pod",
            "replica_role",
            "unique_ues",
            "admitted_registrations",
            "request_events",
            "used",
            "measurement_source",
            "identifiers",
        ],
    )
    writer.writeheader()
    writer.writerows(rows)

summary_lines = [
    "DA-SACO Per-Replica Traffic Summary",
    "",
]

for row in rows:
    summary_lines.append(
        (
            "{} | {} | role={} | unique_ues={} | "
            "admitted={} | request_events={} | used={} | source={}"
        ).format(
            row["function"],
            row["pod"],
            row["replica_role"],
            row["unique_ues"],
            row["admitted_registrations"],
            row["request_events"],
            row["used"],
            row["measurement_source"],
        )
    )

summary_path = run_dir / "per-replica-traffic.txt"
summary_path.write_text("\n".join(summary_lines) + "\n")

print("\n".join(summary_lines))
print()
print(f"CSV: {csv_path}")
print(f"Summary: {summary_path}")
