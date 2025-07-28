import yaml
import subprocess
from pathlib import Path
from fabric import Connection

with open("pipeline.yaml", "r") as f:
    cfg = yaml.safe_load(f)

ecmwf_username = cfg["user"]["ecmwf_username"]
remote_username = cfg["user"]["remote_username"]
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
#TODO fill in intermediate steps
# Create tarball
#subprocess.run(["tar", "czvf", "../ifsnemo-build.tar.gz", "."], cwd=local_path)
#
## Upload the tarball
#conn = Connection(f"{remote_username}@glogin4.bsc.es")
#conn.put("../ifsnemo-build.tar.gz", remote=remote_path + "/ifsnemo-build.tar.gz")
