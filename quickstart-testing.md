# Getting Started Guide

## 1. Prerequisites

Before you begin, ensure you have:

### 1.1. ifsnemo-build access
- For full setup details, visit:
  - [ifsnemo-build repository](https://earth.bsc.es/gitlab/digital-twins/nvidia/ifsnemo-build)
  - [ifsnemo-build instructions](https://hackmd.io/@mxKVWCKbQd6NvRm0h72YpQ/SkHOb6FZgg)

### 1.2. Required Python packages (installed on local machine)
We recommend creating a dedicated Python virtual environment for this project:
```bash
# Create environment
python3 -m venv ifsnemo-compare

# Activate environment
source ifsnemo-compare/bin/activate

# Install required packages
pip3 install fabric pyyaml

# Deactivate environment (when needed)
deactivate
```

### 1.3. Access to required platforms
- MN5
- ECMWF Bitbucket (see section 2.3 for detailed access requirements)

---

## 2. Local Machine Setup

First, create a dedicated project directory to organize all the components:
```bash
mkdir ifsnemo-compare-project
cd ifsnemo-compare-project
# All subsequent clone operations will be performed in this directory
```

### 2.1. Install `yq`

```bash
mkdir -p ~/bin
wget https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64 -O ~/bin/yq
chmod +x ~/bin/yq

# Ensure ~/bin is in your PATH
echo 'export PATH="$HOME/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

> Note: While this example installs `yq` in `~/bin`, you can install it anywhere in your PATH. The `dnb.sh` script shown elsewhere expects `yq` to be available in PATH.

### 2.2. Configure GitLab Access (generic-hpc-scripts)

1. Generate a token:
   - Go to **Profile → Personal Access Tokens** on [earth.bsc.es](https://earth.bsc.es/gitlab/-/profile/personal_access_tokens)
   - Select all scopes
   - Remove the expiration date

   ![Token Creation](https://github.com/user-attachments/assets/665f5be5-9889-46b5-a77d-6f7a0b396262)

2. Create and copy your token:
   - Click **Create personal access token**
   - Copy the token when the page reloads

   ![Copy Token](https://github.com/user-attachments/assets/4c75d326-fa82-4e7a-a0b8-abfa18fafe02)

3. Add it to your `~/.netrc`:

```ini
machine earth.bsc.es
  login YOUR_USERNAME
  password YOUR_NEW_PERSONAL_ACCESS_TOKEN
```

### 2.3. Configure ECMWF Bitbucket Access

Important: Before proceeding with Bitbucket access setup, you must first:

1. Have an ECMWF account (https://ecmwf.int)
2. Request Bitbucket access:
   - Visit the [IFS Access Request Form](https://wiki.eduuni.fi/pages/viewpage.action?pageId=343558915&spaceKey=cscRDIcollaboration&title=IFS%2Baccess)
   - Fill out the form with the following details:
     - For "Group leader support/explanation": write "model development and integration testing"
     - For "Specific access needed to": write "Bitbucket (IFS-Sources/RAPS)"
   - Note: This is a monthly process and you will receive a confirmation email that you must acknowledge
   - Important: By requesting access, you agree to the terms, particularly that IFS source code must not be made publicly available

Once you have Bitbucket access:

1. Create an HTTP access token:
   - Log in to ECMWF: https://git.ecmwf.int/account
   - Under "HTTP access tokens" click **Create token** (default options are sufficient)

   ![ECMWF Token Creation](https://github.com/user-attachments/assets/ce1a17c2-4e3a-407c-8980-7755a5cecbab)

2. Copy the token when prompted (you won't see it again).

3. Add it to your `~/.netrc`:

```ini
machine git.ecmwf.int
  login YOUR_ECMWF_USERNAME
  password YOUR_NEW_ACCESS_TOKEN
```

> Note: You can find your ECMWF username at https://git.ecmwf.int/profile (example: ecme0874).

   ![ECMWF Username Example](https://github.com/user-attachments/assets/c34813c4-eb30-472d-bd53-ab06ce507fe9)

### 2.4. Clone and Configure ifsnemo-build
In this step, we'll clone the ifsnemo-build repository and set up the necessary configuration:

```bash
git clone --recursive https://earth.bsc.es/gitlab/digital-twins/nvidia/ifsnemo-build.git
cd ifsnemo-build
git checkout nabel-main-patch-75101

# Link to generic machine config
ln -s dnb-generic.yaml machine.yaml
```

### 2.5. Clone ifsnemo-compare
Now we'll clone the main comparison tool repository:

```bash
cd ..  # Return to project root directory
git clone https://github.com/NickAbel/ifsnemo-compare.git
```

---

## 3. Login Node Setup

> Note: This step assumes the availability and existence of an internet-connected login node. If this is not the case, download `yq` and `psubmit` and use `scp`, etc. as needed.

SSH into your internet-connected login node (in this case, `glogin4`) and prepare utilities:

```bash
ssh bscXXXXXX@glogin4.bsc.es
mkdir -p ~/bin && cd ~/bin

# yq (if not already present)
wget -q https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64 -O ./yq && chmod +x ./yq

# psubmit helper
git clone https://github.com/a-v-medvedev/psubmit.git tmp-ps
chmod +x tmp-ps/
mv tmp-ps/*.sh . && rm -fr tmp-ps

# Ensure bin is in PATH
echo 'export PATH="$HOME/bin:$PATH"' >> ~/.bashrc && source ~/.bashrc
```

> Tip: `yq` and `psubmit` do not have to live in `~/bin`; this is shown as an example. The `dnb.sh` script and other tools expect these utilities to be available in PATH.

---

## 4. Create your pipeline.yaml

The pipeline configuration file `pipeline.yaml` should be created in the `ifsnemo-compare` directory. Follow these steps:

1. Navigate to the ifsnemo-compare directory:
   ```bash
   cd ifsnemo-compare
   ```

2. Copy the example configuration file:
   ```bash
   cp pipeline.yaml.example pipeline.yaml
   ```

3. Edit `pipeline.yaml` with your specific settings. Below is a complete list of available options:

```yaml
# User configuration
user:
  remote_username: string          # Your username on the remote machine (e.g., bscXXXXXX)
  remote_machine_url: string      # Remote machine address (e.g., glogin4.bsc.es)
  machine_file: string           # Machine configuration file to use (e.g., dnb-mn5-gpp.yaml)

# Path configuration
paths:
  local_bin_dir: string          # (DEPRECATED) Path to local binary directory 
  local_build_dir: string        # Path to ifsnemo-build directory on local machine. (Step 2.4)
  remote_bin_dir: string         # (DEPRECATED) Path to remote binary directory
  remote_project_dir: string     # Path to remote project directory. Will be created if it doesn't exist.

# Override settings
overrides:
  DNB_SANDBOX_SUBDIR: string     # Sandbox subdirectory name (e.g., "ifsFOOBAR.SP.CPU.GPP") 
  DNB_IFSNEMO_URL: string        # IFSNEMO URL (e.g., "https://git.ecmwf.int/scm/~ecmeXXXX") (see pipeline-20250521-nabel.yaml and quickstart.md for guidance)
  IFS_BUNDLE_IFS_SOURCE_GIT: string # IFS source Git URL (can use $DNB_IFSNEMO_URL variable) (see pipeline-20250521-nabel.yaml and quickstart.md for guidance)
  IFS_BUNDLE_IFS_SOURCE_VERSION: string # Branch or version to use (see pipeline-20250521-nabel.yaml and quickstart.md for guidance)
  DNB_IFSNEMO_BUNDLE_BRANCH: string    # Optional bundle branch specification (see pipeline-20250521-nabel.yaml and quickstart.md for guidance)

# SLURM submission settings
psubmit:
  queue_name: string             # Queue name (can be empty string) (see pipeline-20250521-nabel.yaml for guidance)
  account: string               # Account name (e.g., ehpc01) (see pipeline-20250521-nabel.yaml for guidance)
  node_type: string            # Node type (e.g., gp_ehpc) (see pipeline-20250521-nabel.yaml for guidance)

# IFS-NEMO comparison settings
ifsnemo_compare:
  gold_standard_tag: string     # Reference tag (e.g., "ifs.DE_CY48R1.0_climateDT_20250521.SP.CPU.GPP") (see https://github.com/kellekai/bsc-ndse/tree/main/references for all available tags)
  # Test configuration arrays (the five arrays below all must have matching lengths)
  resolution: []               # Array of resolutions (e.g., ["tco79-eORCA1", "tco399-eORCA025"])
  steps: []                   # Array of steps (e.g., ["d1", "d1"])
  threads: []                 # Array of thread counts (e.g., [4, 4])
  ppn: []                    # Array of processes per node (e.g., [28, 28])
  nodes: []                  # Array of node counts (e.g., [1, 16])

# Reference configuration (optional)
references:
  url: string                 # Git URL for references repository (e.g https://github.com/kellekai/bsc-ndse/) (see pipeline-20250521-nabel.yaml for guidance)
  branch: string             # Branch to use (defaults to "main" if not specified) (see pipeline-20250521-nabel.yaml for guidance)
  path_in_repo: string       # Path within the repository where references are located (probably "references") (see https://github.com/kellekai/bsc-ndse/tree/main/references)
```

For guidance on specific values, refer to [a personal pipeline.yaml to test the develop branch](./pipeline-20250521-nabel.yaml). For instructions on creating your own fork in ECMWF Bitbucket for testing, see [How to create a fork](./quickstart.md#how-to-create-a-fork-of-ifssource-on-ecmwf-bitbucket).

---

## 5. Run the pipeline on your local machine

Ensure your Python virtual environment is activated:
```bash
source ~/ifsnemo-compare/bin/activate
```

Then run the pipeline:
```bash
python3 pipeline.py
```

This will execute the pipeline using the configuration specified in `pipeline.yaml`.

## 6. Pipeline Options (Note: Advanced/Custom Use Only)

The pipeline script (`pipeline.py`) accepts several optional arguments:

- `-y, --yaml <path>`: Specify a custom path to the pipeline YAML file (default: pipeline.yaml)
- `-s, --skip-build`: Skip the build and install steps, only run tests and compare
- `--no-run`: Do the build/install but skip the run and compare stages

Example usage:
```bash
python3 pipeline.py --yaml custom-pipeline.yaml  # Use a custom config file
python3 pipeline.py --skip-build                # Skip build steps, only run tests
python3 pipeline.py --no-run                    # Only do build/install, no tests
```
