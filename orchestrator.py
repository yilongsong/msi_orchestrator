import json
import os
import subprocess
import time
import glob
import shutil
from datetime import datetime

try:
    from safetensors import safe_open
except ImportError:
    safe_open = None

CONFIG_FILE = "experiments.json"
SBATCH_DIR = "sbatch_scripts"
LOGS_DIR = "logs"
USER = os.environ.get("USER", "song0837")

def load_configs():
    if not os.path.exists(CONFIG_FILE):
        return {}
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)

def save_configs(configs):
    with open(CONFIG_FILE, "w") as f:
        json.dump(configs, f, indent=2)

def get_running_jobs():
    """Returns a dictionary mapping exp_name to Job ID for active Jobs."""
    running = {}
    try:
        result = subprocess.run(
            ["squeue", "-u", USER, "-h", "-o", "%i %250j"], 
            capture_output=True, text=True, check=True
        )
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if not line: continue
            parts = line.split(maxsplit=1)
            if len(parts) == 2:
                running[parts[1].strip()] = parts[0]
        return running
    except subprocess.CalledProcessError as e:
        print(f"Error calling squeue: {e}")
        return running

def find_log_file(job_id, exp_name):
    pattern = os.path.join(LOGS_DIR, "**", f"{job_id}_{exp_name}.err")
    matches = glob.glob(pattern, recursive=True)
    if matches:
        return matches[0]
    return os.path.join(LOGS_DIR, f"{job_id}_{exp_name}.err")

def did_job_timeout(job_id, exp_name):
    """
    Checks the error log for a given job to see if it was cancelled
    due to a time limit (SLURM 24hr cancellation limit).
    """
    err_log = find_log_file(job_id, exp_name)
    if not os.path.exists(err_log):
        print(f"WARNING: Log file {err_log} not found.")
        return False
        
    try:
        with open(err_log, "r") as f:
            content = f.read()
            if "DUE TO TIME LIMIT" in content:
                return True
    except Exception as e:
        print(f"Error reading log file {err_log}: {e}")
        return False
        
    return False

def check_if_reached_1m(job_id, exp_name):
    """
    Checks the log to see if the job exit gracefully or reached 1000000 steps.
    """
    err_log = find_log_file(job_id, exp_name)
    if not os.path.exists(err_log):
        return False
        
    try:
        with open(err_log, "r") as f:
            content = f.read()
            if "step:1000K" in content or "step:1000000" in content:
                return True
    except Exception as e:
        pass
    return False

def get_total_frames(repo_path, episodes_str=None):
    if not os.path.isabs(repo_path):
        repo_path = os.path.expanduser(f"~/.cache/huggingface/lerobot/{repo_path}")
        
    info_path = os.path.join(repo_path, "meta", "info.json")
    if not os.path.exists(info_path):
        return None
        
    try:
        if not episodes_str:
            with open(info_path) as f:
                info = json.load(f)
            return info.get("total_frames")
            
        import ast
        try:
            episodes_list = ast.literal_eval(episodes_str)
        except Exception:
            with open(info_path) as f:
                info = json.load(f)
            return info.get("total_frames")
            
        episodes_path = os.path.join(repo_path, "meta", "episodes.jsonl")
        if not os.path.exists(episodes_path):
            with open(info_path) as f:
                info = json.load(f)
            return info.get("total_frames")
            
        total = 0
        with open(episodes_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line: continue
                ep_data = json.loads(line)
                if ep_data.get("episode_index") in episodes_list:
                    total += ep_data.get("length", 0)
        return total if total > 0 else None
    except Exception as e:
        print(f"Error calculating frames: {e}")
        return None

def get_epochs_for_run(exp_name, dataset_repo, episodes_str=None):
    output_dir = f"/projects/standard/ztchen/shared/yilong/outputs/{exp_name}"
    checkpoints_dir = os.path.join(output_dir, "checkpoints")
    
    if not os.path.exists(checkpoints_dir):
        return 0.0, 0
    
    highest_step = 0
    latest_ckpt_path = None
    for subdir in os.listdir(checkpoints_dir):
        if subdir.isdigit():
            step_val = int(subdir)
            if step_val > highest_step:
                highest_step = step_val
                latest_ckpt_path = os.path.join(checkpoints_dir, subdir)
            
    if highest_step == 0 or latest_ckpt_path is None:
        return 0.0, 0
        
    cfg_path = os.path.join(latest_ckpt_path, "pretrained_model", "train_config.json")
    safe_tensor_path = os.path.join(latest_ckpt_path, "pretrained_model", "model.safetensors")
    if not os.path.exists(cfg_path) or not os.path.exists(safe_tensor_path):
        return 0.0, 0
        
    try:
        with open(cfg_path) as f:
            cfg = json.load(f)
        batch_size = cfg.get("batch_size")
        if not batch_size: return 0.0, highest_step
    except Exception:
        return 0.0, highest_step
        
    total_frames = get_total_frames(dataset_repo, episodes_str)
    if not total_frames: 
        return 0.0, highest_step
        
    return (highest_step * batch_size) / total_frames, highest_step

def get_cluster_states():
    """Returns a dictionary mapping exp_name to dict of Slurm info."""
    states = {}
    try:
        result = subprocess.run(
            ["squeue", "-h", "-o", "%i %250j %T %M %N"], 
            capture_output=True, text=True, check=True
        )
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if not line: continue
            parts = line.split()
            if len(parts) >= 4:
                job_id = parts[0]
                exp_name = parts[1]
                state = parts[2]
                time_str = parts[3]
                node = parts[4] if len(parts) > 4 else ""
                states[exp_name] = {"job_id": job_id, "state": state, "time": time_str, "node": node}
        return states
    except Exception as e:
        print(f"Error calling squeue for telemetry: {e}")
        return states

def generate_telemetry():
    configs = load_configs()
    cluster_states = get_cluster_states()
    telemetry = {}
    
    for exp_name, exp_data in configs.items():
        if not isinstance(exp_data, dict): continue
        target_epochs = exp_data.get('target', 500)
        
        job_info = cluster_states.get(exp_name, {})
        dataset_repo = exp_data.get('dataset_repo_id', '')
        episodes_str = exp_data.get('episodes')
        current_epochs, step_val = get_epochs_for_run(exp_name, dataset_repo, episodes_str)
        
        telemetry[exp_name] = {
            "slurm_state": job_info.get("state", "NONE"),
            "slurm_time": job_info.get("time", ""),
            "slurm_node": job_info.get("node", ""),
            "epochs": round(current_epochs, 2) if current_epochs else 0,
            "target": target_epochs
        }
        
    with open("status.json", "w") as f:
        json.dump(telemetry, f, indent=2)


def create_and_submit_sbatch(exp_name, config_data, resume=False):
    """Creates an sbatch script and submits it, returning the newly assigned job ID."""
    os.makedirs(SBATCH_DIR, exist_ok=True)
    
    date_str = datetime.now().strftime("%Y-%m-%d")
    current_logs_dir = os.path.join(LOGS_DIR, f"{date_str}_{USER}")
    os.makedirs(current_logs_dir, exist_ok=True)
    
    sbatch_file = os.path.join(SBATCH_DIR, f"{exp_name}.sbatch")
    
    output_dir = f"/projects/standard/ztchen/shared/yilong/outputs/{exp_name}"
    
    # Base bash template
    script_content = f"""#!/bin/bash
#SBATCH --job-name={exp_name}
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64gb
#SBATCH --gres=gpu:a100:1
#SBATCH --time=24:00:00
#SBATCH --partition=msigpu
#SBATCH --output={current_logs_dir}/%j_%x.out
#SBATCH --error={current_logs_dir}/%j_%x.err
#SBATCH --mail-type=BEGIN,END,FAIL
#SBATCH --mail-user={USER}@umn.edu

mkdir -p {current_logs_dir}

module purge
module load ffmpeg
module unload python 2>/dev/null || true

if [ -f "/users/7/{USER}/miniconda3/etc/profile.d/conda.sh" ]; then
    source /users/7/{USER}/miniconda3/etc/profile.d/conda.sh
else
    module load conda
fi
conda activate /projects/standard/ztchen/shared/yilong/conda_envs/lerobot-shared

export PATH="/users/7/{USER}/.local/bin:$PATH"
export PYTHONNOUSERSITE=1
unset LD_PRELOAD
export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$LD_LIBRARY_PATH

umask 0002

"""

    if not resume:
        # Build fresh training command
        eps_str = f"--dataset.episodes={config_data['episodes']}" if config_data.get('episodes') else ""
        extra_args_str = " ".join(config_data.get('extra_args', []))
        
        script_content += f"""python /projects/standard/ztchen/shared/yilong/lerobot_trossen/lerobot/scripts/train.py \\
    --dataset.repo_id {config_data['dataset_repo_id']} \\
    --policy.type {config_data['policy_type']} \\
    --steps 1000000 \\
    --save_freq 2000 \\
    --output_dir {output_dir} \\
    {eps_str} \\
    {extra_args_str}
"""
    else:
        # Build resume training command
        eps_str = f"--dataset.episodes={config_data['episodes']}" if config_data.get('episodes') else ""
        extra_args_str = " ".join(config_data.get('extra_args', []))
        
        target_epochs = config_data.get('target', 500)
        target_steps_str = "1000000"
        
        try:
            train_cfg_path = os.path.join(output_dir, "checkpoints", "last", "pretrained_model", "train_config.json")
            with open(train_cfg_path) as f:
                cfg = json.load(f)
            batch_size = cfg.get("batch_size")
            
            repo_path = config_data['dataset_repo_id']
            episodes_str = config_data.get('episodes')
            total_frames = get_total_frames(repo_path, episodes_str)
            
            if batch_size and total_frames:
                target_steps_str = str(int((target_epochs * total_frames) / batch_size))
        except Exception as e:
            print(f"[{exp_name}] Warning: Could not calculate precise steps: {e}")
            
        script_content += f"""python /projects/standard/ztchen/shared/yilong/lerobot_trossen/lerobot/scripts/train.py \\
    --resume=true \\
    --config_path={output_dir}/checkpoints/last/pretrained_model \\
    --dataset.repo_id {config_data['dataset_repo_id']} \\
    --output_dir {output_dir} \\
    --save_freq 2000 \\
    --steps {target_steps_str} \\
    {eps_str} \\
    {extra_args_str}
"""

    with open(sbatch_file, "w") as f:
        f.write(script_content)
        
    print(f"Submitting {'resume' if resume else 'initial'} job for {exp_name}...")
    result = subprocess.run(["sbatch", sbatch_file], capture_output=True, text=True, check=True)
    
    # Extract job ID from output like "Submitted batch job 6264457"
    output = result.stdout.strip()
    job_id = output.split()[-1]
    print(f"Started job ID {job_id} for {exp_name}")
    return job_id

def orchestrate():
    configs = load_configs()
    
    # Global toggle that allows the user to safely edit the JSON without partial execution!
    if not configs.get("_READY_TO_SYNC", True):
        print("Orchestrator paused. '_READY_TO_SYNC' is set to false in experiments.json.")
        return
        
    running_jobs = get_running_jobs()
    running_job_ids = set(running_jobs.values())
    
    updated = False
    
    # Phase calculation
    my_active_count = 0
    my_pending_count = 0
    
    for exp_name, exp_data in configs.items():
        if not isinstance(exp_data, dict): continue
        owner = exp_data.get('owner')
        if owner and owner != USER: continue
        
        status = exp_data.get('status')
        if status == 'active':
            my_active_count += 1
        elif status == 'pending':
            my_pending_count += 1
            
    if my_active_count == 0 and my_pending_count > 0:
        print(f"All {my_pending_count} active jobs finished Phase 1 (500 epochs). Transitioning Phase 2 (1000 epochs)!")
        for exp_name, exp_data in configs.items():
            if not isinstance(exp_data, dict): continue
            owner = exp_data.get('owner')
            if owner and owner != USER: continue
            
            if exp_data.get('status') == 'pending':
                exp_data['status'] = 'active'
                exp_data['target'] = 1000
                exp_data['job_id'] = None
                updated = True
    
    for exp_name, exp_data in configs.items():
        if not isinstance(exp_data, dict) or exp_data.get('status') != 'active':
            # Skip strings (JSON comments) and inactive/finished configs
            if isinstance(exp_data, dict) and exp_data.get('status') != 'active':
                
                # Check absolute owner bypass (so we never touch other researchers' jobs, active or inactive)
                owner = exp_data.get('owner')
                if owner and owner != USER:
                    continue
                
                last_job_id = exp_data.get('job_id')
                
                # If they wiped last_job_id in IDE, we can use the cluster truth
                job_to_cancel = last_job_id if last_job_id else running_jobs.get(exp_name)
                
                if job_to_cancel and str(job_to_cancel) in running_job_ids:
                    print(f"[{exp_name}] Status is '{exp_data.get('status')}' but job {job_to_cancel} is still running. Cancelling via scancel...")
                    subprocess.run(['scancel', str(job_to_cancel)])
                    time.sleep(1)
            continue
            
        # Also check owner explicitly for ACTIVE jobs so it doesn't launch someone else's unlaunched config
        owner = exp_data.get('owner')
        if owner and owner != USER:
            # Safely skip processing someone else's configuration
            continue
            
        dataset_repo = exp_data.get('dataset_repo_id', '')
        episodes_str = exp_data.get('episodes')
        current_epochs, step_val = get_epochs_for_run(exp_name, dataset_repo, episodes_str)
        target_epochs = exp_data.get('target', 500)
            
        last_job_id = exp_data.get('job_id')
        
        # Epoch Target Self-Healing Watchdog
        if current_epochs >= target_epochs:
            print(f"[{exp_name}] Target {target_epochs} epochs reached ({current_epochs:.2f} actual at step {step_val}). Checkpoint fully saved!")
            if last_job_id and str(last_job_id) in running_job_ids:
                print(f"[{exp_name}] Halting active job {last_job_id} via scancel...")
                subprocess.run(['scancel', str(last_job_id)])
                time.sleep(1)
                
            if target_epochs == 500:
                exp_data['status'] = 'pending'
            else:
                exp_data['status'] = 'finished'
            updated = True
            continue
        
        # Self-Healing: If IDE wiped the job_id to null but the job is actually running securely
        real_job_id = running_jobs.get(exp_name)
        if real_job_id and str(last_job_id) != str(real_job_id):
            print(f"[{exp_name}] IDE overwrite detected! Restoring missing job ID {real_job_id} from cluster.")
            exp_data['job_id'] = real_job_id
            last_job_id = real_job_id
            updated = True
            
        if last_job_id == "null" or last_job_id == "":
            last_job_id = None
            
        # Case 1: Job is currently running or pending in SLURM
        if last_job_id and str(last_job_id) in running_job_ids:
            print(f"[{exp_name}] Job {last_job_id} is running/pending (Epochs: {current_epochs:.2f} / {target_epochs}). Skipping.")
            continue
            
        # Case 2: Job has no ID yet (Freshly added configuration)
        if not last_job_id:
            output_dir = f"/projects/standard/ztchen/shared/yilong/outputs/{exp_name}"
            checkpoints_dir = os.path.join(output_dir, "checkpoints")
            
            # Deep Tensor Self-Healing: Dynamically rollback if hardware corruption exists.
            valid_checkpoint_found = False
            if os.path.exists(checkpoints_dir):
                highest_step = -1
                latest_ckpt_name = None
                
                # Sort numerically descending to naturally fall-back downwards
                subdirs = [d for d in os.listdir(checkpoints_dir) if d.isdigit()]
                subdirs.sort(key=int, reverse=True)
                
                for subdir in subdirs:
                    step_val = int(subdir)
                    checkpoint_target = os.path.join(checkpoints_dir, subdir)
                    
                    # Ensure both critical serialization matrices natively hit disk
                    model_path = os.path.join(checkpoint_target, "pretrained_model", "model.safetensors")
                    optimizer_path = os.path.join(checkpoint_target, "training_state", "optimizer_state.safetensors")
                    
                    if os.path.exists(model_path) and os.path.exists(optimizer_path):
                        is_valid = True
                        if safe_open:
                            try:
                                # Structurally crack open the binary headers
                                with safe_open(model_path, framework="pt"):
                                    pass
                                with safe_open(optimizer_path, framework="pt"):
                                    pass
                            except Exception as e:
                                print(f"[{exp_name}] WARNING: Checkpoint {subdir} has mathematically corrupted .safetensors headers. Purging...")
                                is_valid = False
                                
                        if not is_valid:
                            try:
                                shutil.rmtree(checkpoint_target)
                            except:
                                pass
                            continue # Ignore this folder and cleanly roll backwards to the next loop check!
                            
                        # If we reached here, the checkpoint is mathematically intact!
                        highest_step = step_val
                        latest_ckpt_name = subdir
                        break
                    else:
                        print(f"[{exp_name}] WARNING: Checkpoint {subdir} did not successfully serialize out natively. Purging...")
                        try:
                            shutil.rmtree(checkpoint_target)
                        except:
                            pass
                            
                if latest_ckpt_name:
                    last_link = os.path.join(checkpoints_dir, "last")
                    if os.path.islink(last_link) or os.path.exists(last_link):
                        os.remove(last_link)
                    os.symlink(latest_ckpt_name, last_link)
                    valid_checkpoint_found = True
            
            if valid_checkpoint_found:
                print(f"[{exp_name}] Found existing checkpoint for new configuration. Submitting resume job.")
                new_job_id = create_and_submit_sbatch(exp_name, exp_data, resume=True)
            else:
                # LeRobot strictly refuses to initialize (resume=False) if the output folder exists. 
                # If we legitimately have NO valid checkpoints, it's a corrupted launch remnant and must be safely purged!
                if os.path.exists(output_dir):
                    print(f"[{exp_name}] Corrupted empty output folder exists. Wiping for fresh init!")
                    import shutil
                    shutil.rmtree(output_dir)
                
                print(f"[{exp_name}] Found new active configuration. Generating initial job.")
                new_job_id = create_and_submit_sbatch(exp_name, exp_data, resume=False)
                
            exp_data['job_id'] = new_job_id
            updated = True
            continue
            
        # Case 3: Job is NOT running anymore. We must check what happened.
        print(f"[{exp_name}] Job {last_job_id} is no longer running. Checking outcomes...")
        
        # Did it finish legally with 1,000,000 steps?
        # Alternatively we can check sacct, but checking the log works well.
        if check_if_reached_1m(last_job_id, exp_name):
            print(f"[{exp_name}] Reached 1,000,000 steps! Marking as finished.")
            exp_data['status'] = "finished"
            updated = True
            continue

        # Did it timeout?
        if did_job_timeout(last_job_id, exp_name):
            print(f"[{exp_name}] Job timed out. Submitting a resume job.")
            new_job_id = create_and_submit_sbatch(exp_name, exp_data, resume=True)
            exp_data['job_id'] = new_job_id
            updated = True
            continue
            
        # If it reached here, it didn't finish cleanly and didn't timeout cleanly
        # It likely crashed or hits OOM. We don't automatically resume errors.
        print(f"[{exp_name}] ERROR: Job {last_job_id} exited without reaching 1M steps and without a TIME LIMIT. Skipping auto-resume. Please check logs manually.")

    if updated:
        save_configs(configs)
        
    # Generate telemetry after routine check
    generate_telemetry()

if __name__ == "__main__":
    print("Starting Orchestrator at", time.strftime('%Y-%m-%d %H:%M:%S'))
    try:
        orchestrate()
        print("Orchestration pass complete.")
    except Exception as e:
        print(f"Orchestrator encountered error: {e}")
