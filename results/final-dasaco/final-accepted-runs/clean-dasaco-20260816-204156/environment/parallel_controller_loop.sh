#!/usr/bin/env bash
set -u

INTERVAL_SECONDS="${INTERVAL_SECONDS:-15}"
LOG_DIR="logs"
LOOP_LOG="$LOG_DIR/parallel-controller-loop.log"

mkdir -p "$LOG_DIR"

if [ "${DASACO_ACTIVE:-0}" = "1" ]; then
  echo "DA-SACO Parallel Controller started in ACTIVE mode."
else
  echo "DA-SACO Parallel Controller started in DRY_RUN mode."
fi

echo "Interval: ${INTERVAL_SECONDS} seconds"

while true
do
  TIMESTAMP="$(date --iso-8601=seconds)"

  echo "[$TIMESTAMP] Starting parallel cycle" \
  | tee -a "$LOOP_LOG"

  if ! python3 monitoring_adapter.py --once \
    >> "$LOOP_LOG" 2>&1
  then
    echo "[$TIMESTAMP] Monitoring failed" \
    | tee -a "$LOOP_LOG"

    sleep "$INTERVAL_SECONDS"
    continue
  fi

  if ! python3 multi_pressure_localizer.py \
    >> "$LOOP_LOG" 2>&1
  then
    echo "[$TIMESTAMP] Parallel localization failed" \
    | tee -a "$LOOP_LOG"

    sleep "$INTERVAL_SECONDS"
    continue
  fi

  if ! python3 parallel_action_executor.py \
    >> "$LOOP_LOG" 2>&1
  then
    echo "[$TIMESTAMP] Parallel execution failed" \
    | tee -a "$LOOP_LOG"
  fi

  echo "[$TIMESTAMP] Parallel cycle completed" \
  | tee -a "$LOOP_LOG"

  sleep "$INTERVAL_SECONDS"
done
