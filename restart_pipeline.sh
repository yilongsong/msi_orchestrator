#!/bin/bash
echo "Initiating Complete Cluster and Pipeline Purge..."

# 1. Kill everything dynamically for the user
echo "Killing all hanging SLURM processes..."
scancel -u $USER

# 2 and 3. Dynamically slice the JSON array and wipe user logs
echo "Decoupling Ghost Strings from experiments.json and clearing user logs..."
python3 -c "
import json
import os
import glob
USER = os.environ.get('USER', '')
f = '/projects/standard/ztchen/shared/yilong/orchestrator/experiments.json'
try:
    with open(f, 'r') as file:
        d = json.load(file)
    for k, v in d.items():
        if isinstance(v, dict) and 'owner' in v and v['owner'] == USER:
            if 'job_id' in v:
                v['job_id'] = None
            # Wipe only this user's logs and sbatch scripts
            for log_file in glob.glob(f'/projects/standard/ztchen/shared/yilong/orchestrator/logs/**/*_{k}.*', recursive=True):
                try: os.remove(log_file)
                except: pass
            for sbatch_file in glob.glob(f'/projects/standard/ztchen/shared/yilong/orchestrator/sbatch_scripts/{k}.sbatch'):
                try: os.remove(sbatch_file)
                except: pass
    with open(f, 'w') as file:
        json.dump(d, file, indent=2)
except Exception as e:
    print('Failed to wipe json constraints:', e)
"

# 4. Reignite cluster
echo "Igniting primary Orchestrator loop..."
sbatch /projects/standard/ztchen/shared/yilong/orchestrator/submit_orchestrator.sbatch
echo "Done!"
