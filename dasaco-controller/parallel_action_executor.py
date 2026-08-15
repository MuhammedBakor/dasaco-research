#!/usr/bin/env python3

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import action_executor as base

MAX_PARALLEL_ACTIONS = 5


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def verify_amf(target):
    if not base.wait_for_amf_ready(target):
        raise RuntimeError("AMF readiness timeout")

    running = base.running_amf_pods()

    if len(running) != target:
        raise RuntimeError(
            f"Expected {target} running AMFs, found {len(running)}"
        )

    if not base.wait_for_open5glos_discovery(running):
        raise RuntimeError("Open5GLoS AMF discovery timeout")

    return {
        "ready_replicas": target,
        "running_pods": sorted(running),
        "verification": "KUBERNETES_AND_OPEN5GLOS",
    }


def verify_nf(name, target):
    if not base.wait_for_nf_ready(name, target):
        raise RuntimeError(
            f"{name.upper()} readiness timeout"
        )

    if not base.wait_for_nrf_registration(name, target):
        raise RuntimeError(
            f"{name.upper()} NRF registration timeout"
        )

    return {
        "ready_replicas": target,
        "registered_instances": target,
        "verification": "KUBERNETES_AND_NRF",
    }


def scale_and_verify(name, original, target):
    started = timestamp()

    try:
        if name == "amf":
            base.scale_amf(target)
            verification = verify_amf(target)
        else:
            base.scale_nf(name, target)
            verification = verify_nf(name, target)

        return {
            "function": name,
            "phase": "CAPACITY_VERIFIED",
            "original_replicas": original,
            "target_replicas": target,
            "started_at": started,
            "finished_at": timestamp(),
            "success": True,
            "verification": verification,
            "error": None,
        }

    except Exception as error:
        rollback_error = None

        try:
            if name == "amf":
                base.scale_amf(original)

                if not base.wait_for_amf_ready(original):
                    raise RuntimeError(
                        "AMF rollback readiness timeout"
                    )
            else:
                base.scale_nf(name, original)

                if not base.wait_for_nf_ready(name, original):
                    raise RuntimeError(
                        f"{name.upper()} rollback readiness timeout"
                    )

                if not base.wait_for_nrf_registration(
                    name,
                    original,
                ):
                    raise RuntimeError(
                        f"{name.upper()} rollback NRF timeout"
                    )

        except Exception as failure:
            rollback_error = str(failure)

        return {
            "function": name,
            "phase": (
                "ROLLED_BACK"
                if rollback_error is None
                else "FAILED"
            ),
            "original_replicas": original,
            "target_replicas": target,
            "started_at": started,
            "finished_at": timestamp(),
            "success": False,
            "verification": None,
            "error": str(error),
            "rollback_error": rollback_error,
        }


def build_parallel_plan(decision):
    requested = list(
        dict.fromkeys(
            decision.get("scale_candidates", [])
        )
    )

    candidates = []
    blocked = []

    for name in requested:
        if name not in base.NF_CONFIG:
            blocked.append({
                "function": name,
                "reason": "Unsupported function",
            })
            continue

        settings = base.nf_settings(name)

        if not settings.get("eligible", False):
            blocked.append({
                "function": name,
                "reason": "Scaling eligibility not verified",
            })
            continue

        current = base.current_nf_replicas(name)

        if current >= settings["max_replicas"]:
            blocked.append({
                "function": name,
                "reason": "Maximum replica limit reached",
            })
            continue

        candidates.append({
            "function": name,
            "original_replicas": current,
            "target_replicas": current + 1,
        })

    return {
        "timestamp": timestamp(),
        "mode": "DRY_RUN" if base.DRY_RUN else "ACTIVE",
        "action": (
            "SCALE_MULTIPLE_NFS"
            if candidates
            else "HOLD"
        ),
        "candidates": candidates[:MAX_PARALLEL_ACTIONS],
        "blocked": blocked,
        "protection_candidates": decision.get(
            "protection_candidates",
            [],
        ),
        "executed": False,
    }


def execute_parallel_plan(plan):
    candidates = plan.get("candidates", [])

    if not candidates:
        plan["reason"] = "No eligible scaling candidates"
        return plan

    protection = base.set_admission_mode(
        "STRONG_PROTECTION"
    )

    base.append_action_event({
        "timestamp": timestamp(),
        "phase": "PARALLEL_PROTECTION_ACTIVE",
        "functions": [
            item["function"]
            for item in candidates
        ],
        "admission": protection,
    })

    state = {
        "phase": "PARALLEL_ACTIONS_ACTIVE",
        "action": "SCALE_MULTIPLE_NFS",
        "started_at": timestamp(),
        "admission_mode": "STRONG_PROTECTION",
        "actions": {
            item["function"]: {
                "phase": "CAPACITY_PENDING",
                "original_replicas":
                    item["original_replicas"],
                "target_replicas":
                    item["target_replicas"],
                "last_error": None,
            }
            for item in candidates
        },
        "last_error": None,
    }

    base.write_state(state)

    results = []

    with ThreadPoolExecutor(
        max_workers=len(candidates)
    ) as executor:
        futures = {
            executor.submit(
                scale_and_verify,
                item["function"],
                item["original_replicas"],
                item["target_replicas"],
            ): item["function"]
            for item in candidates
        }

        for future in as_completed(futures):
            result = future.result()
            results.append(result)

            name = result["function"]
            state["actions"][name]["phase"] = result["phase"]
            state["actions"][name]["last_error"] = result.get(
                "error"
            )
            base.write_state(state)

            base.append_action_event({
                "timestamp": timestamp(),
                "phase": result["phase"],
                "target_function": name,
                "original_replicas":
                    result["original_replicas"],
                "target_replicas":
                    result["target_replicas"],
                "success": result["success"],
                "error": result.get("error"),
                "rollback_error":
                    result.get("rollback_error"),
                "verification":
                    result.get("verification"),
            })

    verified = [
        item["function"]
        for item in results
        if item["success"]
    ]

    failed = [
        item["function"]
        for item in results
        if not item["success"]
    ]

    state["phase"] = (
        "PARALLEL_CAPACITY_VERIFIED"
        if verified
        else "PARALLEL_FAILED"
    )

    state["verified_functions"] = verified
    state["failed_functions"] = failed
    base.write_state(state)

    plan["executed"] = True
    plan["results"] = results
    plan["verified_functions"] = verified
    plan["failed_functions"] = failed
    plan["controller_phase"] = state["phase"]

    return plan


def main():
    record = base.read_latest_decision()
    decision = record["decision"]
    plan = build_parallel_plan(decision)

    if not base.DRY_RUN and plan["action"] == "SCALE_MULTIPLE_NFS":
        plan = execute_parallel_plan(plan)

    print(json.dumps(plan, indent=2))


if __name__ == "__main__":
    main()
