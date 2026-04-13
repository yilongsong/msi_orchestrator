#!/bin/bash
# run_orchestrator.sh
# 
# This script runs the orchestrator daemon in an infinite loop.
# It is recommended to run this script inside a tmux or screen session.
# Example:
#   tmux new -s orchestrator
#   ./run_orchestrator.sh
#   (Ctrl+B, D to detach)

# Sleep duration in seconds between checks (e.g., 3600 = 1 hour)
SLEEP_DURATION=3600
POLL_INTERVAL=10

umask 0002

# Ensure logs directory exists
mkdir -p logs

echo "Starting Orchestrator daemon..."
echo "It will wake up immediately if you edit experiments.json,"
echo "OR every $(($SLEEP_DURATION / 60)) minutes to routinely check jobs."
echo "Press Ctrl+C to stop."
echo "=========================================="

last_check_time=0
last_mod_time=0

while true; do
  current_time=$(date +%s)
  current_mod_time=$(stat -c %Y experiments.json 2>/dev/null || echo 0)
  
  time_since_check=$((current_time - last_check_time))
  
  if [ "$time_since_check" -ge "$SLEEP_DURATION" ] || [ "$current_mod_time" -gt "$last_mod_time" ]; then
    if [ "$current_mod_time" -gt "$last_mod_time" ] && [ "$last_check_time" -ne 0 ]; then
        echo "Detected manual change to experiments.json! Running orchestrator..."
    else
        echo "Running scheduled routine check..."
    fi

    python orchestrator.py
    
    last_check_time=$(date +%s)
    # Get the new modification time because python orchestrator.py might have modified it implicitly
    last_mod_time=$(stat -c %Y experiments.json 2>/dev/null || echo 0)
  fi
  
  sleep $POLL_INTERVAL
done
