#!/usr/bin/env bash
set -u
set -o pipefail

OUTPUT_DIR="${1:?Usage: collect_replica_traffic.sh OUTPUT_DIR}"
INTERVAL="${COLLECT_INTERVAL_SECONDS:-2}"
NAMESPACE="${NAMESPACE:-free5gc}"

mkdir -p "$OUTPUT_DIR/pod-logs"
mkdir -p "$OUTPUT_DIR/replica-snapshots"

echo "$$" > "$OUTPUT_DIR/collector.pid"

while true
do
    TIMESTAMP="$(date -u +%Y-%m-%dT%H:%M:%S.%NZ)"

    kubectl get pods \
        -n "$NAMESPACE" \
        -l 'nf in (open5glos,amf,ausf,udm,udr,pcf)' \
        -o custom-columns='FUNCTION:.metadata.labels.nf,POD:.metadata.name,PHASE:.status.phase,READY:.status.containerStatuses[0].ready' \
        --no-headers \
        > "$OUTPUT_DIR/replica-snapshots/latest.txt" \
        2>/dev/null || true

    while read -r function pod phase ready
    do
        [ -n "${pod:-}" ] || continue

        printf '%s\t%s\t%s\t%s\t%s\n' \
            "$TIMESTAMP" \
            "$function" \
            "$pod" \
            "$phase" \
            "$ready" \
            >> "$OUTPUT_DIR/replica-snapshots/timeline.tsv"

        log_file="$OUTPUT_DIR/pod-logs/${function}__${pod}.log"

        {
            echo "===== SNAPSHOT $TIMESTAMP ====="

            kubectl logs \
                -n "$NAMESPACE" \
                "$pod" \
                --all-containers=true \
                --timestamps \
                --since=10s \
                2>/dev/null || true
        } >> "$log_file"

    done < "$OUTPUT_DIR/replica-snapshots/latest.txt"

    sleep "$INTERVAL"
done
