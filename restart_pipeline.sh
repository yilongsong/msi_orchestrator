#!/bin/bash
echo "Initiating Complete Cluster and Pipeline Purge..."

# 1. Kill everything dynamically for the user
echo "Killing all hanging SLURM processes..."
scancel -u $USER

# 2. Wipe environment logs securely
echo "Sweeping runtime crash caches..."
rm -rf /projects/standard/ztchen/shared/yilong/orchestrator/logs/* 2>/dev/null
rm -rf /projects/standard/ztchen/shared/yilong/orchestrator/sbatch_scripts/* 2>/dev/null

# 3. Dynamically slice the JSON array
echo "Decoupling Ghost Strings from experiments.json..."
python3 -c "
import json
import os
f = '/projects/standard/ztchen/shared/yilong/orchestrator/experiments.json'
try:
    with open(f, 'r') as file:
        d = json.load(file)
    for k, v in d.items():
        if isinstance(v, dict) and 'job_id' in v:
            v['job_id'] = None
    with open(f, 'w') as file:
        json.dump(d, file, indent=2)
except Exception as e:
    print('Failed to wipe json constraints:', e)
"

# 4. Reignite cluster
echo "Igniting primary Orchestrator loop..."
sbatch /projects/standard/ztchen/shared/yilong/orchestrator/submit_orchestrator.sbatch
echo "Done!"
