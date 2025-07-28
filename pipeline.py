import yaml
import subprocess
from pathlib import Path
from fabric import Connection
import shutil

verbose = True

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
remote_machine = cfg["user"]["remote_machine"]
remote_path = cfg["paths"]["remote_project_dir"]
local_path = Path(cfg["paths"]["local_build_dir"])

ov = cfg["overrides"]

ifs_source_git_url = ov["IFS_BUNDLE_IFS_SOURCE_GIT"].format(**ov)

# Generate overrides.yaml
(local_path / "overrides.yaml").write_text(f"""---
environment:
  - export DNB_SANDBOX_SUBDIR="{ov['DNB_SANDBOX_SUBDIR']}"
  - export DNB_IFSNEMO_URL="{ov['DNB_IFSNEMO_URL']}"
  - export IFS_BUNDLE_IFS_SOURCE_VERSION="{ov['IFS_BUNDLE_IFS_SOURCE_VERSION']}"
  - export IFS_BUNDLE_IFS_SOURCE_GIT="{ifs_source_git_url}"
""")

# Generate accounts.yaml
(local_path / "accounts.yaml").write_text(f"""---
psubmit:
  queue_name: "{cfg['psubmit']['queue_name']}"
  account:     {cfg['psubmit']['account']}
  node_type:   {cfg['psubmit']['node_type']}
""")


############################################
# 1.4 Fetch and Package Build Artifacts
############################################

## Run './dnb.sh :du' from within local_path
#run_command(['./dnb.sh', ':du'], cwd=local_path, verbose=verbose)
#
## Create tarball
#run_command(["tar", "czvf", "../ifsnemo-build.tar.gz", "."], cwd=local_path, verbose=verbose)

# Upload the tarball
conn = Connection(f"{remote_username}@{remote_machine}")
local_path = Path(local_path)
remote_path = Path(remote_path)
upload_file(conn, local_path / "../ifsnemo-build.tar.gz", remote_path / "ifsnemo-build.tar.gz", verbose=verbose)
