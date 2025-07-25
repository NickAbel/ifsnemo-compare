import yaml
import subprocess
from pathlib import Path
from fabric import Connection

with open("pipeline.cfg", "r") as f:
    cfg = yaml.safe_load(f)

username = cfg["user"]["username"]
remote_path = cfg["paths"]["remote_project_dir"]
local_path = Path(cfg["paths"]["local_build_dir"])
#TODO fill in intermediate steps
# Generate overrides.yaml
#TODO expand for non-default cases
(local_path / "overrides.yaml").write_text(f"""---
environment:
  - export DNB_SANDBOX_SUBDIR="{cfg['overrides']['DNB_SANDBOX_SUBDIR']}"
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
subprocess.run(["tar", "czvf", "../ifsnemo-build.tar.gz", "."], cwd=local_path)

# Upload the tarball
conn = Connection(f"{username}@glogin4.bsc.es")
conn.put("../ifsnemo-build.tar.gz", remote=remote_path + "/ifsnemo-build.tar.gz")
