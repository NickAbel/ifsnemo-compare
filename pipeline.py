import yaml
from shlex import quote
import subprocess
from pathlib import Path
from fabric import Connection
import shutil
import time

verbose = True

def wait_for_job(conn, job_id, poll_interval=30):
    while True:
        result = conn.run(f"squeue -j {job_id}", hide=True, warn=True)
        if job_id not in result.stdout:
            break
        print(f"Waiting for SLURM job {job_id} to complete...")
        time.sleep(poll_interval)

    print(f"SLURM job {job_id} completed.")

def check_remote_requirements(conn, verbose=False):
    # Check for yq and psubmit.sh in remote PATH
    missing = []
    for cmd in ['yq', 'psubmit.sh']:
        result = conn.run(f'command -v {cmd}', hide=True, warn=True)
        if result.exited != 0:
            missing.append(cmd)
    if missing:
        warning = f"""
#######################################################
#WARNING: The following required commands are missing:#
#    {', '.join(missing)}                                          
#Please ensure they are in your PATH on the remote!   #
#######################################################
"""
        print(warning)
    elif verbose:
        print("All remote requirements are present.")

def run_command(cmd, cwd=None, verbose=False):
    if verbose:
        print(f"Running: {' '.join(cmd)} in {cwd or '.'}")
    # Use subprocess with output shown live
    process = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    for line in process.stdout:
        print(line, end='')  # print output live
    process.wait()
    if process.returncode != 0:
        raise subprocess.CalledProcessError(process.returncode, cmd)

def upload_file(conn, local_path, remote_path, verbose=False):
    local_str = str(local_path)
    remote_str = str(remote_path)
    remote_dir = remote_path.parent

    print(f"Ensuring remote directory {remote_dir} exists...")

    # Ensure the remote directory exists
    conn.run(f"mkdir -p '{remote_dir}'")

    if verbose:
        print(f"Uploading {local_path} → {remote_path} ...")
    result = conn.put(local=local_str, remote=remote_str)
    if verbose:
        print(f"Upload complete: {result.remote}")

############################################
# 1.1 Ensure yq installed on local machine
############################################
if shutil.which("yq") is None:
    print("""
###########################################################################
#      WARNING: 'yq' not found in PATH! Some steps may not work.          #
# https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64 #
###########################################################################
""")

############################################
# 1.2 Ensure netrc file exists
############################################
if not Path.home().joinpath('.netrc').exists():
    print("""
###########################################################
# WARNING: '~/.netrc' not found! Some steps may not work. #
###########################################################
""")

############################################
# 1.3 Write ifsnemo-build config files
############################################
with open("pipeline.yaml", "r") as f:
    cfg = yaml.safe_load(f)

remote_username = cfg["user"]["remote_username"]
remote_machine = cfg["user"]["remote_machine_url"]
machine_file = cfg["user"]["machine_file"]
remote_path = cfg["paths"]["remote_project_dir"]
local_path = Path(cfg["paths"]["local_build_dir"])

resolution = cfg["ifsnemo_compare"]["resolution"]
steps = cfg["ifsnemo_compare"]["steps"]
threads = cfg["ifsnemo_compare"]["threads"]
ppn = cfg["ifsnemo_compare"]["ppn"]
nodes = cfg["ifsnemo_compare"]["nodes"]

ov = cfg["overrides"]

ifs_source_git_url = ov["IFS_BUNDLE_IFS_SOURCE_GIT"].format(**ov)
dnb_sandbox_subdir = ov['DNB_SANDBOX_SUBDIR']

# Generate overrides.yaml
(local_path / "overrides.yaml").write_text(f"""---
environment:
  - export DNB_SANDBOX_SUBDIR="{ov['DNB_SANDBOX_SUBDIR']}"
  - export DNB_IFSNEMO_URL="{ov['DNB_IFSNEMO_URL']}"
  - export IFS_BUNDLE_IFS_SOURCE_VERSION="{ov['IFS_BUNDLE_IFS_SOURCE_VERSION']}"
  - export IFS_BUNDLE_IFS_SOURCE_GIT="{ifs_source_git_url}"
""")

# Generate account.yaml
(local_path / "account.yaml").write_text(f"""---
psubmit:
  queue_name: "{cfg['psubmit']['queue_name']}"
  account:     {cfg['psubmit']['account']}
  node_type:   {cfg['psubmit']['node_type']}
""")

# Link to generic machine config
run_command(['ln', '-sf', 'dnb-generic.yaml', 'machine.yaml'], cwd=local_path, verbose=verbose)

############################################
# 1.4 Fetch and Package Build Artifacts
############################################

# Fetch references if specified
if "references" in cfg:
    ref_cfg = cfg["references"]
    ref_url = ref_cfg["url"]
    ref_branch = ref_cfg.get("branch", "main")
    ref_path_in_repo = ref_cfg["path_in_repo"]
    
    temp_ref_dir = local_path / "temp_ref"
    if temp_ref_dir.exists():
        shutil.rmtree(temp_ref_dir)
    
    print(f"Cloning {ref_url} (branch: {ref_branch}) to {temp_ref_dir}")
    run_command(["git", "clone", "--depth", "1", "--branch", ref_branch, ref_url, str(temp_ref_dir)], verbose=verbose)
    
    source_path = temp_ref_dir / ref_path_in_repo
    target_path = local_path / "references"
    
    if target_path.exists():
        shutil.rmtree(target_path)
    
    print(f"Copying {source_path} to {target_path}")
    shutil.copytree(source_path, target_path)
    
    print(f"Cleaning up {temp_ref_dir}")
    shutil.rmtree(temp_ref_dir)

# Run './dnb.sh :du' from within local_path
run_command(['./dnb.sh', ':du'], cwd=local_path, verbose=verbose)

# Download ifsnemo-compare into the local_path
subprocess.run(["rm", "-fr", str(local_path) + "/ifsnemo-compare"], check=True)
subprocess.run(["git", "clone", "https://github.com/NickAbel/ifsnemo-compare.git", str(local_path) + "/ifsnemo-compare"], check=True)

# Create tarball
run_command(["tar", "czvf", "../ifsnemo-build.tar.gz", "."], cwd=local_path, verbose=verbose)

############################################
# 2.1-2.3 Build and Install on remote
############################################

# Establish connection to remote
conn = Connection(f"{remote_username}@{remote_machine}")
check_remote_requirements(conn, verbose=True)

# Upload the tarball
local_path = Path(local_path)
remote_path = Path(remote_path)
upload_file(conn, local_path / "../ifsnemo-build.tar.gz", remote_path / "ifsnemo-build.tar.gz", verbose=verbose)

# Build on a compute node
sbatch_script = f"""#!/bin/bash
#SBATCH -A ehpc01
#SBATCH --qos=gp_debug
#SBATCH --job-name=dnb_sh_build
#SBATCH --output=dnb_sh_build_%j.out
#SBATCH --error=dnb_sh_build_%j.err
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=112
#SBATCH --cpus-per-task=1
#SBATCH --time=02:00:00
#SBATCH --exclusive

module load cmake/3.30.5

cd {remote_path}
tar xzvf ifsnemo-build.tar.gz --one-top-level
cd ifsnemo-build
ln -sf {machine_file} machine.yaml
./dnb.sh :b
"""

Path("ifsnemo_build_dnb_b.sbatch").write_text(sbatch_script)
conn.put("ifsnemo_build_dnb_b.sbatch", f"{remote_path}/ifsnemo_build_dnb_b.sbatch")

# Run ./dnb.sh :b on compute node with sbatch job
job_output = conn.run(f"cd {remote_path} && sbatch ifsnemo_build_dnb_b.sbatch", hide=True)

# Wait until completion
job_id = job_output.stdout.strip().split()[-1]
wait_for_job(conn, job_id)

# Run ./dnb.sh :i on login node
conn.run(f"cd {remote_path}/ifsnemo-build && ./dnb.sh :i")

# Move references into the test arena if they exist
if "references" in cfg:
    conn.run(f"mv -f {remote_path}/ifsnemo-build/references {remote_path}/ifsnemo-build/ifsnemo")

# Move the comparison script into the test arena
conn.run(f"mv -f {remote_path}/ifsnemo-build/ifsnemo-compare/compare_norms.py {remote_path}/ifsnemo-build/ifsnemo")

for r, s, t, p, n in zip(resolution, steps, threads, ppn, nodes):
    print(f"running test remotely with r={r}, s={s}, t={t}, p={p}, n={n}...")
    cmd_run = (
        f"cd {quote(remote_path)}/ifsnemo-build/ifsnemo && "
        f"python3 compare_norms.py run-tests "
        f"-t {quote(dnb_sandbox_subdir)}/ -ot tests -r {quote(r)} -nt {quote(str(t))} "
        f"-p {quote(str(p))} -n {quote(str(n))} -s {quote(s)}"
    )
    conn.run(cmd_run)

    print(f"comparing tests remotely with r={r}, s={s}, t={t}, p={p}, n={n}...")
    cmd_cmp = (
        f"cd {quote(remote_path)}/ifsnemo-build/ifsnemo && "
        f"python3 compare_norms.py compare "
        f"-t {quote(dnb_sandbox_subdir)}/ -ot tests "
        f"-g ifsMASTER.SP.CPU.GPP/ -og references "
        f"-r {quote(r)} -nt {quote(str(t))} -p {quote(str(p))} -n {quote(str(n))} -s {quote(s)}"
    )
    conn.run(cmd_cmp)

