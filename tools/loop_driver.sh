#!/usr/bin/env bash
# tools/loop_driver.sh
# Continuous execution driver for WebLens Autonomous Quality Loop (v8 Part A2)

MAX_RESTARTS_PER_HOUR=10
INITIAL_BACKOFF=5
MAX_BACKOFF=60
LOG_FILE="evidence/loop/driver.log"
STATE_FILE="evidence/loop/STATE.json"
STOP_FILE="STOP"
PAUSE_FILE="PAUSE"
DONE_FILE="evidence/loop/DONE"

log_msg() {
    local timestamp
    timestamp=$(date -Iseconds)
    echo "[$timestamp] $1" | tee -a "$LOG_FILE"
}

log_msg "WebLens Loop Driver started (Bash)."

restarts=0
hour_start=$(date +%s)
backoff=$INITIAL_BACKOFF

while true; do
    if [ -f "$STOP_FILE" ]; then
        log_msg "STOP file detected. Ending loop gracefully."
        break
    fi

    if [ -f "$DONE_FILE" ]; then
        log_msg "DONE file detected. All stop rules achieved."
        break
    fi

    if [ -f "$PAUSE_FILE" ]; then
        log_msg "PAUSE file detected. Waiting 10 seconds..."
        sleep 10
        continue
    fi

    now=$(date +%s)
    if [ $((now - hour_start)) -ge 3600 ]; then
        restarts=0
        hour_start=$now
    fi

    if [ $restarts -ge $MAX_RESTARTS_PER_HOUR ]; then
        log_msg "WARNING: Exceeded $MAX_RESTARTS_PER_HOUR restarts this hour. Backing off 300 seconds."
        sleep 300
        continue
    fi

    if [ ! -f "$STATE_FILE" ]; then
        log_msg "ERROR: State file $STATE_FILE does not exist. Halting driver."
        break
    fi

    log_msg "Executing cycle tests..."
    python3 -m pytest tests/test_01_static_and_deps.py tests/test_02_mcp_protocol.py tests/test_03_security_boundaries.py tests/test_04_fuzz_and_chaos.py tests/test_05_extraction_quality.py tests/test_06_performance_stress.py -q
    exit_code=$?

    if [ $exit_code -eq 0 ]; then
        log_msg "Cycle execution completed successfully."
        backoff=$INITIAL_BACKOFF
    else
        restarts=$((restarts + 1))
        log_msg "Cycle step exited with code $exit_code. Backing off ${backoff}s."
        sleep $backoff
        backoff=$((backoff * 2))
        if [ $backoff -gt $MAX_BACKOFF ]; then
            backoff=$MAX_BACKOFF
        fi
    fi

    sleep 2
done

log_msg "WebLens Loop Driver terminated."

