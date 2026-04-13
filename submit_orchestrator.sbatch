#!/bin/bash
#SBATCH --job-name=orchestrator         # Job name
#SBATCH --nodes=1                       # Number of nodes
#SBATCH --ntasks=1                      # Number of tasks
#SBATCH --cpus-per-task=1               # CPUs for the python watcher
#SBATCH --mem=4gb                       # Memory
#SBATCH --partition=msilong             # Specific long-duration CPU queue
#SBATCH --time=4-00:00:00               # Time (Shortened to bypass maintenance hold)
#SBATCH --output=logs/%j_orchestrator.out
#SBATCH --error=logs/%j_orchestrator.err
#SBATCH --mail-type=BEGIN,END,FAIL
#SBATCH --mail-user=song0837@umn.edu

# No GPU is requested here! This is a pure CPU node.

echo "Deploying the Master Orchestrator onto SLURM..."

# Setup environment just like the training jobs
module purge
module unload python 2>/dev/null || true

if [ -f "/users/7/$USER/miniconda3/etc/profile.d/conda.sh" ]; then
    source /users/7/$USER/miniconda3/etc/profile.d/conda.sh
else
    module load conda
fi
conda activate /projects/standard/ztchen/shared/yilong/conda_envs/lerobot-shared

export PATH="/users/7/$USER/.local/bin:$PATH"
export PYTHONNOUSERSITE=1
unset LD_PRELOAD
export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$LD_LIBRARY_PATH

# Execute the infinite loop
# Because sbatch jobs automatically run in the background tied to the cluster,
# you will never have to worry about a tmux session disconnecting!
bash run_orchestrator.sh
