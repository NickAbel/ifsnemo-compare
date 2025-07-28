import yaml
import subprocess
from pathlib import Path
from fabric import Connection
import shutil


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

# Run './dnb.sh :du' from within local_path
result = subprocess.run(['./dnb.sh', ':du'], cwd=local_path, capture_output=True, text=True)

# Print the output
print(result.stdout)
if result.stderr:
    print("Error output:", result.stderr)

# Create tarball
subprocess.run(["tar", "czvf", "../ifsnemo-build.tar.gz", "."], cwd=local_path)

## Upload the tarball
conn = Connection(f"{remote_username}@{remote_machine}")
conn.put(f"{local_path}/../ifsnemo-build.tar.gz", remote=remote_path + "/ifsnemo-build.tar.gz")
