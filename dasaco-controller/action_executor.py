#!/usr/bin/env python3
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

DECISION_LOG = Path("logs/localizer-decisions.jsonl")
ACTION_LOG = Path("logs/action-plans.jsonl")
STATE_FILE = Path("logs/controller-state.json")
ACTION_STATE_LOG = Path("logs/controller-actions.jsonl")
NAMESPACE = "free5gc"
AMF_DEPLOYMENT = "free5gc-free5gc-amf-amf"
AMF_MAX_REPLICAS = 5
AMF_READY_TIMEOUT_SECONDS = 120
AMF_DISCOVERY_TIMEOUT_SECONDS = 60
POLL_INTERVAL_SECONDS = 3
OPEN5GLOS_LABEL = "nf=open5glos"
DRY_RUN = os.getenv("DASACO_ACTIVE", "0") != "1"

NF_CONFIG = {
    "amf": {
        "deployment": "free5gc-free5gc-amf-amf",
        "label": "nf=amf",
        "max_replicas": 5,
        "eligible": True,
        "nrf_type": "AMF",
        "requester_type": "AMF",
    },
    "ausf": {
        "deployment": "free5gc-free5gc-ausf-ausf",
        "label": "nf=ausf",
        "max_replicas": 3,
        "eligible": True,
        "nrf_type": "AUSF",
        "requester_type": "AMF",
    },
    "udm": {
        "deployment": "free5gc-free5gc-udm-udm",
        "label": "nf=udm",
        "max_replicas": 3,
        "eligible": True,
        "nrf_type": "UDM",
        "requester_type": "AUSF",
    },
    "udr": {
        "deployment": "free5gc-free5gc-udr-udr",
        "label": "nf=udr",
        "max_replicas": 3,
        "eligible": True,
        "nrf_type": "UDR",
        "requester_type": "UDM",
    },
    "pcf": {
        "deployment": "free5gc-free5gc-pcf-pcf",
        "label": "nf=pcf",
        "max_replicas": 3,
        "eligible": True,
        "nrf_type": "PCF",
        "requester_type": "AMF",
    },
}

NF_READY_TIMEOUT_SECONDS = 120

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

def nf_settings(name):
    if name not in NF_CONFIG:
        raise RuntimeError(f"Unsupported NF: {name}")
    return NF_CONFIG[name]


def current_nf_replicas(name):
    settings = nf_settings(name)

    value = run_command([
        "kubectl", "get", "deployment",
        settings["deployment"],
        "-n", NAMESPACE,
        "-o", "jsonpath={.spec.replicas}",
    ])

    return int(value)


def ready_nf_replicas(name):
    settings = nf_settings(name)

    value = run_command([
        "kubectl", "get", "deployment",
        settings["deployment"],
        "-n", NAMESPACE,
        "-o", "jsonpath={.status.readyReplicas}",
    ])

    return int(value or "0")


def scale_nf(name, target):
    settings = nf_settings(name)

    if not settings["eligible"]:
        raise RuntimeError(
            f"{name.upper()} scaling eligibility is not verified"
        )

    if target < 1 or target > settings["max_replicas"]:
        raise RuntimeError(
            f"{name.upper()} target {target} is outside safe range"
        )

    run_command([
        "kubectl", "scale",
        f"deployment/{settings['deployment']}",
        "-n", NAMESPACE,
        f"--replicas={target}",
    ])


def wait_for_nf_ready(name, target):
    deadline = time.monotonic() + NF_READY_TIMEOUT_SECONDS

    while time.monotonic() < deadline:
        desired = current_nf_replicas(name)
        ready = ready_nf_replicas(name)

        if desired == target and ready == target:
            return True

        time.sleep(POLL_INTERVAL_SECONDS)

    return False


def nrf_registered_count(name):
    settings = nf_settings(name)
    target_type = settings.get("nrf_type")
    requester_type = settings.get("requester_type")

    if not target_type or not requester_type:
        return current_nf_replicas(name)

    pod = f"dasaco-nrf-check-{name}"

    run_command([
        "kubectl", "delete", "pod", pod,
        "-n", NAMESPACE,
        "--ignore-not-found",
    ])

    url = (
        "http://nrf-nnrf:8000/nnrf-disc/v1/nf-instances"
        f"?requester-nf-type={requester_type}"
        f"&target-nf-type={target_type}"
    )

    try:
        run_command([
            "kubectl", "run", pod,
            "-n", NAMESPACE,
            "--restart=Never",
            "--image=curlimages/curl:8.7.1",
            "--",
            "curl", "-sf", url,
        ])

        run_command([
            "kubectl", "wait",
            "-n", NAMESPACE,
            "--for=jsonpath={.status.phase}=Succeeded",
            f"pod/{pod}",
            "--timeout=30s",
        ])

        response = run_command([
            "kubectl", "logs",
            "-n", NAMESPACE,
            f"pod/{pod}",
        ])

        document = json.loads(response)
        instances = document.get("nfInstances", [])

        return sum(
            1
            for instance in instances
            if instance.get("nfStatus") == "REGISTERED"
        )

    finally:
        run_command([
            "kubectl", "delete", "pod", pod,
            "-n", NAMESPACE,
            "--ignore-not-found",
        ])


def wait_for_nrf_registration(name, target):
    deadline = time.monotonic() + NF_READY_TIMEOUT_SECONDS

    while time.monotonic() < deadline:
        if nrf_registered_count(name) >= target:
            return True

        time.sleep(POLL_INTERVAL_SECONDS)

    return False


def current_amf_replicas():
    value = run_command([
        "kubectl", "get", "deployment", AMF_DEPLOYMENT,
        "-n", NAMESPACE,
        "-o", "jsonpath={.spec.replicas}",
    ])
    return int(value)

def scale_amf(target):
    if target < 1 or target > AMF_MAX_REPLICAS:
        raise RuntimeError(
            f"AMF target {target} is outside the safe range"
        )

    run_command([
        "kubectl",
        "scale",
        f"deployment/{AMF_DEPLOYMENT}",
        "-n",
        NAMESPACE,
        f"--replicas={target}",
    ])


def ready_amf_replicas():
    value = run_command([
        "kubectl",
        "get",
        "deployment",
        AMF_DEPLOYMENT,
        "-n",
        NAMESPACE,
        "-o",
        "jsonpath={.status.readyReplicas}",
    ])

    return int(value or "0")


def wait_for_amf_ready(target):
    deadline = time.monotonic() + AMF_READY_TIMEOUT_SECONDS

    while time.monotonic() < deadline:
        desired = current_amf_replicas()
        ready = ready_amf_replicas()

        if desired == target and ready == target:
            return True

        time.sleep(POLL_INTERVAL_SECONDS)

    return False


def running_pods(label):
    output = run_command([
        "kubectl",
        "get",
        "pods",
        "-n",
        NAMESPACE,
        "-l",
        label,
        "--field-selector=status.phase=Running",
        "-o",
        "json",
    ])

    document = json.loads(output)

    return {
        item["metadata"]["name"]
        for item in document.get("items", [])
        if item.get("status", {}).get("phase") == "Running"
    }


def running_amf_pods():
    return running_pods("nf=amf")


def current_open5glos_pod():
    pods = sorted(running_pods(OPEN5GLOS_LABEL))

    if len(pods) != 1:
        raise RuntimeError(
            "Expected exactly one Running Open5GLoS Pod, "
            f"found {len(pods)}"
        )

    return pods[0]


def discovered_amf_pods():
    pod = current_open5glos_pod()

    logs = run_command([
        "kubectl",
        "logs",
        "-n",
        NAMESPACE,
        pod,
        "--since=2h",
    ])

    discovered = set()
    log_marker = "Added AMF to manager:"

    for line in logs.splitlines():
        if log_marker in line:
            name = line.split(log_marker, 1)[1].strip()
            if name:
                discovered.add(name)

    return discovered


def wait_for_open5glos_discovery(expected_pods):
    deadline = time.monotonic() + AMF_DISCOVERY_TIMEOUT_SECONDS
    expected = set(expected_pods)

    while time.monotonic() < deadline:
        discovered = discovered_amf_pods()

        if expected.issubset(discovered):
            return True

        time.sleep(POLL_INTERVAL_SECONDS)

    return False


def default_state():
    return {
        "phase": "IDLE",
        "action": None,
        "target_function": None,
        "original_replicas": None,
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


def set_admission_mode(mode):
    if mode not in {"OPEN", "STRONG_PROTECTION"}:
        raise RuntimeError(
            f"Unsupported admission mode: {mode}"
        )

    pod = "dasaco-admission-action"

    run_command([
        "kubectl", "delete", "pod", pod,
        "-n", NAMESPACE,
        "--ignore-not-found",
    ])

    try:
        run_command([
            "kubectl", "run", pod,
            "-n", NAMESPACE,
            "--restart=Never",
            "--image=curlimages/curl:8.7.1",
            "--",
            "curl", "-sf", "-X", "PUT",
            "-H", "Content-Type: application/json",
            "-d", json.dumps({"mode": mode}),
            "http://open5glos-control:9091/admission",
        ])

        run_command([
            "kubectl", "wait",
            "-n", NAMESPACE,
            "--for=jsonpath={.status.phase}=Succeeded",
            f"pod/{pod}",
            "--timeout=30s",
        ])

        response = run_command([
            "kubectl", "logs",
            "-n", NAMESPACE,
            f"pod/{pod}",
        ])

        result = json.loads(response)

        if result.get("mode") != mode:
            raise RuntimeError(
                f"Admission verification failed: {result}"
            )

        return result

    finally:
        run_command([
            "kubectl", "delete", "pod", pod,
            "-n", NAMESPACE,
            "--ignore-not-found",
        ])


def execute_generic_nf_scale_plan(plan):
    name = plan["target_function"]
    original = plan["current_nf_replicas"]
    target = plan["proposed_nf_replicas"]
    started = datetime.now(timezone.utc).isoformat()

    state = {
        **default_state(),
        "phase": "CAPACITY_PENDING",
        "action": f"SCALE_{name.upper()}",
        "target_function": name,
        "original_replicas": original,
        "target_replicas": target,
        "started_at": started,
    }
    write_state(state)

    append_action_event({
        "timestamp": started,
        "phase": "CAPACITY_PENDING",
        "target_function": name,
        "original_replicas": original,
        "target_replicas": target,
    })

    try:
        protection = set_admission_mode("STRONG_PROTECTION")

        append_action_event({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "phase": "PROTECTION_ACTIVE",
            "target_function": name,
            "admission": protection,
        })

        scale_nf(name, target)

        if not wait_for_nf_ready(name, target):
            raise RuntimeError(
                f"{name.upper()} readiness timeout"
            )

        state["phase"] = "DISCOVERY_PENDING"
        write_state(state)

        if not wait_for_nrf_registration(name, target):
            raise RuntimeError(
                f"{name.upper()} NRF registration timeout"
            )

        state["phase"] = "CAPACITY_VERIFIED"
        write_state(state)

        plan["executed"] = True
        plan["controller_phase"] = "CAPACITY_VERIFIED"
        plan["reason"] = (
            f"{name.upper()} scale-out completed and "
            "Kubernetes readiness verified"
        )

        append_action_event({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "phase": "CAPACITY_VERIFIED",
            "target_function": name,
            "target_replicas": target,
            "ready_replicas": ready_nf_replicas(name),
        })

        return plan

    except Exception as error:
        state["phase"] = "ROLLBACK"
        state["last_error"] = str(error)
        write_state(state)

        append_action_event({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "phase": "ROLLBACK",
            "target_function": name,
            "rollback_target": original,
            "error": str(error),
        })

        try:
            scale_nf(name, original)

            if not wait_for_nf_ready(name, original):
                raise RuntimeError(
                    f"{name.upper()} rollback readiness timeout"
                )

            set_admission_mode("OPEN")
            write_state(default_state())

        except Exception as rollback_error:
            state["phase"] = "FAILED"
            state["last_error"] = (
                f"{error}; rollback failed: {rollback_error}"
            )
            write_state(state)
            raise

        plan["executed"] = False
        plan["controller_phase"] = "IDLE"
        plan["reason"] = (
            f"{name.upper()} scaling failed and rolled back: {error}"
        )

        return plan


def execute_scale_plan(plan):
    original = plan["current_amf_replicas"]
    target = plan["proposed_amf_replicas"]
    started = datetime.now(timezone.utc).isoformat()

    state = {
        **default_state(),
        "phase": "CAPACITY_PENDING",
        "action": "SCALE_AMF",
        "target_function": "amf",
        "original_replicas": original,
        "target_replicas": target,
        "started_at": started,
    }
    write_state(state)
    append_action_event({
        "timestamp": started,
        "phase": "CAPACITY_PENDING",
        "original_replicas": original,
        "target_replicas": target,
    })

    try:
        protection = set_admission_mode(
            "STRONG_PROTECTION"
        )

        append_action_event({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "phase": "PROTECTION_ACTIVE",
            "admission": protection,
        })

        scale_amf(target)

        if not wait_for_amf_ready(target):
            raise RuntimeError("AMF readiness timeout")

        state["phase"] = "DISCOVERY_PENDING"
        write_state(state)

        running = running_amf_pods()

        if len(running) != target:
            raise RuntimeError(
                f"Expected {target} Running AMFs, found {len(running)}"
            )

        if not wait_for_open5glos_discovery(running):
            raise RuntimeError("Open5GLoS discovery timeout")

        state["phase"] = "CAPACITY_VERIFIED"
        write_state(state)

        plan["executed"] = True
        plan["controller_phase"] = "CAPACITY_VERIFIED"
        plan["reason"] = (
            "AMF scale-out completed; readiness and "
            "Open5GLoS discovery verified"
        )

        append_action_event({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "phase": "CAPACITY_VERIFIED",
            "target_replicas": target,
            "running_amfs": sorted(running),
        })

        return plan

    except Exception as error:
        state["phase"] = "ROLLBACK"
        state["last_error"] = str(error)
        write_state(state)

        append_action_event({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "phase": "ROLLBACK",
            "error": str(error),
            "rollback_target": original,
        })

        try:
            scale_amf(original)
            rollback_ready = wait_for_amf_ready(original)
        except Exception as rollback_error:
            state["phase"] = "FAILED"
            state["last_error"] = (
                f"{error}; rollback failed: {rollback_error}"
            )
            write_state(state)
            raise

        if not rollback_ready:
            state["phase"] = "FAILED"
            state["last_error"] = (
                f"{error}; rollback readiness timeout"
            )
            write_state(state)
            raise RuntimeError(state["last_error"])

        try:
            set_admission_mode("OPEN")
        except Exception as admission_error:
            append_action_event({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "phase": "ADMISSION_RESET_FAILED",
                "error": str(admission_error),
            })

        write_state(default_state())

        plan["executed"] = False
        plan["controller_phase"] = "IDLE"
        plan["reason"] = f"Scale failed and rolled back: {error}"
        return plan


def execute_recovery_plan(plan):
    state = read_state()
    name = state.get("target_function")
    original = state.get("original_replicas")

    started = datetime.now(timezone.utc).isoformat()

    effect_event = {
        "timestamp": started,
        "phase": "EFFECT_VERIFIED",
        "trigger": plan["source_state"],
        "previous_action": state.get("action"),
        "target_function": name,
        "reason": (
            "Persistent NORMAL evidence confirmed after action"
        ),
    }
    append_action_event(effect_event)

    state["phase"] = "RECOVERY_PENDING"
    write_state(state)

    append_action_event({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "phase": "RECOVERY_PENDING",
        "target_function": name,
        "recovery_target": original,
    })

    try:
        if name and original is not None:
            if name == "amf":
                scale_amf(original)

                if not wait_for_amf_ready(original):
                    raise RuntimeError(
                        "AMF recovery readiness timeout"
                    )
            else:
                scale_nf(name, original)

                if not wait_for_nf_ready(name, original):
                    raise RuntimeError(
                        f"{name.upper()} recovery readiness timeout"
                    )

                if not wait_for_nrf_registration(name, original):
                    raise RuntimeError(
                        f"{name.upper()} recovery NRF timeout"
                    )

        admission = set_admission_mode("OPEN")
        write_state(default_state())

        plan["executed"] = True
        plan["controller_phase"] = "IDLE"
        plan["reason"] = (
            "Effect verified; capacity and admission recovered"
        )

        append_action_event({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "phase": "RECOVERY_VERIFIED",
            "target_function": name,
            "replicas": original,
            "admission": admission,
        })

        return plan

    except Exception as error:
        failed = {
            **state,
            "phase": "FAILED",
            "last_error": str(error),
        }
        write_state(failed)

        append_action_event({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "phase": "RECOVERY_FAILED",
            "target_function": name,
            "error": str(error),
        })

        plan["executed"] = False
        plan["controller_phase"] = "FAILED"
        plan["reason"] = f"Recovery failed: {error}"
        return plan


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
    recoverable_phases = {
        "CAPACITY_VERIFIED",
        "PROTECTION_ACTIVE",
    }

    recovery_candidate = (
        state["phase"] in recoverable_phases
        and decision["state"] == "NORMAL"
        and decision.get("persistent") is True
    )

    if recovery_candidate:
        plan["action"] = "RECOVER"
        plan["reason"] = (
            "Persistent NORMAL evidence verifies the action effect "
            "and permits guarded recovery"
        )
        return plan

    if state["phase"] != "IDLE":
        plan["reason"] = (
            "Controller action is already pending: "
            + state["phase"]
        )
        return plan

    scale_states = {
        "AUSF_PRESSURE": "ausf",
        "UDM_PRESSURE": "udm",
        "UDR_PRESSURE": "udr",
        "PCF_PRESSURE": "pcf",
    }

    target_function = scale_states.get(decision["state"])

    if (
        target_function
        and decision.get("persistent") is True
    ):
        settings = nf_settings(target_function)

        if not settings["eligible"]:
            plan["action"] = "PROTECT_WITH_ADMISSION"
            plan["target_function"] = target_function
            plan["reason"] = (
                f"{target_function.upper()} pressure detected, "
                "but automatic scaling eligibility is not verified"
            )
            return plan

        current_nf = current_nf_replicas(target_function)

        if current_nf >= settings["max_replicas"]:
            plan["reason"] = (
                f"{target_function.upper()} maximum replica "
                "limit reached"
            )
            return plan

        plan["action"] = "SCALE_NF"
        plan["target_function"] = target_function
        plan["current_nf_replicas"] = current_nf
        plan["proposed_nf_replicas"] = current_nf + 1
        plan["reason"] = (
            f"Persistent {target_function.upper()} pressure "
            "passed scaling eligibility and safety guards"
        )

        if DRY_RUN:
            plan["reason"] += "; execution blocked by DRY_RUN"

        return plan

    protection_candidate = (
        decision["state"] == "MONGODB_PRESSURE"
        and decision.get("persistent") is True
    )

    if protection_candidate:
        plan["action"] = "PROTECT_WITH_ADMISSION"
        plan["reason"] = (
            "Persistent MongoDB pressure requires "
            "temporary admission protection"
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
            plan["target_function"] = "amf"
            plan["proposed_amf_replicas"] = current + 1
            plan["reason"] = "Persistent AMF pressure passed safety guards"
            if DRY_RUN:
                plan["reason"] += "; execution blocked by DRY_RUN"
    return plan

def main():
    plan = create_plan(read_latest_decision())

    if not DRY_RUN and not plan["executed"]:
        if plan["action"] == "SCALE_AMF":
            plan = execute_scale_plan(plan)

        elif plan["action"] == "SCALE_NF":
            plan = execute_generic_nf_scale_plan(plan)

        elif plan["action"] == "RECOVER":
            plan = execute_recovery_plan(plan)

        elif plan["action"] == "PROTECT_WITH_ADMISSION":
            result = set_admission_mode(
                "STRONG_PROTECTION"
            )
            state = {
                **default_state(),
                "phase": "PROTECTION_ACTIVE",
                "action": "PROTECT_WITH_ADMISSION",
                "target_function": plan.get("target_function"),
                "original_replicas": None,
                "started_at": datetime.now(timezone.utc).isoformat(),
            }
            write_state(state)

            plan["executed"] = True
            plan["controller_phase"] = "PROTECTION_ACTIVE"
            plan["reason"] = (
                "Strong admission protection activated "
                "for persistent downstream pressure"
            )
            append_action_event({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "phase": "PROTECTION_ACTIVE",
                "trigger": "DOWNSTREAM_PRESSURE",
                "admission": result,
            })

    ACTION_LOG.parent.mkdir(exist_ok=True)
    with ACTION_LOG.open("a") as file:
        file.write(json.dumps(plan) + "\n")
    print(json.dumps(plan, indent=2))

if __name__ == "__main__":
    main()
