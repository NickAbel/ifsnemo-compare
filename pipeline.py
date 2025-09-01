import yaml
from shlex import quote
import subprocess
from pathlib import Path
from fabric import Connection
import shutil
import time
import sys
import argparse
import json

verbose = True

def wait_for_job(conn, job_id, poll_interval=30):
    while True:
        try:
            result = conn.run(f"squeue -j {job_id}", hide=True, warn=True)
            if job_id not in result.stdout:
                break
            print(f"Waiting for SLURM job {job_id} to complete...")
            time.sleep(poll_interval)
        except EOFError:
            print("Connection dropped, attempting to reconnect...")
            conn.close()
            time.sleep(5)  # Wait a bit before retrying

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
        # Treat missing remote requirements as fatal
        raise RuntimeError(f"Missing remote requirements: {', '.join(missing)}")
    elif verbose:
        print("All remote requirements are present.")

def run_command(cmd, cwd=None, verbose=False, capture_output=False):
    if verbose:
        print(f"Running: {' '.join(cmd)} in {cwd or '.'}")
    # Use subprocess with output shown live
    process = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE if capture_output else subprocess.PIPE,
        stderr=subprocess.STDOUT if capture_output else subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    output_lines = []
    for line in process.stdout:
        print(line, end='')  # print output live
        if capture_output:
            output_lines.append(line)
    process.wait()
    if process.returncode != 0:
        raise subprocess.CalledProcessError(process.returncode, cmd)
    if capture_output:
        return process.returncode, "".join(output_lines)
    else:
        return process.returncode, None

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

def main(pipeline_yaml_path: str, skip_build: bool):
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
    with open(pipeline_yaml_path, "r") as f:
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
    gold_standard_tag = cfg["ifsnemo_compare"]["gold_standard_tag"]

    ov = cfg.get("overrides", {})

    ifs_source_git_url_template = ov.get("IFS_BUNDLE_IFS_SOURCE_GIT", "")
    ifs_source_git_url = ifs_source_git_url_template.format(**ov) if ifs_source_git_url_template else ""
    dnb_sandbox_subdir = ov.get('DNB_SANDBOX_SUBDIR', '')

    # Generate overrides.yaml
    overrides_content = ['---', 'environment:']
    if dnb_sandbox_subdir:
        overrides_content.append(f'  - export DNB_SANDBOX_SUBDIR="{dnb_sandbox_subdir}"')
    if ov.get('DNB_IFSNEMO_URL'):
        overrides_content.append(f'  - export DNB_IFSNEMO_URL="{ov.get("DNB_IFSNEMO_URL")}"')
    if ov.get('IFS_BUNDLE_IFS_SOURCE_VERSION'):
        overrides_content.append(f'  - export IFS_BUNDLE_IFS_SOURCE_VERSION="{ov.get("IFS_BUNDLE_IFS_SOURCE_VERSION")}"')
    if ifs_source_git_url:
        overrides_content.append(f'  - export IFS_BUNDLE_IFS_SOURCE_GIT="{ifs_source_git_url}"')
    if ov.get('DNB_IFSNEMO_BUNDLE_BRANCH'):
        overrides_content.append(f'  - export DNB_IFSNEMO_BUNDLE_BRANCH="{ov.get("DNB_IFSNEMO_BUNDLE_BRANCH")}"')


    (local_path / "overrides.yaml").write_text('\n'.join(overrides_content) + '\n')

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

    # Establish connection to remote
    conn = Connection(f"{remote_username}@{remote_machine}")

    # This will raise if remote requirements are missing
    check_remote_requirements(conn, verbose=True)

    if not skip_build:
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

    test_results = {}
    results_file = "test_results.json"

    for r, s, t, p, n in zip(resolution, steps, threads, ppn, nodes):
        test_id = f"r{r}_s{s}_t{t}_p{p}_n{n}"
        test_results[test_id] = {}

        print(f"running test remotely with r={r}, s={s}, t={t}, p={p}, n={n}...")
        run_output_file = f"run_tests_{test_id}.log"
        cmd_run = (
            f"cd {quote(str(remote_path))}/ifsnemo-build/ifsnemo && "
            f"python3 compare_norms.py run-tests "
            f"-t {quote(dnb_sandbox_subdir)}/ -ot tests -r {quote(r)} -nt {quote(str(t))} "
            f"-p {quote(str(p))} -n {quote(str(n))} -s {quote(s)} "
            f"> {run_output_file} 2>&1"
        )
        print(cmd_run)
        return_code = conn.run(cmd_run, warn=True).return_code
        test_results[test_id]["run_tests_passed"] = return_code == 0
        test_results[test_id]["run_tests_output"] = run_output_file

        print(f"comparing tests remotely with r={r}, s={s}, t={t}, p={p}, n={n}...")
        compare_output_file = f"compare_{test_id}.log"
        cmd_cmp = (
            f"cd {quote(str(remote_path))}/ifsnemo-build/ifsnemo && "
            f"python3 compare_norms.py compare "
            f"-t {quote(dnb_sandbox_subdir)}/ -ot tests "
            f"-g {quote(gold_standard_tag)}/ -og references "
            f"-r {quote(r)} -nt {quote(str(t))} -p {quote(str(p))} -n {quote(str(n))} -s {quote(s)} "
            f"> {compare_output_file} 2>&1"
        )
        print(cmd_cmp)
        return_code = conn.run(cmd_cmp, warn=True).return_code
        test_results[test_id]["compare_passed"] = return_code == 0
        test_results[test_id]["compare_output"] = compare_output_file

    # Write the results to a JSON file
    conn.run(f"echo '{json.dumps(test_results)}' > {remote_path}/ifsnemo-build/ifsnemo/{results_file}")
    print(f"Test results written to {results_file}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Build and run ifs-nemo comparison pipeline.")
    parser.add_argument(
        "-y", "--yaml",
        dest="pipeline_yaml",
        default="pipeline.yaml",
        help="Path to pipeline YAML file (default: pipeline.yaml)"
    )
    parser.add_argument(
        "-s", "--skip-build",
        dest="skip_build",
        action="store_true",
        help="Skip the build and install steps, only run tests and compare"
    )
    args = parser.parse_args()

    try:
        main(args.pipeline_yaml, args.skip_build)
    except Exception as e:
        print("ERROR:", e)
        # Print traceback for easier debugging
        import traceback
        traceback.print_exc()
        sys.exit(1)
    else:
        sys.exit(0)
