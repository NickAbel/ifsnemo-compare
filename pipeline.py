#!/usr/bin/env python3
import yaml
from shlex import quote
import subprocess
from pathlib import Path
try:
    from fabric import Connection
except ImportError:
    Connection = None
from datetime import datetime
import shutil
import time
import sys
import argparse
import json
import os
import socket
from typing import Optional
from test_runner import (
    load_test_definitions,
    validate_test_definitions,
    execute_test,
    init_run_directory,
)

# ANSI formatting
BOLD = '\033[1m'
RESET = '\033[0m'


from dataclasses import dataclass

@dataclass
class _LocalResult:
    stdout: str
    stderr: str
    exited: int


class LocalConnection:
    """Fabric Connection-compatible interface for local (on-HPC) execution."""

    def run(self, cmd, hide=False, warn=False):
        result = subprocess.run(cmd, shell=True, text=True, capture_output=True)
        if not hide:
            if result.stdout:
                print(result.stdout, end='')
            if result.stderr:
                print(result.stderr, end='', file=sys.stderr)
        if result.returncode != 0 and not warn:
            raise subprocess.CalledProcessError(result.returncode, cmd, result.stdout, result.stderr)
        return _LocalResult(stdout=result.stdout, stderr=result.stderr, exited=result.returncode)

    def get(self, remote_path, local=None):
        if local:
            shutil.copy2(remote_path, local)

    def put(self, local_path, remote_path):
        dest = Path(remote_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_path, dest)

    def close(self):
        pass


def check_internet() -> bool:
    """Returns True if outbound TCP to github.com:443 succeeds within 5 seconds."""
    try:
        with socket.create_connection(("github.com", 443), timeout=5):
            return True
    except OSError:
        return False


def print_banner():
    C  = '\033[96m'   # bright cyan
    W  = '\033[97m'   # bright white
    D  = '\033[2;36m' # dim cyan (box + separator)
    DW = '\033[2m'    # dim (info line)
    R  = '\033[0m'    # reset
    pad = ' ' * 18    # right-pad art rows to fill 50-char interior (2 indent + 30 art + 18 pad)
    bl  = ' ' * 50    # blank interior
    print('\n'.join([
        f"{D}╔{'═'*50}╗{R}",
        f"{D}║{R}{bl}{D}║{R}",
        f"{D}║{R}  {C}### ### ### # # ### #   # ####{R}{pad}{D}║{R}",
        f"{D}║{R}  {C} #  #   #   ### #   ## ## #  #{R}{pad}{D}║{R}",
        f"{D}║{R}  {C} #  ##  ### # # ##  # # # #  #{R}{pad}{D}║{R}",
        f"{D}║{R}  {C} #  #     # # # #   #   # #  #{R}{pad}{D}║{R}",
        f"{D}║{R}  {C}### #   ### # # ### #   # ####{R}{pad}{D}║{R}",
        f"{D}║{R}{bl}{D}║{R}",
        f"{D}║{R}  {D}──────────────────────────────{R}{pad}{D}║{R}",
        f"{D}║{R}{bl}{D}║{R}",
        f"{D}║{R}  {W}### #### #   # ##   #  ##  ###{R}{pad}{D}║{R}",
        f"{D}║{R}  {W}#   #  # ## ## # # # # # # #  {R}{pad}{D}║{R}",
        f"{D}║{R}  {W}#   #  # # # # ##  ### ##  ## {R}{pad}{D}║{R}",
        f"{D}║{R}  {W}#   #  # #   # #   # # # # #  {R}{pad}{D}║{R}",
        f"{D}║{R}  {W}### #### #   # #   # # # # ###{R}{pad}{D}║{R}",
        f"{D}║{R}{bl}{D}║{R}",
        f"{D}║{R}  {DW}version cy49r3  ·  BSC Earth Sciences{R}           {D}║{R}",
        f"{D}╚{'═'*50}╝{R}",
    ]))


def can_ssh_github(conn) -> bool:
    """Returns True if outbound SSH to github.com port 22 succeeds."""
    try:
        result = conn.run(
            "ssh -o ConnectTimeout=5 -o BatchMode=yes -T git@github.com 2>&1 || true",
            hide=True, warn=True
        )
        return "successfully authenticated" in result.stdout or "Hi " in result.stdout
    except Exception:
        return False


def github_https_env(conn) -> dict:
    """Returns env vars that rewrite git@github.com: to https://github.com/ if SSH is blocked."""
    if can_ssh_github(conn):
        return {}
    return {
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "url.https://github.com/.insteadOf",
        "GIT_CONFIG_VALUE_0": "git@github.com:",
    }


def resolve_exec_mode(exec_mode_arg: Optional[str]) -> str:
    """
    Returns 'direct' or 'proxy'.

    If exec_mode_arg is provided (from --exec-mode), use it directly.
    Otherwise, explain why we cannot determine this automatically and ask the user.
    """
    if exec_mode_arg in ('direct', 'proxy'):
        return exec_mode_arg

    print("""
Cannot determine execution mode automatically.

This tool needs to know whether it should run commands directly on this machine
or connect to a remote system via SSH. We cannot infer this from the environment
because filesystem paths (e.g. /gpfs) can exist in many unrelated contexts —
a different HPC cluster, a local SSHFS mount, etc. Using the wrong mode could
cause unintended writes to an unknown system.

Two modes are available:

  [1] direct  — This machine has direct filesystem access to the target HPC
                system's storage AND can submit jobs there from its command
                line (e.g. you are on a login node of the target cluster).

  [2] proxy   — This machine cannot do the above from its command line, but
                can SSH to a machine that can (e.g. you are on a laptop
                connecting to the cluster over SSH).

To skip this prompt in future runs, pass --exec-mode direct or --exec-mode proxy.
""")
    while True:
        answer = input("Enter 1 (direct) or 2 (proxy): ").strip()
        if answer == '1':
            return 'direct'
        if answer == '2':
            return 'proxy'
        print("Please enter 1 or 2.")


def collect_artifacts(conn, log_path: Path, local_dir: Path) -> list:
    """
    Scan a local log file for 'ARTIFACT: <remote_path>' lines and download
    each file from the remote host into local_dir.  Returns list of local paths.
    """
    collected = []
    try:
        text = log_path.read_text()
    except OSError:
        return collected
    for line in text.splitlines():
        if line.startswith("ARTIFACT:"):
            remote = line.split(":", 1)[1].strip()
            local_dest = local_dir / Path(remote).name
            try:
                conn.get(remote, local=str(local_dest))
                print(f"  Artifact fetched: {local_dest}")
                collected.append(str(local_dest))
            except Exception as exc:
                print(f"  [WARN] Could not fetch artifact {remote}: {exc}")
    return collected

def timestamp():
    """Return current timestamp in date -d style format."""
    return datetime.now().strftime("%a %b %d %H:%M:%S %Y")

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

def run_command(cmd, cwd=None, verbose=False, capture_output=False, show_spinner=False):
    import threading
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
    output_lines = []
    if show_spinner:
        # Read stdout in background thread to prevent blocking
        def drain_output():
            for line in process.stdout:
                output_lines.append(line)
        reader = threading.Thread(target=drain_output)
        reader.start()
        # Show spinner while process runs
        spinner = ['|', '/', '-', '\\']
        spin_idx = 0
        while process.poll() is None:
            print(f"\r  {spinner[spin_idx]} syncing...", end='', flush=True)
            spin_idx = (spin_idx + 1) % 4
            time.sleep(0.2)
        reader.join()
        print("\r  done.          ")
    else:
        for line in process.stdout:
            print(line, end='')
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

def main(pipeline_yaml_path: str, skip_build: bool, no_run: bool, partial_build: bool, no_install: bool, args_exec_mode: Optional[str] = None):
    print_banner()

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

    # Initialize output directory for this run
    run_dir = init_run_directory(pipeline_yaml_path)
    print(f"{BOLD}Output directory: {run_dir}{RESET}")

    remote_username = cfg.get("user", {}).get("remote_username")
    remote_machine = cfg.get("user", {}).get("remote_machine_url")
    remote_transfer_machine = cfg.get("user", {}).get("remote_transfer_machine")
    machine_file = cfg.get("user", {}).get("machine_file")
    # "local" and "remote" are from the perspective of proxy mode (running on a laptop).
    # In direct mode (running on the HPC login node) local_path is overridden to remote_path
    # below, so local_build_dir is unused and need not exist on the HPC.
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

    # Determine execution context
    exec_mode = resolve_exec_mode(args_exec_mode or cfg.get('exec_mode'))
    has_internet = check_internet()
    if exec_mode == 'direct':
        print(f"{BOLD}Execution mode: direct (running on HPC, filesystem and job submission available locally){RESET}")
    else:
        print(f"{BOLD}Execution mode: proxy (will connect via SSH to {remote_machine}){RESET}")
    if has_internet:
        print("Internet connectivity: OK")
    else:
        print("Internet connectivity: NONE — steps requiring git access will fail")

    # Establish connection (or use local execution in direct mode)
    script_dir = Path(__file__).resolve().parent
    if exec_mode == 'direct':
        # In direct mode the build workspace mirrors what proxy mode creates at remote_path/ifsnemo-build/.
        # We populate it from the ifsnemo-build clone that sits next to this script on the HPC.
        build_source_dir = script_dir.parent / "ifsnemo-build"
        if not build_source_dir.is_dir():
            print(f"ERROR: expected ifsnemo-build clone at {build_source_dir} (sibling of ifsnemo-compare). "
                  f"Clone it there or adjust the path.")
            sys.exit(1)
        local_path = Path(remote_path) / "ifsnemo-build"
        local_path.mkdir(parents=True, exist_ok=True)
        conn = LocalConnection()
    else:
        build_source_dir = local_path
        if Connection is None:
            print("ERROR: proxy mode requires the 'fabric' package. Install it with: pip install fabric")
            sys.exit(1)
        conn = Connection(f"{remote_username}@{remote_machine}")

    run_command(["git", "submodule", "update", "--init", "--recursive"], cwd=build_source_dir, verbose=verbose)

    if exec_mode == 'direct':
        print(f"{BOLD}Syncing ifsnemo-build to workspace: {local_path} [{timestamp()}]{RESET}")
        run_command(["rsync", "-rlpgoDt", "--exclude", ".git", "--exclude", "src",
                     str(build_source_dir) + "/", str(local_path) + "/"], verbose=verbose)
    check_remote_requirements(conn, verbose=True)

    # Handle flag interactions
    if skip_build and partial_build:
        print("Warning: --partial-build is ignored when --skip-build is set")
        partial_build = False

    if skip_build and no_install:
        print("Warning: --no-install is ignored when --skip-build is set")
        no_install = False

    if skip_build:
        # If we skip the build, the remote tests directory may not be empty.
        # We'd have to delete any subdirectory in there that corresponds to the
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
        if ov.get('DNB_IFSNEMO_INPROOT'):
            overrides_content.append(f'  - export DNB_IFSNEMO_INPROOT="{ov.get("DNB_IFSNEMO_INPROOT")}"')
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
        # Set DNB_IFSNEMO_USE_ARCH_AND_RAPS to TRUE by default, but allow overriding this value
        use_arch_and_raps = ov.get('DNB_IFSNEMO_USE_ARCH_AND_RAPS', 'TRUE')
        overrides_content.append(f'  - export DNB_IFSNEMO_USE_ARCH_AND_RAPS={use_arch_and_raps}')

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

        # Link to machine config
        run_command(['ln', '-sf', machine_file, 'machine.yaml'], cwd=local_path, verbose=verbose)

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

            print(f"{BOLD}Fetching references: {ref_url} (branch: {ref_branch}) [{timestamp()}]{RESET}")
            run_command(["git", "clone", "--depth", "1", "--branch", ref_branch, ref_url, str(temp_ref_dir)], verbose=verbose)

            source_path = temp_ref_dir / ref_path_in_repo
            target_path = local_path / "references"

            if target_path.exists():
                shutil.rmtree(target_path)

            print(f"Copying {source_path} to {target_path}")
            shutil.copytree(source_path, target_path)

            # Also copy .git to enable git-restore-mtime on references
            git_source = temp_ref_dir / ".git"
            git_target = target_path / ".git"
            if git_source.exists():
                print(f"Copying .git to {target_path}")
                shutil.copytree(git_source, git_target)

            print(f"Cleaning up {temp_ref_dir}")
            shutil.rmtree(temp_ref_dir)

        # Create src folder for dnb.sh :du
        (local_path / "src").mkdir(exist_ok=True, parents=True)

        # MN5 (and similar HPC nodes) block outbound SSH port 22, so git@github.com: URLs fail.
        # Detect this and inject a git URL rewrite via env vars for the duration of :du.
        gh_env = github_https_env(conn)
        if gh_env:
            print("GitHub SSH (port 22) not available — applying HTTPS URL rewrite for git clones")
            os.environ.update(gh_env)

        # Run './dnb.sh :du' from within local_path
        run_command(['./dnb.sh', ':du'], cwd=local_path, verbose=verbose)

        # Copy local ifsnemo-compare into the local_path
        script_dir = Path(__file__).resolve().parent
        subprocess.run(["rm", "-fr", str(local_path) + "/ifsnemo-compare"], check=True)
        rsync_compare_cmd = [
            "rsync", "-a", "--exclude", ".git", "--exclude", "__pycache__", "--exclude", "*.log",
            str(script_dir) + "/",
            str(local_path) + "/ifsnemo-compare/"
        ]
        run_command(rsync_compare_cmd, verbose=verbose, show_spinner=True)

        # Restore modification times on git-controlled source files
        print(f"{BOLD}Restoring modification times for git-controlled sources... [{timestamp()}]{RESET}")
        src_path = local_path / "src"
        git_restore_mtime_script = local_path / "ifsnemo-compare" / "git-restore-mtime"

        def restore_mtimes_recursive(root_dir, base_path):
            """Recursively find and process all git repositories"""
            for item in root_dir.iterdir():
                if not item.is_dir():
                    continue

                # Skip symlinks to avoid infinite loops
                if item.is_symlink():
                    continue

                rel_path = item.relative_to(base_path)

                if (item / ".git").exists():
                    print(f"  Restoring mtimes in {rel_path}...")
                    try:
                        run_command(
                            [str(git_restore_mtime_script), "--quiet"],
                            cwd=item,
                            verbose=verbose
                        )
                    except Exception as e:
                        print(f"  [WARN] git-restore-mtime failed for {rel_path}: {e}")

                # Recurse into subdirectories
                try:
                    restore_mtimes_recursive(item, base_path)
                except (PermissionError, OSError):
                    pass

        if src_path.exists() and git_restore_mtime_script.exists():
            restore_mtimes_recursive(src_path, src_path)
        else:
            if not src_path.exists():
                print(f"  [INFO] No src directory found at {src_path}, skipping mtime restoration")
            if not git_restore_mtime_script.exists():
                print(f"  [WARN] git-restore-mtime script not found at {git_restore_mtime_script}")

        # Also restore mtimes for references if it's git-controlled
        references_path = local_path / "references"
        if references_path.exists() and (references_path / ".git").exists() and git_restore_mtime_script.exists():
            print(f"  Restoring mtimes in references...")
            try:
                run_command(
                    [str(git_restore_mtime_script), "--quiet"],
                    cwd=references_path,
                    verbose=verbose
                )
            except Exception as e:
                print(f"  [WARN] git-restore-mtime failed for references: {e}")

        ############################################
        # 2.1-2.3 Build and Install on remote
        ############################################

        # In proxy mode, rsync local ifsnemo-build workspace to the remote.
        # In direct mode we're already on the HPC — local_path IS the workspace, nothing to sync.
        if exec_mode == 'proxy':
            rsync_machine = remote_transfer_machine if remote_transfer_machine else remote_machine
            print(f"Ensuring remote directory {remote_path}/ifsnemo-build exists...")
            conn.run(f"mkdir -p '{remote_path}/ifsnemo-build'")
            print(f"{BOLD}Syncing to remote: {remote_username}@{rsync_machine}:{remote_path}/ifsnemo-build/ [{timestamp()}]{RESET}")
            rsync_cmd = [
                "rsync", "-rlpgoDt", "--compress", "--info=progress2,stats2", "--itemize-changes",
                str(local_path) + "/",
                f"{remote_username}@{rsync_machine}:{remote_path}/ifsnemo-build/"
            ]
            run_command(rsync_cmd, verbose=verbose, show_spinner=True)

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

        if exec_mode == 'direct':
            Path(remote_path).joinpath("ifsnemo_build_dnb_b.sbatch").write_text(sbatch_script)
        else:
            Path("ifsnemo_build_dnb_b.sbatch").write_text(sbatch_script)
            conn.put("ifsnemo_build_dnb_b.sbatch", f"{remote_path}/ifsnemo_build_dnb_b.sbatch")

        # Run the build on compute node with sbatch job
        print(f"{BOLD}Submitting build job to remote... [{timestamp()}]{RESET}")
        job_output = conn.run(f"cd {remote_path} && sbatch ifsnemo_build_dnb_b.sbatch", hide=True)

        # Wait until completion
        job_id = job_output.stdout.strip().split()[-1]
        wait_for_job(conn, job_id)

        #~ WIP ~ testing until here; return after build step's done.
        return

        # Run ./dnb.sh :i on login node (unless --no-install specified)
        if no_install:
            print(f"{BOLD}Skipping install step (--no-install).{RESET}")
        else:
            print(f"{BOLD}Running install step (./dnb.sh :i)... [{timestamp()}]{RESET}")
            conn.run(f"cd {remote_path}/ifsnemo-build && ./dnb.sh :i")

            # Copy references into the test arena if they exist (only when install ran)
            if "references" in cfg:
                conn.run(f"rsync -a {remote_path}/ifsnemo-build/references/ {remote_path}/ifsnemo-build/ifsnemo/references/")

    test_results = {}
    results_file = run_dir / "test_results.json"

    # Explicitly handle the case where the user asked to skip run/compare
    if no_run:
        print(f"{BOLD}Skipping run and compare stages (--no-run).{RESET}")
    else:
        # Load test definitions
        print(f"{BOLD}Starting test execution... [{timestamp()}]{RESET}")
        test_defs_path = ifs_cfg.get('test_definitions_file', 'test_definitions.yaml')
        test_defs = load_test_definitions(test_defs_path)

        # Derive machine key from machine_file stem (e.g. "dnb-mn5-gpp.yaml" -> "dnb-mn5-gpp")
        machine_key = Path(machine_file).stem if machine_file else ''
        machine_pre_commands = test_defs.get('machine_pre_commands', {}).get(machine_key, {})

        # === Build suites (run once per build) ===
        default_build_suites = test_defs.get('default_build_suites', [])
        requested_build_suites = ifs_cfg.get('build_suites', default_build_suites)

        if requested_build_suites:
            # Validate build suites exist
            validate_test_definitions(test_defs, cfg, requested_build_suites, suite_type='build_suites')

            # Build context for build suites
            build_context = {
                'remote_path': str(remote_path),
                'bundle_yaml': f"{remote_path}/ifsnemo-build/src/ifsnemo-XXX.src/bundle.yml",
                'build_dir': f"{remote_path}/ifsnemo-build/src/ifsnemo-XXX.src/build",
                'gold_standard_tag': gold_standard_tag,
            }

            # Validate build context
            build_required = test_defs.get('build_required_params', [])
            missing = [p for p in build_required if p not in build_context]
            if missing:
                raise ValueError(f"Build context missing required params: {missing}")

            test_results['build'] = {}
            for suite_name in requested_build_suites:
                suite_def = test_defs['build_suites'][suite_name]
                sequence = suite_def.get('sequence', [])

                for cmd_name in sequence:
                    print(f"{BOLD}Running build suite {suite_name}:{cmd_name}...{RESET}")
                    results = execute_test(
                        conn, suite_name, suite_def, cmd_name, build_context,
                        'build', verbose=verbose
                    )
                    test_results['build'].update(results)

        # === Test suites (run per configuration) ===
        if not (resolution and steps and threads and ppn and nodes):
            print("No test configurations found; skipping per-config test suites.")
        else:
            default_test_suites = test_defs.get('default_test_suites', [])
            requested_test_suites = ifs_cfg.get('test_suites', default_test_suites)

            if requested_test_suites:
                # Validate test suites exist
                validate_test_definitions(test_defs, cfg, requested_test_suites, suite_type='test_suites')

                use_gpu = str(ov.get('DNB_IFSNEMO_WITH_GPU', 'FALSE')).upper() == 'TRUE'
                loop_items = [resolution, steps, threads, ppn, nodes]
                if use_gpu:
                    loop_items.append(gpus)

                # Ensure all elements are lists for zip
                loop_items = [x if isinstance(x, list) else [x] for x in loop_items]

                for items in zip(*loop_items):
                    # Unpack test parameters and build test_id
                    if use_gpu:
                        r, s, t, p, n, g = items
                        test_id = f"r{r}_s{s}_t{t}_p{p}_n{n}_g{g}"
                        gpu_flag = f" --gpus {quote(str(g))}"
                    else:
                        r, s, t, p, n = items
                        test_id = f"r{r}_s{s}_t{t}_p{p}_n{n}"
                        gpu_flag = ""

                    print(f"{BOLD}Processing test config: {test_id}{RESET}")
                    test_results[test_id] = {}

                    # Build context for template substitution
                    _pipeline_name = Path(pipeline_yaml_path).name
                    _machine_name  = Path(machine_file).stem if machine_file else 'unknown'
                    _run_ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
                    test_context = {
                        'remote_path': str(remote_path),
                        'test_subdir': dnb_sandbox_subdir,
                        'gold_standard_tag': gold_standard_tag,
                        'resolution': r,
                        'steps': s,
                        'threads': t,
                        'ppn': p,
                        'nodes': n,
                        'gpu_flag': gpu_flag,
                        'annotation': f"pipeline: {_pipeline_name} | machine: {_machine_name} | run: {_run_ts}",
                    }
                    if use_gpu:
                        test_context['gpus'] = g

                    # Validate test context
                    test_required = test_defs.get('test_required_params', [])
                    missing = [p for p in test_required if p not in test_context]
                    if missing:
                        raise ValueError(f"Test context missing required params: {missing}")

                    # Execute each requested test suite
                    for suite_name in requested_test_suites:
                        suite_def = test_defs['test_suites'][suite_name]
                        sequence = suite_def.get('sequence', [])

                        for cmd_name in sequence:
                            print(f"{BOLD}Running {suite_name}:{cmd_name}...{RESET}")
                            results = execute_test(
                                conn, suite_name, suite_def, cmd_name, test_context,
                                test_id, verbose=verbose,
                                pre_cmd=machine_pre_commands.get(cmd_name, ''),
                            )
                            test_results[test_id].update(results)
                            log_path = Path(results.get(
                                next(k for k in results if k.endswith('_output')), ''))
                            if log_path.exists():
                                collect_artifacts(conn, log_path, run_dir)

    # Write the results to a JSON file
    with open(results_file, "w") as f:
        json.dump(test_results, f, indent=4)
    print(f"{BOLD}Test results written to {results_file} [{timestamp()}]{RESET}")

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
    parser.add_argument(
        "--no-install",
        dest="no_install",
        action="store_true",
        help="Skip the install step (dnb.sh :i) after building. Use when you don't need to set up the sandbox or want to avoid the potentially long install phase."
    )
    parser.add_argument(
        "--exec-mode",
        dest="exec_mode",
        choices=["direct", "proxy"],
        default=None,
        help=(
            "Execution mode: 'direct' if this machine has filesystem access and can submit jobs "
            "on the target HPC system directly; 'proxy' if you need SSH to reach it. "
            "If omitted, you will be prompted interactively."
        ),
    )
    args = parser.parse_args()

    try:
        main(args.pipeline_yaml, args.skip_build, args.no_run, args.partial_build, args.no_install, args.exec_mode)
    except Exception as e:
        print("ERROR:", e)
        # Print traceback for easier debugging
        import traceback
        traceback.print_exc()
        sys.exit(1)
    else:
        sys.exit(0)
