#!/usr/bin/env bash
set -u
set -o pipefail

OUTPUT_DIR="${1:?Usage: capture_experiment_environment.sh OUTPUT_DIR}"
ROOT="${ROOT:-$HOME/dasaco-research}"
NAMESPACE="${NAMESPACE:-free5gc}"

mkdir -p "$OUTPUT_DIR/environment"
ENV_DIR="$OUTPUT_DIR/environment"

{
    echo "captured_at_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "hostname=$(hostname)"
    echo "kernel=$(uname -srmo)"
    echo "architecture=$(uname -m)"
    echo "cpu_count=$(nproc)"
    echo "memory_bytes=$(awk '/MemTotal/ {print $2 * 1024}' /proc/meminfo)"
} > "$ENV_DIR/host.txt"

{
    echo "=== OS release ==="
    cat /etc/os-release 2>/dev/null || true

    echo
    echo "=== CPU ==="
    lscpu 2>/dev/null || true

    echo
    echo "=== Memory ==="
    free -h 2>/dev/null || true

    echo
    echo "=== Disk ==="
    df -h 2>/dev/null || true
} > "$ENV_DIR/system-details.txt"

{
    echo "=== kubectl client ==="
    kubectl version --client 2>/dev/null || true

    echo
    echo "=== Kubernetes server ==="
    kubectl version 2>/dev/null || true

    echo
    echo "=== Nodes ==="
    kubectl get nodes -o wide 2>/dev/null || true

    echo
    echo "=== Node details ==="
    kubectl describe nodes 2>/dev/null || true
} > "$ENV_DIR/kubernetes.txt"

kubectl get deployments \
    -n "$NAMESPACE" \
    -o wide \
    > "$ENV_DIR/deployments.txt" \
    2>/dev/null || true

kubectl get pods \
    -n "$NAMESPACE" \
    -o wide \
    > "$ENV_DIR/pods.txt" \
    2>/dev/null || true

kubectl get services \
    -n "$NAMESPACE" \
    -o wide \
    > "$ENV_DIR/services.txt" \
    2>/dev/null || true

kubectl get deployments \
    -n "$NAMESPACE" \
    -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{range .spec.template.spec.containers[*]}{.name}{"="}{.image}{" "}{end}{"\n"}{end}' \
    > "$ENV_DIR/container-images.tsv" \
    2>/dev/null || true

{
    echo "=== Python ==="
    python3 --version 2>&1 || true

    echo
    echo "=== Python packages ==="
    python3 -m pip freeze 2>/dev/null || true

    echo
    echo "=== Git ==="
    git --version 2>&1 || true

    echo
    echo "=== Helm ==="
    helm version 2>/dev/null || true

    echo
    echo "=== Container runtime ==="
    crictl --version 2>/dev/null || true
    docker --version 2>/dev/null || true
    containerd --version 2>/dev/null || true
} > "$ENV_DIR/software-versions.txt"

{
    echo "repository=$ROOT"
    echo "branch=$(git -C "$ROOT" branch --show-current 2>/dev/null || true)"
    echo "commit=$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || true)"
    echo "dirty_files=$(git -C "$ROOT" status --porcelain 2>/dev/null | wc -l)"
} > "$ENV_DIR/repository-version.txt"

{
    echo "=== PacketRusher executable information ==="

    PACKETRUSHER_BIN="$ROOT/packetrusher/repo/packetrusher"

    if [ -x "$PACKETRUSHER_BIN" ]; then
        file "$PACKETRUSHER_BIN"
        sha256sum "$PACKETRUSHER_BIN"
        "$PACKETRUSHER_BIN" --version 2>&1 || true
    else
        echo "PacketRusher executable not found"
    fi

    echo
    echo "=== PacketRusher repository ==="

    git -C "$ROOT/packetrusher/repo" \
        rev-parse HEAD 2>/dev/null || true

    git -C "$ROOT/packetrusher/repo" \
        status --short 2>/dev/null || true
} > "$ENV_DIR/packetrusher-version.txt"

{
    echo "workload_ues=100"
    echo "inter_arrival_ms=50"
    echo "pdu_sessions=0"
    echo "timeout_seconds=240"
    echo "subscriber_first=imsi-208930000018001"
    echo "subscriber_last=imsi-208930000018100"
    echo "namespace=$NAMESPACE"
} > "$ENV_DIR/workload-parameters.txt"

CONFIG_SOURCE="$ROOT/configs/packetrusher/dasaco-100ue.yml"

if [ ! -f "$CONFIG_SOURCE" ]; then
    CONFIG_SOURCE="/tmp/dasaco-auto-parallel-100.yml"
fi

if [ -f "$CONFIG_SOURCE" ]; then
    cp "$CONFIG_SOURCE" \
        "$ENV_DIR/packetrusher-config-used.yml"

    sha256sum "$CONFIG_SOURCE" \
        > "$ENV_DIR/packetrusher-config.sha256"
else
    echo "ERROR: PacketRusher configuration not found" \
        > "$ENV_DIR/packetrusher-config-error.txt"
fi

for source in \
    "$ROOT/dasaco-controller/run_clean_dasaco_once.sh" \
    "$ROOT/dasaco-controller/parallel_controller_loop.sh" \
    "$ROOT/dasaco-controller/collect_replica_traffic.sh" \
    "$ROOT/dasaco-controller/analyze_replica_traffic.py" \
    "$ROOT/dasaco-controller/capture_experiment_environment.sh"
do
    if [ -f "$source" ]; then
        cp "$source" "$ENV_DIR/"
    fi
done

sha256sum \
    "$ENV_DIR"/* \
    > "$ENV_DIR/evidence-sha256.txt" \
    2>/dev/null || true

echo "[OK] Experiment environment captured in $ENV_DIR"
