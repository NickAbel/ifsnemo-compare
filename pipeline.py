#!/usr/bin/env python3
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
            timestamp = time.strftime("%H:%M:%S")
            print(f"\rWaiting for SLURM job {job_id} to complete... (last checked: {timestamp})", end='', flush=True)
            time.sleep(poll_interval)
        except EOFError:
            print("\nConnection dropped, attempting to reconnect...")
            conn.close()
            time.sleep(5)  # Wait a bit before retrying

    print(f"\nSLURM job {job_id} completed.")

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
    import os
    local_str = str(local_path)
    remote_str = str(remote_path)
    remote_dir = remote_path.parent

    print(f"Ensuring remote directory {remote_dir} exists...")

    # Ensure the remote directory exists
    conn.run(f"mkdir -p '{remote_dir}'")

    if verbose:
        print(f"Uploading {local_path} → {remote_path} ...")

    # Progress callback
    file_size = os.path.getsize(local_str)

    def progress_callback(transferred, total):
        percent = (transferred / total) * 100
        bar_length = 50
        filled = int(bar_length * transferred // total)
        bar = '=' * filled + '-' * (bar_length - filled)
        transferred_mb = transferred / (1024 * 1024)
        total_mb = total / (1024 * 1024)
        print(f'\r[{bar}] {percent:.1f}% ({transferred_mb:.1f}/{total_mb:.1f} MB)', end='', flush=True)

    sftp = conn.sftp()
    sftp.put(local_str, remote_str, callback=progress_callback)
    print()  # newline after progress bar

    if verbose:
        print(f"Upload complete: {remote_str}")

def main(pipeline_yaml_path: str, skip_build: bool, no_run: bool, partial_build: bool):
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
        cfg = yaml.safe_load(f) or {}

    remote_username = cfg.get("user", {}).get("remote_username")
    remote_machine = cfg.get("user", {}).get("remote_machine_url")
    machine_file = cfg.get("user", {}).get("machine_file")
    remote_path = cfg.get("paths", {}).get("remote_project_dir")
    local_path = Path(cfg.get("paths", {}).get("local_build_dir", "."))

    # Use safe defaults and guard missing keys
    ifs_cfg = cfg.get("ifsnemo_compare", {})
    resolution = ifs_cfg.get("resolution", [])
    steps = ifs_cfg.get("steps", [])
    threads = ifs_cfg.get("threads", [])
    ppn = ifs_cfg.get("ppn", [])
    nodes = ifs_cfg.get("nodes", [])
    gpus = ifs_cfg.get("gpus", [])
    gold_standard_tag = ifs_cfg.get("gold_standard_tag", "")

    ov = cfg.get("overrides", {})

    ifs_source_git_url_template = ov.get("IFS_BUNDLE_IFS_SOURCE_GIT", "")
    ifs_source_git_url = ifs_source_git_url_template.format(**ov) if ifs_source_git_url_template else ""
    dnb_sandbox_subdir = ov.get('DNB_SANDBOX_SUBDIR', '')

    # Establish connection to remote
    conn = Connection(f"{remote_username}@{remote_machine}")
    # This will raise if remote requirements are missing
    check_remote_requirements(conn, verbose=True)

    # Handle flag interactions
    if skip_build and partial_build:
        print("Warning: --partial-build is ignored when --skip-build is set")
        partial_build = False

    if skip_build:
        # If we skip the build, the remote tests directory will not be empty.
        # We want to delete any subdirectory in there that corresponds to the
        # test configuration we are running.
        if dnb_sandbox_subdir:
            remote_tests_dir = f"{remote_path}/ifsnemo-build/ifsnemo/tests/{dnb_sandbox_subdir}"
            print(f"Deleting remote tests directory: {remote_tests_dir}")
            conn.run(f"rm -rf {remote_tests_dir}")

    if not skip_build:
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
        if ov.get('DNB_IFSNEMO_BUNDLE_GIT'):
            overrides_content.append(f'  - export DNB_IFSNEMO_BUNDLE_GIT="{ov.get("DNB_IFSNEMO_BUNDLE_GIT")}"')
        if ov.get('IFS_BUNDLE_RAPS_GIT'):
            overrides_content.append(f'  - export IFS_BUNDLE_RAPS_GIT="{ov.get("IFS_BUNDLE_RAPS_GIT")}"')
        if ov.get('IFS_BUNDLE_RAPS_VERSION'):
            overrides_content.append(f'  - export IFS_BUNDLE_RAPS_VERSION="{ov.get("IFS_BUNDLE_RAPS_VERSION")}"')
        if ov.get('DNB_IFSNEMO_WITH_GPU'):
            overrides_content.append(f'  - export DNB_IFSNEMO_WITH_GPU={ov.get("DNB_IFSNEMO_WITH_GPU")}')
        if ov.get('DNB_IFSNEMO_WITH_GPU_EXTRA'):
            overrides_content.append(f'  - export DNB_IFSNEMO_WITH_GPU_EXTRA={ov.get("DNB_IFSNEMO_WITH_GPU_EXTRA")}')
        if ov.get('DNB_IFSNEMO_WITH_STATIC_LINKING'):
            overrides_content.append(f'  - export DNB_IFSNEMO_WITH_STATIC_LINKING={ov.get("DNB_IFSNEMO_WITH_STATIC_LINKING")}')
        if ov.get('DNB_IFSNEMO_USE_ARCH_AND_RAPS'):
            overrides_content.append(f'  - export DNB_IFSNEMO_USE_ARCH_AND_RAPS={ov.get("DNB_IFSNEMO_USE_ARCH_AND_RAPS")}')

        ## Process miscellaneous environment variables from 'env' key
        misc_env = ov.get('env', {})
        if misc_env:
            for env_key, env_value in misc_env.items():
                overrides_content.append(f'  - export {env_key}="{env_value}"')

        (local_path / "overrides.yaml").write_text('\n'.join(overrides_content) + '\n')

        # Generate account.yaml
        (local_path / "account.yaml").write_text(f"""---
psubmit:
  queue_name: "{cfg.get('psubmit', {}).get('queue_name', '')}"
  account:     {cfg.get('psubmit', {}).get('account', '')}
  node_type:   {cfg.get('psubmit', {}).get('node_type', '')}
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

        # Create src folder for dnb.sh :du
        (local_path / "src").mkdir(exist_ok=True, parents=True)

        # Run './dnb.sh :du' from within local_path
        run_command(['./dnb.sh', ':du'], cwd=local_path, verbose=verbose)

        # Download ifsnemo-compare into the local_path
        subprocess.run(["rm", "-fr", str(local_path) + "/ifsnemo-compare"], check=True)
        subprocess.run(["git", "clone", "https://github.com/NickAbel/ifsnemo-compare.git", str(local_path) + "/ifsnemo-compare"], check=True)

        ############################################
        # 2.1-2.3 Build and Install on remote
        ############################################

        # Sync files to remote using rsync
        local_path = Path(local_path)
        remote_path = Path(remote_path)

        # Ensure the remote directory exists
        print(f"Ensuring remote directory {remote_path}/ifsnemo-build exists...")
        conn.run(f"mkdir -p '{remote_path}/ifsnemo-build'")

        print(f"Syncing {local_path}/ to {remote_username}@{remote_machine}:{remote_path}/ifsnemo-build/ ...")
        rsync_cmd = [
            "rsync", "-rlpgoDcvvz", 
            str(local_path) + "/",
            f"{remote_username}@{remote_machine}:{remote_path}/ifsnemo-build/"
        ]
        run_command(rsync_cmd, verbose=verbose)

        psubmit_account = cfg.get('psubmit', {}).get('account', '')
        psubmit_node_type = cfg.get('psubmit', {}).get('node_type', '')

        # Read ppn and nth from machine_file to calculate ntasks-per-node for SBATCH
        ntasks_per_node = 80  # Default value
        machine_config_path = local_path / machine_file
        if machine_config_path.is_file():
            with open(machine_config_path, 'r') as f:
                machine_config = yaml.safe_load(f) or {}
            psubmit_config = machine_config.get('psubmit', {})
            machine_ppn = psubmit_config.get('ppn')
            machine_nth = psubmit_config.get('nth')
            if machine_ppn and machine_nth:
                try:
                    ntasks_per_node = int(machine_ppn) * int(machine_nth)
                except (ValueError, TypeError):
                    print(f"Warning: Could not calculate ntasks-per-node from ppn='{machine_ppn}' and nth='{machine_nth}'. Using default {ntasks_per_node}.")
            else:
                print(f"Warning: 'ppn' or 'nth' not found in {machine_config_path}. Using default ntasks-per-node={ntasks_per_node}.")
        else:
            print(f"Warning: machine_file '{machine_config_path}' not found. Using default ntasks-per-node={ntasks_per_node}.")

        # Determine build command
        if partial_build:
            build_cmd = ":r"
            print("""
 PARTIAL BUILD MODE
 Using incremental/partial rebuild instead of full build
 This is primarily intended for only when source code
 changes have occurred and re-run of the bundle is not
 needed.
 If in doubt, run a full build instead!
""")
        else:
            build_cmd = ":b"

        # Build on a compute node
        sbatch_script = f"""#!/bin/bash
#SBATCH -A {psubmit_account}
#SBATCH --qos={psubmit_node_type}
#SBATCH --job-name=dnb_sh_build
#SBATCH --output=dnb_sh_build_%j.out
#SBATCH --error=dnb_sh_build_%j.err
#SBATCH --nodes=1
#SBATCH --ntasks-per-node={ntasks_per_node}
#SBATCH --cpus-per-task=1
#SBATCH --time=02:00:00
#SBATCH --exclusive

module load cmake/3.30.5

cd {remote_path}/ifsnemo-build
ln -sf {machine_file} machine.yaml
./dnb.sh {build_cmd}
"""

        Path("ifsnemo_build_dnb_b.sbatch").write_text(sbatch_script)
        conn.put("ifsnemo_build_dnb_b.sbatch", f"{remote_path}/ifsnemo_build_dnb_b.sbatch")

        # Run the build on compute node with sbatch job
        job_output = conn.run(f"cd {remote_path} && sbatch ifsnemo_build_dnb_b.sbatch", hide=True)

        # Wait until completion
        job_id = job_output.stdout.strip().split()[-1]
        wait_for_job(conn, job_id)

        # Run ./dnb.sh :i on login node
        conn.run(f"cd {remote_path}/ifsnemo-build && ./dnb.sh :i")

        # Copy references into the test arena if they exist
        if "references" in cfg:
            conn.run(f"rsync -a {remote_path}/ifsnemo-build/references/ {remote_path}/ifsnemo-build/ifsnemo/references/")

        # Copy the comparison script into the test arena
        conn.run(f"rsync -a {remote_path}/ifsnemo-build/ifsnemo-compare/compare_norms.py {remote_path}/ifsnemo-build/ifsnemo/")

    test_results = {}
    results_file = "test_results.json"

    # Explicitly handle the case where the user asked to skip run/compare
    if no_run:
        print("Skipping run and compare stages (--no-run).")
    else:
        # If any of the test-parameter lists are empty, there are no tests to run.
        if not (resolution and steps and threads and ppn and nodes):
            print("No test configurations found; skipping run and compare stages.")
        else:
            use_gpu = str(ov.get('DNB_IFSNEMO_WITH_GPU', 'FALSE')).upper() == 'TRUE'
            loop_items = [resolution, steps, threads, ppn, nodes]
            if use_gpu:
                loop_items.append(gpus)

            # Ensure all elements are lists for zip
            loop_items = [x if isinstance(x, list) else [x] for x in loop_items]

            for items in zip(*loop_items):
                if use_gpu:
                    r, s, t, p, n, g = items
                    test_id = f"r{r}_s{s}_t{t}_p{p}_n{n}_g{g}"
                    gpu_flag = f" --gpus {quote(str(g))}"
                    print(f"running test remotely with r={r}, s={s}, t={t}, p={p}, n={n}, g={g}...")
                else:
                    r, s, t, p, n = items
                    test_id = f"r{r}_s{s}_t{t}_p{p}_n{n}"
                    gpu_flag = ""
                    print(f"running test remotely with r={r}, s={s}, t={t}, p={p}, n={n}...")

                test_results[test_id] = {}

                run_output_file = f"run_tests_{test_id}.log"
                cmd_run = (
                    f"cd {quote(str(remote_path))}/ifsnemo-build/ifsnemo && "
                    f"python3 compare_norms.py run-tests "
                    f"-t {quote(dnb_sandbox_subdir)}/ -ot tests -r {quote(r)} -nt {quote(str(t))} "
                    f"-p {quote(str(p))} -n {quote(str(n))} -s {quote(s)}{gpu_flag}"
                )
                print(cmd_run)
                result = conn.run(cmd_run, warn=True, pty=True)
                with open(run_output_file, "w") as f:
                    f.write(result.stdout)
                if verbose:
                    print(f"Output of run-tests saved to local file {run_output_file}")
                test_results[test_id]["run_tests_passed"] = result.return_code == 0
                test_results[test_id]["run_tests_output"] = run_output_file

                if use_gpu:
                    print(f"comparing tests remotely with r={r}, s={s}, t={t}, p={p}, n={n}, g={g}...")
                else:
                    print(f"comparing tests remotely with r={r}, s={s}, t={t}, p={p}, n={n}...")
                compare_output_file = f"compare_{test_id}.log"
                cmd_cmp = (
                    f"cd {quote(str(remote_path))}/ifsnemo-build/ifsnemo && "
                    f"python3 compare_norms.py compare "
                    f"-t {quote(dnb_sandbox_subdir)}/ -ot tests "
                    f"-g {quote(gold_standard_tag)}/ -og references "
                    f"-r {quote(r)} -nt {quote(str(t))} -p {quote(str(p))} -n {quote(str(n))} -s {quote(s)}{gpu_flag}"
                )
                print(cmd_cmp)
                result = conn.run(cmd_cmp, warn=True, pty=True)
                with open(compare_output_file, "w") as f:
                    f.write(result.stdout)
                if verbose:
                    print(f"Output of compare saved to local file {compare_output_file}")
                test_results[test_id]["compare_passed"] = result.return_code == 0
                test_results[test_id]["compare_output"] = compare_output_file

    # Write the results to a JSON file
    with open(results_file, "w") as f:
        json.dump(test_results, f, indent=4)
    print(f"Test results written to {results_file} on the local machine.")

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
    parser.add_argument(
        "--no-run",
        dest="no_run",
        action="store_true",
        help="Do the build/install but skip the run and compare stages (produce no test runs)"
    )
    parser.add_argument(
        "--partial-build",
        dest="partial_build",
        action="store_true",
        help="Use partial build (dnb.sh :r) instead of full build (dnb.sh :b). Intended for quick rebuilds involving small changes in the code, and does not invoke ifs-bundle."
    )
    args = parser.parse_args()

    try:
        main(args.pipeline_yaml, args.skip_build, args.no_run, args.partial_build)
    except Exception as e:
        print("ERROR:", e)
        # Print traceback for easier debugging
        import traceback
        traceback.print_exc()
        sys.exit(1)
    else:
        sys.exit(0)
