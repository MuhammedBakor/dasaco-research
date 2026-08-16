#!/usr/bin/env bash
set -u
set -o pipefail

ROOT="$HOME/dasaco-research"
CONTROLLER="$ROOT/dasaco-controller"
PACKETRUSHER="$ROOT/packetrusher/repo"
PACKETRUSHER_CONFIG="$ROOT/configs/packetrusher/dasaco-150ue.yml"

RUN_ID="stress-150ue-$(date +%Y%m%d-%H%M%S)"
RESULTS="$ROOT/results/exploratory-stress-dasaco/$RUN_ID"

UE_LOG="$RESULTS/packetrusher-150ue.log"
CONTROLLER_CONSOLE="$RESULTS/controller-console.log"

CONTROLLER_PID=""
COLLECTOR_PID=""

mkdir -p "$RESULTS"
mkdir -p "$ROOT/results/exploratory-stress-dasaco/diagnostic-runs"

cleanup() {
    if [ -n "$COLLECTOR_PID" ]; then
        kill "$COLLECTOR_PID" 2>/dev/null || true
        wait "$COLLECTOR_PID" 2>/dev/null || true
    fi

    if [ -n "$CONTROLLER_PID" ]; then
        kill "$CONTROLLER_PID" 2>/dev/null || true
        wait "$CONTROLLER_PID" 2>/dev/null || true
    fi
}

trap cleanup EXIT INT TERM

echo "========================================"
echo "DA-SACO EXPLORATORY 150-UE STRESS RUN"
echo "Run ID: $RUN_ID"
echo "========================================"

cd "$CONTROLLER"

echo "[1] Creating fresh control-plane state"

for deployment in \
    open5glos \
    free5gc-free5gc-amf-amf \
    free5gc-free5gc-ausf-ausf \
    free5gc-free5gc-udm-udm \
    free5gc-free5gc-udr-udr \
    free5gc-free5gc-pcf-pcf
do
    kubectl rollout restart \
        -n free5gc \
        "deployment/$deployment"
done

for deployment in \
    free5gc-free5gc-amf-amf \
    free5gc-free5gc-ausf-ausf \
    free5gc-free5gc-udm-udm \
    free5gc-free5gc-udr-udr \
    free5gc-free5gc-pcf-pcf \
    open5glos
do
    kubectl rollout status \
        -n free5gc \
        "deployment/$deployment" \
        --timeout=240s
done

echo "[INFO] Waiting for NRF and Open5GLoS convergence"
sleep 20

echo "[2] Verifying clean baseline"

python3 -c '
import action_executor as a

assert a.read_state()["phase"] == "IDLE"

for name in ["amf", "ausf", "udm", "udr", "pcf"]:
    assert a.current_nf_replicas(name) == 1
    assert a.ready_nf_replicas(name) == 1
    assert a.nrf_registered_count(name) == 1

assert a.current_open5glos_replicas() == 1
assert a.ready_open5glos_replicas() == 1

running = a.running_amf_pods()
assert len(running) == 1
assert running.issubset(a.discovered_amf_pods())

pod = a.running_open5glos_pods()[0]
runtime = a.open5glos_runtime(pod)

assert runtime["active_gnb_connections"] == 0
assert runtime["draining"] is False

assert a.set_admission_mode("OPEN")["mode"] == "OPEN"

a.write_state(a.default_state())

print("[OK] Baseline: all functions 1/1")
print("[OK] Admission: OPEN")
print("[OK] Controller: IDLE")
'

echo "[3] Capturing experiment environment"

if [ ! -f "$PACKETRUSHER_CONFIG" ]; then
    echo "ERROR: PacketRusher configuration not found"
    echo "Expected: $PACKETRUSHER_CONFIG"
    exit 1
fi

"$CONTROLLER/capture_experiment_environment.sh" "$RESULTS"     > "$RESULTS/environment-capture-console.log" 2>&1

ENVIRONMENT_RC=$?

if [ "$ENVIRONMENT_RC" -ne 0 ]; then
    echo "ERROR: Environment capture failed with exit=$ENVIRONMENT_RC"
    exit 1
fi

cat > "$RESULTS/environment/stress-experiment.txt" <<EOF
classification=EXPLORATORY_STRESS_RUN
planned_ues=150
inter_arrival_ms=50
pdu_sessions=0
subscriber_first=imsi-208930000018001
subscriber_last=imsi-208930000018150
included_in_primary_comparison=false
purpose=verify-scale-out-scale-in-and-new-replica-use
git_branch=$(git -C "$ROOT" branch --show-current 2>/dev/null || true)
git_commit=$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || true)
EOF

sed -i     's/^workload_ues=.*/workload_ues=150/'     "$RESULTS/environment/workload-parameters.txt"

sed -i     's/^subscriber_last=.*/subscriber_last=imsi-208930000018150/'     "$RESULTS/environment/workload-parameters.txt"

echo "[OK] Experiment environment captured"

echo "[4] Cleaning run logs"

rm -f \
    logs/monitoring.jsonl \
    logs/parallel-localizer-decisions.jsonl \
    logs/controller-actions.jsonl \
    logs/parallel-controller-loop.log

echo "[5] Resetting 150 subscribers"

kubectl exec -n free5gc mongodb-0 -- \
mongosh --quiet --eval '
db=db.getSiblingDB("free5gc");

const first="imsi-208930000018001";
const last="imsi-208930000018150";

db.getCollection(
  "subscriptionData.authenticationData.authenticationStatus"
).deleteMany({
  ueId:{$gte:first,$lte:last}
});

db.getCollection(
  "subscriptionData.contextData.amf3gppAccess"
).deleteMany({
  ueId:{$gte:first,$lte:last}
});

const result=db.getCollection(
  "subscriptionData.authenticationData.authenticationSubscription"
).updateMany(
  {ueId:{$gte:first,$lte:last}},
  {$set:{"sequenceNumber.sqn":"000000000000"}}
);

print("sqnMatched="+result.matchedCount);

if (result.matchedCount != 150) {
  quit(2);
}
'

echo "[6] Starting DA-SACO Parallel Controller"

DASACO_ACTIVE=1 \
INTERVAL_SECONDS=5 \
./parallel_controller_loop.sh \
> "$CONTROLLER_CONSOLE" 2>&1 &

CONTROLLER_PID=$!

sleep 3

if ! kill -0 "$CONTROLLER_PID" 2>/dev/null; then
    echo "ERROR: Parallel Controller failed to start"
    exit 1
fi

echo "[OK] Controller PID=$CONTROLLER_PID"

echo "[7] Starting per-replica traffic collector"

COLLECT_INTERVAL_SECONDS=2 "$CONTROLLER/collect_replica_traffic.sh" "$RESULTS" > "$RESULTS/replica-collector-console.log" 2>&1 &

COLLECTOR_PID=$!

sleep 2

if ! kill -0 "$COLLECTOR_PID" 2>/dev/null; then
    echo "ERROR: Per-replica traffic collector failed to start"
    exit 1
fi

echo "[OK] Replica collector PID=$COLLECTOR_PID"

echo "[8] Starting one exploratory 150-UE workload"

cd "$PACKETRUSHER"

sudo -n timeout 240 ./packetrusher \
    --config "$PACKETRUSHER_CONFIG" \
    multi-ue -n 150 --tr 50 --nPdu 0 \
    > "$UE_LOG" 2>&1

PACKETRUSHER_RC=$?

if [ "$PACKETRUSHER_RC" -eq 124 ]; then
    echo "[INFO] PacketRusher reached the configured 240-second timeout"
elif [ "$PACKETRUSHER_RC" -ne 0 ]; then
    echo "WARNING: PacketRusher exit=$PACKETRUSHER_RC"
else
    echo "[OK] PacketRusher exited normally"
fi

echo "[9] Waiting for protocol-safe recovery"

cd "$CONTROLLER"

DEADLINE=$((SECONDS + 480))
RECOVERED=0

while [ "$SECONDS" -lt "$DEADLINE" ]; do
    STATUS="$(python3 -c '
import action_executor as a
import parallel_action_executor as p

phase = a.read_state()["phase"]
active, _ = p.active_gnb_connection_summary()

replicas = {
    "open5glos": a.current_open5glos_replicas(),
    "amf": a.current_nf_replicas("amf"),
    "ausf": a.current_nf_replicas("ausf"),
    "udm": a.current_nf_replicas("udm"),
    "udr": a.current_nf_replicas("udr"),
    "pcf": a.current_nf_replicas("pcf"),
}

all_one = all(value == 1 for value in replicas.values())

print(
    phase,
    active,
    int(all_one),
    replicas,
)
')"

    echo "$STATUS"

    PHASE="$(printf '%s\n' "$STATUS" | awk '{print $1}')"
    ACTIVE="$(printf '%s\n' "$STATUS" | awk '{print $2}')"
    ALL_ONE="$(printf '%s\n' "$STATUS" | awk '{print $3}')"

    if [ "$ACTIVE" = "0" ] && [ "$ALL_ONE" = "1" ]; then
        if python3 -c '
import action_executor as a

running = a.running_amf_pods()

assert len(running) == 1
raise SystemExit(
    0
    if running.issubset(a.discovered_amf_pods())
    else 1
)
'
        then
            python3 -c '
import action_executor as a

assert a.set_admission_mode("OPEN")["mode"] == "OPEN"
a.write_state(a.default_state())

print("[OK] Functional baseline verified")
'
        else
            echo "[INFO] Restoring Open5GLoS AMF discovery"

            kubectl rollout restart \
                -n free5gc \
                deployment/open5glos

            kubectl rollout status \
                -n free5gc \
                deployment/open5glos \
                --timeout=180s

            sleep 15

            python3 -c '
import action_executor as a

running = a.running_amf_pods()

assert len(running) == 1
assert running.issubset(a.discovered_amf_pods())

pod = a.running_open5glos_pods()[0]
runtime = a.open5glos_runtime(pod)

assert runtime["active_gnb_connections"] == 0
assert runtime["draining"] is False
assert a.set_admission_mode("OPEN")["mode"] == "OPEN"

a.write_state(a.default_state())

print("[OK] Discovery fallback completed")
'
        fi

        RECOVERED=1
        break
    fi

    sleep 5
done

if [ "$RECOVERED" != "1" ]; then
    echo "ERROR: Recovery did not finish within 480 seconds"
    exit 1
fi

echo "[10] Stopping per-replica traffic collector"

if [ -n "$COLLECTOR_PID" ]; then
    kill "$COLLECTOR_PID" 2>/dev/null || true
    wait "$COLLECTOR_PID" 2>/dev/null || true
    COLLECTOR_PID=""
fi

echo "[11] Preparing controller evidence for traffic analysis"

cp logs/controller-actions.jsonl     "$RESULTS/" 2>/dev/null || true

cp logs/controller-state.json     "$RESULTS/" 2>/dev/null || true

echo "[11] Analyzing per-replica traffic"

python3 "$CONTROLLER/analyze_replica_traffic.py"     --run-dir "$RESULTS"     > "$RESULTS/per-replica-analysis-console.log" 2>&1

ANALYZER_RC=$?

if [ "$ANALYZER_RC" -ne 0 ]; then
    echo "WARNING: Per-replica analyzer exit=$ANALYZER_RC"
else
    cat "$RESULTS/per-replica-traffic.txt"
fi

echo "[12] Saving evidence"

cp logs/monitoring.jsonl \
    "$RESULTS/" 2>/dev/null || true

cp logs/parallel-localizer-decisions.jsonl \
    "$RESULTS/" 2>/dev/null || true

cp logs/controller-actions.jsonl \
    "$RESULTS/" 2>/dev/null || true

cp logs/controller-state.json \
    "$RESULTS/" 2>/dev/null || true

echo "[13] Calculating result"

STARTED="$(
    grep -c \
    "TESTING REGISTRATION USING IMSI" \
    "$UE_LOG" || true
)"

ACCEPTS="$(
    grep -c \
    "Receive Registration Accept" \
    "$UE_LOG" || true
)"

COMPLETES="$(
    grep -c \
    "Initiating Configuration Update Complete" \
    "$UE_LOG" || true
)"

REJECTS="$(
    grep -c \
    "Receive Registration Reject" \
    "$UE_LOG" || true
)"

AMF_STATUS="$(
    grep -c \
    "Receive AMF Status Indication" \
    "$UE_LOG" || true
)"

{
    echo "Run ID: $RUN_ID"
    echo "Started=$STARTED"
    echo "Accepts=$ACCEPTS"
    echo "Completes=$COMPLETES"
    echo "Rejects=$REJECTS"
    echo "AMF_Status=$AMF_STATUS"
} | tee "$RESULTS/summary.txt"

echo
echo "=== RUN QUALIFICATION ==="

UNKNOWN_RAN="$(
    grep -c         "Cannot send DownlinkNASTransport message to UE with RANUEID"         "$UE_LOG" || true
)"

FULL_COMPLETION=false
PERFECT_SERVICE=false
INFRASTRUCTURE_FAILURE=false
QUALIFICATION="EXPLORATORY_STRESS_RUN"
QUALIFICATION_REASON="supplementary-scalability-demonstration"

if [ "$COMPLETES" -ge 150 ]; then
    FULL_COMPLETION=true
fi

if     [ "$COMPLETES" -ge 150 ] &&     [ "$REJECTS" -eq 0 ] &&     [ "$AMF_STATUS" -eq 0 ] &&     [ "$UNKNOWN_RAN" -eq 0 ]
then
    PERFECT_SERVICE=true
fi

if [ "$STARTED" -ne 150 ]; then
    INFRASTRUCTURE_FAILURE=true
    QUALIFICATION="INVALID_EXPLORATORY_INFRASTRUCTURE_RUN"
    QUALIFICATION_REASON="planned-workload-not-started"
elif [ "$UNKNOWN_RAN" -ne 0 ]; then
    INFRASTRUCTURE_FAILURE=true
    QUALIFICATION="INVALID_EXPLORATORY_INFRASTRUCTURE_RUN"
    QUALIFICATION_REASON="unknown-ran-ue-context"
fi

{
    echo "accept_events=$ACCEPTS"
    echo "complete_events=$COMPLETES"
    echo "unknown_ran_ue_errors=$UNKNOWN_RAN"
    echo "qualification=$QUALIFICATION"
    echo "qualification_reason=$QUALIFICATION_REASON"
    echo "infrastructure_failure=$INFRASTRUCTURE_FAILURE"
    echo "full_completion=$FULL_COMPLETION"
    echo "perfect_service=$PERFECT_SERVICE"
} >> "$RESULTS/summary.txt"

echo "Qualification=$QUALIFICATION"
echo "Infrastructure_failure=$INFRASTRUCTURE_FAILURE"
echo "Full_completion=$FULL_COMPLETION"
echo "Perfect_service=$PERFECT_SERVICE"
echo "Unknown_RAN_UE_errors=$UNKNOWN_RAN"

if [ "$QUALIFICATION" = "INVALID_EXPLORATORY_INFRASTRUCTURE_RUN" ]; then
    DESTINATION="$ROOT/results/exploratory-stress-dasaco/diagnostic-runs/$RUN_ID"

    rm -rf "$DESTINATION"
    mv "$RESULTS" "$DESTINATION"

    echo "ERROR: Infrastructure-invalid run"
    echo "Diagnostic evidence moved to:"
    echo "$DESTINATION"

    exit 2
fi

{
    echo "planned_ues=150"
    echo "classification=EXPLORATORY_STRESS_RUN"
    echo "included_in_primary_comparison=false"
    echo "purpose=verify-scale-out-scale-in-and-new-replica-use"
} >> "$RESULTS/summary.txt"

echo "[OK] Exploratory stress run is experimentally valid"

echo
echo "=== AUTOMATIC CONTROL ACTIONS ==="

grep -E \
'"phase": "(CAPACITY_VERIFIED|CAPACITY_USE_VERIFIED|CAPACITY_IDLE|RECOVERY_BLOCKED_ACTIVE_GNB|PARALLEL_RECOVERY_COMPLETE|OPEN5GLOS_DISCOVERY_RESTORED)"' \
logs/controller-actions.jsonl \
2>/dev/null || echo "No scaling action was required"

echo
echo "=== FINAL STATE ==="

cat logs/controller-state.json

echo
echo "[OK] EXPLORATORY 150-UE DA-SACO RUN COMPLETED"
echo "Results: $RESULTS"
