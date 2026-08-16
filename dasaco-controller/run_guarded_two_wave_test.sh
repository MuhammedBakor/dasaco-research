#!/usr/bin/env bash
set -u
set -o pipefail

ROOT="$HOME/dasaco-research"
CONTROLLER="$ROOT/dasaco-controller"
PACKETRUSHER="$ROOT/packetrusher/repo"

RUN_ID="auto-parallel-final-$(date +%Y%m%d-%H%M%S)"
RESULTS="$ROOT/results/final-dasaco/automatic-runs/$RUN_ID"

WAVE1_LOG="$RESULTS/wave1.log"
WAVE2_LOG="$RESULTS/wave2.log"
CONTROLLER_LOG="$RESULTS/controller-console.log"

WAVE1_CONFIG="/tmp/dasaco-auto-parallel-100.yml"
WAVE2_CONFIG="/tmp/dasaco-run3-wave2.yml"

CONTROLLER_PID=""
WAVE1_PID=""
WAVE2_PID=""

mkdir -p "$RESULTS"
echo "$RUN_ID" > /tmp/dasaco-current-run-id

cleanup() {
    if [ -n "$WAVE1_PID" ]; then
        kill "$WAVE1_PID" 2>/dev/null || true
    fi

    if [ -n "$WAVE2_PID" ]; then
        kill "$WAVE2_PID" 2>/dev/null || true
    fi

    if [ -n "$CONTROLLER_PID" ]; then
        kill "$CONTROLLER_PID" 2>/dev/null || true
    fi
}

trap cleanup EXIT INT TERM

echo "Run ID: $RUN_ID"

cd "$CONTROLLER"

python3 - <<'PY'
import action_executor as a

assert a.read_state()["phase"] == "IDLE"

for name in ["amf", "ausf", "udm", "udr", "pcf"]:
    assert a.current_nf_replicas(name) == 1
    assert a.ready_nf_replicas(name) == 1
    assert a.nrf_registered_count(name) == 1

assert a.current_open5glos_replicas() == 1
assert a.ready_open5glos_replicas() == 1

pod = a.running_open5glos_pods()[0]
runtime = a.open5glos_runtime(pod)

assert runtime["active_gnb_connections"] == 0
assert runtime["draining"] is False

admission = a.set_admission_mode("OPEN")
assert admission["mode"] == "OPEN"

print("[OK] Clean baseline verified")
PY

echo "[1] Resetting subscribers"

kubectl exec -n free5gc mongodb-0 -- \
mongosh --quiet --eval '
db=db.getSiblingDB("free5gc");

const ranges=[
  ["imsi-208930000018001","imsi-208930000018100"],
  ["imsi-208930000017001","imsi-208930000017100"]
];

for (const range of ranges) {
  db.getCollection(
    "subscriptionData.authenticationData.authenticationStatus"
  ).deleteMany({
    ueId:{$gte:range[0],$lte:range[1]}
  });

  db.getCollection(
    "subscriptionData.contextData.amf3gppAccess"
  ).deleteMany({
    ueId:{$gte:range[0],$lte:range[1]}
  });

  const result=db.getCollection(
    "subscriptionData.authenticationData.authenticationSubscription"
  ).updateMany(
    {ueId:{$gte:range[0],$lte:range[1]}},
    {$set:{"sequenceNumber.sqn":"000000000000"}}
  );

  print(
    range[0]+".."+range[1]+
    " matched="+result.matchedCount
  );
}
'

echo "[2] Starting Parallel DA-SACO"

cd "$CONTROLLER"

DASACO_ACTIVE=1 INTERVAL_SECONDS=15 \
./parallel_controller_loop.sh \
> "$CONTROLLER_LOG" 2>&1 &

CONTROLLER_PID=$!

sleep 3

if ! kill -0 "$CONTROLLER_PID" 2>/dev/null; then
    echo "ERROR: Controller failed to start"
    exit 1
fi

echo "[3] Starting Wave 1 once"

cd "$PACKETRUSHER"

sudo -n timeout 240 ./packetrusher \
    --config "$WAVE1_CONFIG" \
    multi-ue -n 100 --tr 50 --nPdu 0 \
    > "$WAVE1_LOG" 2>&1 &

WAVE1_PID=$!

echo "Wave 1 PID=$WAVE1_PID"
echo "[4] Waiting for fully verified scale-out"

READY_DEADLINE=$((SECONDS + 210))
SCALE_READY=0

while [ "$SECONDS" -lt "$READY_DEADLINE" ]; do
    PHASE="$(
        cd "$CONTROLLER" &&
        python3 - <<'PY'
import action_executor as a
print(a.read_state()["phase"])
PY
    )"

    REPLICA_STATE="$(
        kubectl get deployment -n free5gc \
        free5gc-free5gc-amf-amf \
        free5gc-free5gc-ausf-ausf \
        free5gc-free5gc-udm-udm \
        free5gc-free5gc-udr-udr \
        free5gc-free5gc-pcf-pcf \
        -o jsonpath='{range .items[*]}{.spec.replicas}{"="}{.status.readyReplicas}{" "}{end}'
    )"

    READY_MATCH="$(
        printf '%s\n' "$REPLICA_STATE" |
        awk '
        {
          scaled=0;
          valid=1;

          for (i=1; i<=NF; i++) {
            split($i, values, "=");

            if (values[1] > 1)
              scaled=1;

            if (values[1] != values[2])
              valid=0;
          }
        }

        END {
          print scaled && valid ? 1 : 0;
        }'
    )"

    ADMISSION="$(
        cd "$CONTROLLER" &&
        python3 - <<'PY'
import action_executor as a

modes = []

for pod in a.running_open5glos_pods():
    value = a.call_open5glos_pod_api(
        pod,
        "admission",
    )
    modes.append(value["mode"])

print(
    "OPEN"
    if modes and all(mode == "OPEN" for mode in modes)
    else "NOT_OPEN"
)
PY
    )"

    echo \
      "phase=$PHASE replicas='$REPLICA_STATE' admission=$ADMISSION"

    if \
        [ "$PHASE" = "PARALLEL_CAPACITY_VERIFIED" ] &&
        [ "$READY_MATCH" = "1" ] &&
        [ "$ADMISSION" = "OPEN" ]
    then
        SCALE_READY=1
        break
    fi

    sleep 3
done

if [ "$SCALE_READY" != "1" ]; then
    echo "ERROR: Fully verified scale-out was not reached"
    exit 1
fi

echo "[OK] Scale-out fully Ready and verified"

kubectl get deployment -n free5gc \
    free5gc-free5gc-amf-amf \
    free5gc-free5gc-ausf-ausf \
    free5gc-free5gc-udm-udm \
    free5gc-free5gc-udr-udr \
    free5gc-free5gc-pcf-pcf \
    -o custom-columns='NAME:.metadata.name,DESIRED:.spec.replicas,READY:.status.readyReplicas'

echo "[5] Starting Wave 2 once"

cd "$PACKETRUSHER"

sudo -n timeout 240 ./packetrusher \
    --config "$WAVE2_CONFIG" \
    multi-ue -n 100 --tr 50 --nPdu 0 \
    > "$WAVE2_LOG" 2>&1 &

WAVE2_PID=$!

echo "Wave 2 PID=$WAVE2_PID"

wait "$WAVE1_PID" || true
WAVE1_PID=""

wait "$WAVE2_PID" || true
WAVE2_PID=""

echo "[6] Both waves ended"
echo "[7] Waiting for guarded recovery"

RECOVERY_DEADLINE=$((SECONDS + 480))
RECOVERED=0

while [ "$SECONDS" -lt "$RECOVERY_DEADLINE" ]; do
    STATUS="$(
        cd "$CONTROLLER" &&
        python3 - <<'PY'
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
PY
    )"

    echo "$STATUS"

    PHASE="$(printf '%s\n' "$STATUS" | awk '{print $1}')"
    ACTIVE="$(printf '%s\n' "$STATUS" | awk '{print $2}')"
    ALL_ONE="$(printf '%s\n' "$STATUS" | awk '{print $3}')"

    if \
        [ "$PHASE" = "IDLE" ] &&
        [ "$ACTIVE" = "0" ] &&
        [ "$ALL_ONE" = "1" ]
    then
        RECOVERED=1
        break
    fi

    sleep 5
done

if [ "$RECOVERED" != "1" ]; then
    echo "ERROR: Guarded recovery did not complete"
    exit 1
fi

echo "[OK] Guarded recovery completed"

cp "$CONTROLLER/logs/monitoring.jsonl" \
    "$RESULTS/" 2>/dev/null || true

cp "$CONTROLLER/logs/parallel-localizer-decisions.jsonl" \
    "$RESULTS/" 2>/dev/null || true

cp "$CONTROLLER/logs/controller-actions.jsonl" \
    "$RESULTS/" 2>/dev/null || true

echo "=== Wave 1 results ==="
echo "Started=$(grep -c 'TESTING REGISTRATION USING IMSI' "$WAVE1_LOG")"
echo "Accepts=$(grep -c 'Receive Registration Accept' "$WAVE1_LOG")"
echo "Completes=$(grep -c 'Initiating Configuration Update Complete' "$WAVE1_LOG")"
echo "Rejects=$(grep -c 'Receive Registration Reject' "$WAVE1_LOG")"
echo "AMF_Status=$(grep -c 'Receive AMF Status Indication' "$WAVE1_LOG")"

echo "=== Wave 2 results ==="
echo "Started=$(grep -c 'TESTING REGISTRATION USING IMSI' "$WAVE2_LOG")"
echo "Accepts=$(grep -c 'Receive Registration Accept' "$WAVE2_LOG")"
echo "Completes=$(grep -c 'Initiating Configuration Update Complete' "$WAVE2_LOG")"
echo "Rejects=$(grep -c 'Receive Registration Reject' "$WAVE2_LOG")"
echo "AMF_Status=$(grep -c 'Receive AMF Status Indication' "$WAVE2_LOG")"

echo "=== Traffic-use evidence ==="

grep -E \
'CAPACITY_USE_VERIFIED|CAPACITY_IDLE|RECOVERY_BLOCKED_ACTIVE_GNB' \
"$CONTROLLER/logs/controller-actions.jsonl" \
| tail -n 40

echo
echo "[OK] Run completed: $RUN_ID"
echo "Results: $RESULTS"
