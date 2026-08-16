#!/usr/bin/env bash
set -u
set -o pipefail

ROOT="$HOME/dasaco-research"
CONTROLLER="$ROOT/dasaco-controller"
PACKETRUSHER="$ROOT/packetrusher/repo"

RUN_ID="clean-dasaco-$(date +%Y%m%d-%H%M%S)"
RESULTS="$ROOT/results/final-dasaco/automatic-runs/$RUN_ID"

UE_LOG="$RESULTS/packetrusher-100ue.log"
CONTROLLER_CONSOLE="$RESULTS/controller-console.log"

CONTROLLER_PID=""

mkdir -p "$RESULTS"

cleanup() {
    if [ -n "$CONTROLLER_PID" ]; then
        kill "$CONTROLLER_PID" 2>/dev/null || true
        wait "$CONTROLLER_PID" 2>/dev/null || true
    fi
}

trap cleanup EXIT INT TERM

echo "========================================"
echo "DA-SACO CLEAN AUTOMATIC RUN"
echo "Run ID: $RUN_ID"
echo "========================================"

cd "$CONTROLLER"

echo "[1] Verifying clean baseline"

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

echo "[2] Cleaning run logs"

rm -f \
    logs/monitoring.jsonl \
    logs/parallel-localizer-decisions.jsonl \
    logs/controller-actions.jsonl \
    logs/parallel-controller-loop.log

echo "[3] Resetting 100 subscribers"

kubectl exec -n free5gc mongodb-0 -- \
mongosh --quiet --eval '
db=db.getSiblingDB("free5gc");

const first="imsi-208930000018001";
const last="imsi-208930000018100";

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

if (result.matchedCount != 100) {
  quit(2);
}
'

echo "[4] Starting DA-SACO Parallel Controller"

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

echo "[5] Starting one 100-UE workload"

cd "$PACKETRUSHER"

sudo -n timeout 240 ./packetrusher \
    --config /tmp/dasaco-auto-parallel-100.yml \
    multi-ue -n 100 --tr 50 --nPdu 0 \
    > "$UE_LOG" 2>&1

PACKETRUSHER_RC=$?

if [ "$PACKETRUSHER_RC" -eq 124 ]; then
    echo "[INFO] PacketRusher reached the configured 240-second timeout"
elif [ "$PACKETRUSHER_RC" -ne 0 ]; then
    echo "WARNING: PacketRusher exit=$PACKETRUSHER_RC"
else
    echo "[OK] PacketRusher exited normally"
fi

echo "[6] Waiting for protocol-safe recovery"

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

echo "[7] Saving evidence"

cp logs/monitoring.jsonl \
    "$RESULTS/" 2>/dev/null || true

cp logs/parallel-localizer-decisions.jsonl \
    "$RESULTS/" 2>/dev/null || true

cp logs/controller-actions.jsonl \
    "$RESULTS/" 2>/dev/null || true

cp logs/controller-state.json \
    "$RESULTS/" 2>/dev/null || true

echo "[8] Calculating result"

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
echo "=== AUTOMATIC CONTROL ACTIONS ==="

grep -E \
'"phase": "(CAPACITY_VERIFIED|CAPACITY_USE_VERIFIED|CAPACITY_IDLE|RECOVERY_BLOCKED_ACTIVE_GNB|PARALLEL_RECOVERY_COMPLETE|OPEN5GLOS_DISCOVERY_RESTORED)"' \
logs/controller-actions.jsonl \
2>/dev/null || echo "No scaling action was required"

echo
echo "=== FINAL STATE ==="

cat logs/controller-state.json

echo
echo "[OK] CLEAN DA-SACO RUN COMPLETED"
echo "Results: $RESULTS"
