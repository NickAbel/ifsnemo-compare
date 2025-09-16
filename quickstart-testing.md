# Getting Started Guide

## 1. Prerequisites

Before you begin, ensure you have:

### 1.1. ifsnemo-build access
- For full setup details, visit:
  - [ifsnemo-build repository](https://earth.bsc.es/gitlab/digital-twins/nvidia/ifsnemo-build)
  - [ifsnemo-build instructions](https://hackmd.io/@mxKVWCKbQd6NvRm0h72YpQ/SkHOb6FZgg)

### 1.2. Required Python packages (installed on local machine)
- pyyaml
- fabric

### 1.3. Access to required platforms
- MN5
- ECMWF Bitbucket

---

## 2. Local Machine Setup

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

### 2.4. Clone and Configure `ifsnemo-build`, Check Out nabel-main-patch-75101

```bash
git clone --recursive https://earth.bsc.es/gitlab/digital-twins/nvidia/ifsnemo-build.git
cd ifsnemo-build
git checkout nabel-main-patch-75101

# Link to generic machine config
ln -s dnb-generic.yaml machine.yaml
```

---

## 3. Login Node Setup

SSH into your login node and prepare utilities:

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

- By default, `pipeline.py` expects a YAML file, `pipeline.yaml`, in the main directory.
- Use `pipeline.yaml.example` as a starting point.
- Customize options as needed; ask if you want help with any setting.

---

## 5. Run the pipeline on your local machine

From the command line:

```bash
python3 pipeline.py
```

This will execute the pipeline using the configuration specified in `pipeline.yaml` by default.

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
