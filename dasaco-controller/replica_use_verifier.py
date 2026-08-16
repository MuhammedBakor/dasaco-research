#!/usr/bin/env python3

import re

import action_executor as base


PATTERNS = {
    "open5glos": [
        r"Handling Initial UE Message",
        r"Accepted connection",
    ],
    "amf": [
        r"Handle Registration Request",
        r"Send Registration Accept",
    ],
    "ausf": [
        r"/nausf-auth/v1/ue-authentications",
        r"5g-aka-confirmation",
    ],
    "udm": [
        r"\[UDM\]\[GIN\]",
        r"/nudm-",
    ],
    "udr": [
        r"\[UDR\]\[GIN\]",
        r"/nudr-",
    ],
    "pcf": [
        r"\[PCF\]\[GIN\]",
        r"/npcf-",
    ],
}

IDENTIFIERS = {
    "open5glos": r"(?:imsi-|suci-)[0-9]+",
    "amf": r"imsi-[0-9]+",
    "ausf": r"suci-0-[0-9-]+",
    "udm": r"imsi-[0-9]+",
    "udr": r"imsi-[0-9]+",
    "pcf": r"imsi-[0-9]+",
}


def pod_logs(pod, since="5m"):
    return base.run_command([
        "kubectl",
        "logs",
        "-n",
        base.NAMESPACE,
        pod,
        f"--since={since}",
    ])


def traffic_evidence(name, pod, since="5m"):
    logs = pod_logs(pod, since=since)
    patterns = PATTERNS[name]

    request_count = sum(
        1
        for line in logs.splitlines()
        if any(
            re.search(pattern, line)
            for pattern in patterns
        )
    )

    identifiers = set(
        re.findall(
            IDENTIFIERS[name],
            logs,
            flags=re.IGNORECASE,
        )
    )

    runtime = None

    if name == "open5glos":
        runtime = base.open5glos_runtime(pod)

    used = (
        request_count > 0
        or len(identifiers) > 0
        or (
            runtime is not None
            and runtime.get(
                "active_gnb_connections",
                0,
            ) > 0
        )
    )

    return {
        "function": name,
        "pod": pod,
        "used": used,
        "request_events": request_count,
        "unique_identifiers": len(identifiers),
        "identifiers": sorted(identifiers),
        "runtime": runtime,
        "window": since,
    }


def verify_new_pods(name, pods, since="5m"):
    evidence = [
        traffic_evidence(
            name,
            pod,
            since=since,
        )
        for pod in sorted(pods)
    ]

    return {
        "function": name,
        "status": (
            "CAPACITY_USE_VERIFIED"
            if evidence
            and all(
                item["used"]
                for item in evidence
            )
            else "CAPACITY_IDLE"
        ),
        "all_new_replicas_used": (
            bool(evidence)
            and all(
                item["used"]
                for item in evidence
            )
        ),
        "replicas": evidence,
    }
