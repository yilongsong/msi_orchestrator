#!/bin/bash
echo "Restarting Orchestrator Daemon for $USER..."

# Safely kill ONLY the orchestrator job, leaving active ML train jobs alone
echo "Terminating active orchestrator daemon (if any)..."
scancel -u $USER -n orchestrator
sleep 1

# Launch a new orchestrator pipeline
echo "Deploying fresh orchestrator daemon..."
sbatch /projects/standard/ztchen/shared/yilong/orchestrator/submit_orchestrator.sbatch

echo "Orchestrator successfully bounced back up!"
