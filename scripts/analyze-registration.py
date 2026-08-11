#!/usr/bin/env python3

import argparse
import csv
import re
from pathlib import Path
from datetime import datetime
from statistics import median

LINE_RE = re.compile(
    r'^(?P<ts>\S+).*?'
    r'\[supi:SUPI:(?P<supi>imsi-\d+)\]\s+'
    r'(?P<event>.*)$'
)

def parse_time(value):
    value = value.split(chr(27), 1)[0].strip()

    if value.endswith("Z"):
        value = value[:-1]
        timezone = "+00:00"
    else:
        timezone = ""

    if "." in value:
        base, fraction = value.split(".", 1)
        fraction = fraction[:6].ljust(6, "0")
        value = f"{base}.{fraction}"

    return datetime.fromisoformat(value + timezone)

def percentile(values, p):
    if not values:
        return None

    values = sorted(values)
    position = (len(values) - 1) * p
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    fraction = position - lower

    return values[lower] + (
        values[upper] - values[lower]
    ) * fraction

parser = argparse.ArgumentParser()
parser.add_argument(
    "--logs",
    nargs="+",
    required=True,
    help="One or more AMF log files"
)
parser.add_argument(
    "--output",
    required=True,
    help="Output directory"
)
args = parser.parse_args()

records = {}

for log_path in args.logs:
    path = Path(log_path)

    if not path.exists():
        continue

    pod_name = path.stem

    for line in path.read_text(
        errors="replace"
    ).splitlines():

        match = LINE_RE.search(line)

        if not match:
            continue

        timestamp = parse_time(match.group("ts"))
        supi = match.group("supi")
        event = match.group("event")

        record = records.setdefault(
            supi,
            {
                "supi": supi,
                "pod": pod_name,
                "first_initial": None,
                "last_complete": None,
                "initial_events": 0,
                "accept_events": 0,
                "complete_events": 0
            }
        )

        record["pod"] = pod_name

        if "Handle InitialRegistration" in event:
            record["initial_events"] += 1

            if (
                record["first_initial"] is None
                or timestamp < record["first_initial"]
            ):
                record["first_initial"] = timestamp

        if "Send Registration Accept" in event:
            record["accept_events"] += 1

        if "Handle Registration Complete" in event:
            record["complete_events"] += 1

            if (
                record["last_complete"] is None
                or timestamp > record["last_complete"]
            ):
                record["last_complete"] = timestamp

output = Path(args.output)
output.mkdir(parents=True, exist_ok=True)

rows = []

for supi, record in sorted(records.items()):
    completed = (
        record["first_initial"] is not None
        and record["last_complete"] is not None
    )

    latency_ms = None

    if completed:
        latency_ms = (
            record["last_complete"]
            - record["first_initial"]
        ).total_seconds() * 1000

    retries = max(
        record["initial_events"] - 1,
        record["accept_events"] - 1,
        0
    )

    rows.append(
        {
            "supi": supi,
            "amf_pod": record["pod"],
            "initial_events": record["initial_events"],
            "accept_events": record["accept_events"],
            "complete_events": record["complete_events"],
            "completed": int(completed),
            "retries": retries,
            "latency_ms": (
                f"{latency_ms:.3f}"
                if latency_ms is not None
                else ""
            )
        }
    )

with (output / "per-ue.csv").open(
    "w",
    newline=""
) as file:
    writer = csv.DictWriter(
        file,
        fieldnames=[
            "supi",
            "amf_pod",
            "initial_events",
            "accept_events",
            "complete_events",
            "completed",
            "retries",
            "latency_ms"
        ]
    )

    writer.writeheader()
    writer.writerows(rows)

started = [
    row for row in rows
    if row["initial_events"] > 0
]

completed = [
    row for row in rows
    if row["completed"] == 1
]

latencies = [
    float(row["latency_ms"])
    for row in completed
]

unique_started = len(started)
unique_completed = len(completed)

success_ratio = (
    100 * unique_completed / unique_started
    if unique_started
    else 0
)

retry_ues = sum(
    1 for row in rows
    if row["retries"] > 0
)

total_retries = sum(
    row["retries"] for row in rows
)

pod_counts = {}

for row in completed:
    pod_counts[row["amf_pod"]] = (
        pod_counts.get(row["amf_pod"], 0) + 1
    )

summary = [
    f"Unique UEs started: {unique_started}",
    f"Unique UEs completed: {unique_completed}",
    f"Unique success ratio: {success_ratio:.2f}%",
    f"UEs requiring retry: {retry_ues}",
    f"Estimated retry events: {total_retries}"
]

if latencies:
    summary.extend(
        [
            f"P50 latency: {percentile(latencies, 0.50):.3f} ms",
            f"P95 latency: {percentile(latencies, 0.95):.3f} ms",
            f"P99 latency: {percentile(latencies, 0.99):.3f} ms",
            f"Minimum latency: {min(latencies):.3f} ms",
            f"Maximum latency: {max(latencies):.3f} ms"
        ]
    )

summary.append("")
summary.append("Completed UEs by AMF Pod:")

for pod, count in sorted(
    pod_counts.items(),
    key=lambda item: item[1],
    reverse=True
):
    summary.append(f"{pod}: {count}")

summary_text = "\n".join(summary)

(output / "summary.txt").write_text(
    summary_text + "\n"
)

print(summary_text)
