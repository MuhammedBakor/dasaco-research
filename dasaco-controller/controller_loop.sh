#!/usr/bin/env bash
set -u

INTERVAL_SECONDS="${INTERVAL_SECONDS:-15}"
LOG_DIR="logs"
LOOP_LOG="$LOG_DIR/controller-loop.log"

mkdir -p "$LOG_DIR"

echo "DA-SACO Controller Loop started in DRY_RUN mode."
echo "Interval: ${INTERVAL_SECONDS} seconds"
echo "Press Ctrl+C to stop."

while true; do
  TIMESTAMP="$(date --iso-8601=seconds)"

  echo "[$TIMESTAMP] Starting control cycle" | tee -a "$LOOP_LOG"

  if ! python3 monitoring_adapter.py --once >> "$LOOP_LOG" 2>&1; then
    echo "[$TIMESTAMP] Monitoring failed, action blocked" | tee -a "$LOOP_LOG"
    sleep "$INTERVAL_SECONDS"
    continue
  fi

  if ! python3 bottleneck_localizer.py >> "$LOOP_LOG" 2>&1; then
    echo "[$TIMESTAMP] Localization failed, action blocked" | tee -a "$LOOP_LOG"
    sleep "$INTERVAL_SECONDS"
    continue
  fi

  if ! python3 action_executor.py >> "$LOOP_LOG" 2>&1; then
    echo "[$TIMESTAMP] Planning failed, action blocked" | tee -a "$LOOP_LOG"
  fi

  echo "[$TIMESTAMP] Control cycle completed" | tee -a "$LOOP_LOG"
  sleep "$INTERVAL_SECONDS"
done
