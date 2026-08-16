#!/usr/bin/env python3

import argparse
import json
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

NAMESPACE = "free5gc"
INTERVAL = 5
ADMISSION_URL = "http://127.0.0.1:19091/admission"

FUNCTIONS = {
    "open5glos": ("deployment", "open5glos", "nf=open5glos"),
    "amf": ("deployment", "free5gc-free5gc-amf-amf", "nf=amf"),
    "ausf": ("deployment", "free5gc-free5gc-ausf-ausf", "nf=ausf"),
    "udm": ("deployment", "free5gc-free5gc-udm-udm", "nf=udm"),
    "udr": ("deployment", "free5gc-free5gc-udr-udr", "nf=udr"),
    "pcf": ("deployment", "free5gc-free5gc-pcf-pcf", "nf=pcf"),
    "mongodb": ("statefulset", "mongodb", "app.kubernetes.io/name=mongodb"),
}


def command(args):
    result = subprocess.run(
        args,
        text=True,
        capture_output=True,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())

    return result.stdout


def kubectl_json(args):
    return json.loads(command(["kubectl", *args, "-o", "json"]))


def cpu_to_m(value):
    if value.endswith("n"):
        return float(value[:-1]) / 1_000_000
    if value.endswith("u"):
        return float(value[:-1]) / 1_000
    if value.endswith("m"):
        return float(value[:-1])
    return float(value) * 1000


def memory_to_mib(value):
    if value.endswith("Ki"):
        return float(value[:-2]) / 1024
    if value.endswith("Mi"):
        return float(value[:-2])
    if value.endswith("Gi"):
        return float(value[:-2]) * 1024
    return float(value) / 1048576


def read_metrics():
    path = (
        "/apis/metrics.k8s.io/v1beta1/"
        f"namespaces/{NAMESPACE}/pods"
    )

    data = json.loads(
        command(["kubectl", "get", "--raw", path])
    )

    metrics = {}

    for item in data.get("items", []):
        cpu = 0.0
        memory = 0.0

        for container in item.get("containers", []):
            usage = container.get("usage", {})
            cpu += cpu_to_m(usage.get("cpu", "0"))
            memory += memory_to_mib(
                usage.get("memory", "0")
            )

        metrics[item["metadata"]["name"]] = {
            "cpu_m": round(cpu, 2),
            "memory_mib": round(memory, 2),
        }

    return metrics


def read_admission():
    try:
        with urllib.request.urlopen(
            ADMISSION_URL,
            timeout=2,
        ) as response:
            return json.loads(response.read())
    except Exception as error:
        return {
            "mode": "UNAVAILABLE",
            "error": str(error),
        }


def read_function(name, settings, metrics):
    kind, workload_name, selector = settings

    workload = kubectl_json(
        [
            "get",
            kind,
            workload_name,
            "-n",
            NAMESPACE,
        ]
    )

    pods = kubectl_json(
        [
            "get",
            "pods",
            "-n",
            NAMESPACE,
            "-l",
            selector,
        ]
    )

    cpu = 0.0
    memory = 0.0
    ready_pods = 0
    restarts = 0
    pod_names = []

    for pod in pods.get("items", []):
        pod_name = pod["metadata"]["name"]
        pod_names.append(pod_name)

        statuses = pod.get(
            "status",
            {},
        ).get("containerStatuses", [])

        if statuses and all(
            status.get("ready", False)
            for status in statuses
        ):
            ready_pods += 1

        restarts += sum(
            status.get("restartCount", 0)
            for status in statuses
        )

        usage = metrics.get(pod_name, {})
        cpu += usage.get("cpu_m", 0)
        memory += usage.get("memory_mib", 0)

    status = workload.get("status", {})
    spec = workload.get("spec", {})

    return {
        "function": name,
        "desired": spec.get("replicas", 0),
        "ready": status.get("readyReplicas", ready_pods),
        "available": status.get(
            "availableReplicas",
            ready_pods,
        ),
        "cpu_m": round(cpu, 2),
        "memory_mib": round(memory, 2),
        "restarts": restarts,
        "pods": pod_names,
    }


def collect():
    metrics = read_metrics()
    functions = {}

    for name, settings in FUNCTIONS.items():
        try:
            functions[name] = read_function(
                name,
                settings,
                metrics,
            )
        except Exception as error:
            functions[name] = {
                "function": name,
                "error": str(error),
            }

    return {
        "timestamp": datetime.now(
            timezone.utc
        ).isoformat(),
        "mode": "READ_ONLY",
        "admission": read_admission(),
        "functions": functions,
    }


def display(snapshot):
    print()
    print("=" * 72)
    print("DA-SACO READ-ONLY:", snapshot["timestamp"])
    print(
        "Admission:",
        snapshot["admission"].get("mode"),
    )
    print("-" * 72)

    for name, data in snapshot["functions"].items():
        if "error" in data:
            print(
                f"{name.upper():8} ERROR: {data['error']}"
            )
            continue

        print(
            f"{name.upper():8} "
            f"ready={data['ready']}/{data['desired']} "
            f"cpu={data['cpu_m']:.2f}m "
            f"memory={data['memory_mib']:.2f}Mi "
            f"restarts={data['restarts']}"
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "monitoring.jsonl"

    print("DA-SACO Monitoring Adapter: READ-ONLY")
    print("Press Ctrl+C after three snapshots.")

    while True:
        try:
            snapshot = collect()
            display(snapshot)

            with log_file.open("a") as file:
                file.write(json.dumps(snapshot) + "\n")

            if args.once:
                break

            time.sleep(INTERVAL)

        except KeyboardInterrupt:
            print("\nMonitoring stopped.")
            break

        except Exception as error:
            print("Collection error:", error)
            time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
