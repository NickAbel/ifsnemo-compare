# ifsnemo-compare quickstart (for testing purposes only)

> **Beware:** This version only checks out the latest version of IFS-NEMO from the `master` branch, and uses a symbolic link to it as a testing binary. It does not explain how to add a different branch or fork of IFS, RAPS, or ifs-bundle for comparison. See [this guide](./quickstart.md) for the full quick‑start steps.

---

## Prerequisites

1. **ifsnemo-build** access. Full setup instructions:
   
   [ifsnemo-build repository](https://earth.bsc.es/gitlab/digital-twins/nvidia/ifsnemo-build)

   [ifsnemo-build instructions](https://hackmd.io/@mxKVWCKbQd6NvRm0h72YpQ/SkHOb6FZgg)
   
3. **MN5 and ECMWF Bitbucket**  access.

---

## 1. Setup on Your Local Machine

### 1.1 Install `yq`

```bash
mkdir -p ~/bin
wget https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64 -O ~/bin/yq
chmod +x ~/bin/yq

# Ensure ~/bin is in your PATH
echo 'export PATH="$HOME/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

> **Tip:** `yq` doesn't have to be placed in `~/bin`, this is shown for example only. The `dnb.sh` script run below expects `yq` to be in the PATH.

### 1.2 Configure GitLab Access (for `generic-hpc-scripts`)

Generate a token under **Profile → Personal Access Tokens** on [earth.bsc.es](https://earth.bsc.es/gitlab/-/profile/personal_access_tokens). 

Select all scopes and remove the expiration date.

<img width="568" height="632" alt="image" src="https://github.com/user-attachments/assets/665f5be5-9889-46b5-a77d-6f7a0b396262" />

Click **Create personal access token**, and the page will reload. 

<img width="858" height="338" alt="image" src="https://github.com/user-attachments/assets/4c75d326-fa82-4e7a-a0b8-abfa18fafe02" />

Copy the contents of the field **Your new personal access token** into a new file on your local machine, `~/.netrc`, in the following format:

```ini
machine earth.bsc.es
  login YOUR_USERNAME
  password YOUR_NEW_PERSONAL_ACCESS_TOKEN
```

### 1.3 Clone and Configure `ifsnemo-build`

```bash
git clone --recursive https://earth.bsc.es/gitlab/digital-twins/nvidia/ifsnemo-build.git
cd ifsnemo-build

# Link to generic machine config
ln -s dnb-generic.yaml machine.yaml
```

Create these two files in `ifsnemo-build/`:

- `overrides.yaml`

  ```yaml
  ---
  environment:
    - export DNB_SANDBOX_SUBDIR="ifsMASTER.SP.CPU.GPP"
  ```

- `accounts.yaml`

  ```yaml
  ---
  psubmit:
    queue_name: ""
    account:     bsc32
    node_type:   gp_debug
  ```

### 1.4 Fetch and Package Build Artifacts

```bash
# Download required archives
./dnb.sh :du

# Create a compressed tarball for MN5 transfer
tar czvf ../ifsnemo-build.tar.gz .

# Copy to your projects dir on MN5 login node (adjust XXXXXX)
scp ../ifsnemo-build.tar.gz bscXXXXXX@glogin4.bsc.es:/gpfs/projects/bsc32/bscXXXXXX/
```

> **Beware:** The `tar czvf` command may take a few minutes. So will the `scp` command, but it will show you a progress bar.

---

## 2. Build on MN5 GPP

### 2.1 Prepare Utilities on Login Node

```bash
ssh bscXXXXXX@glogin4.bsc.es
mkdir -p ~/bin && cd ~/bin

# yq (if not already present)
wget -q https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64 -O ./yq && chmod +x ./yq

# psubmit helper
git clone https://github.com/a-v-medvedev/psubmit.git tmp-ps
mv tmp-ps/psubmit . && rm -rf tmp-ps
chmod +x psubmit

# Ensure bin is in PATH
echo 'export PATH="$HOME/bin:$PATH"' >> ~/.bashrc && source ~/.bashrc
```

> **Tip:** `yq` and `psubmit` do not necessarily have to be placed in `~/bin`, this is shown for example only. The `dnb.sh` script and `ifsnemo-compare` tools expect `yq` and `psubmit` to be in the PATH.

### 2.2 Request an Interactive Node

```bash
salloc --qos=gp_debug --partition=standard -A ehpc01 \
       -c 112 --nodes=1 -t 02:00:00 --exclusive
```

### 2.3 Untar, Build and Install

```bash
cd /gpfs/projects/bsc32/bscXXXXXX/
tar xzvf ifsnemo-build.tar.gz --one-top-level
cd ifsnemo-build

# Set machine file to MN5-GPP
ln -sf dnb-mn5-gpp.yaml machine.yaml

# Build on the compute node
./dnb.sh :b

# Exit allocation!! (Ctrl+D)
# Install - on a login node!!
./dnb.sh :i
```

> **Beware:** The `tar xzvf`, `./dnb.sh :b` and `./dnb.sh :i` commands may take a few minutes.

---

## 3. Run a Quick Example

From your `ifsnemo-build/ifsnemo` testbed directory:

```bash
psubmit.sh -n 1 -u ifsMASTER.SP.CPU.GPP
```

Which should complete without complaint.

---

## 4. Install and Use `ifsnemo-compare`

```bash
# Clone into your build tree
cd ifsnemo-build/ifsnemo
git clone https://github.com/NickAbel/ifsnemo-compare.git compare-tmp
mv compare-tmp/* .
rm -rf compare-tmp
```

### 4.1 Create Reference Outputs

```bash
python3 compare_norms.py create-refs \
  -g ifsMASTER.SP.CPU.GPP/ \
  -r tco79-eORCA1 \
  -s 1 -n 1
```

This submits a gold-standard run and stores outputs under:

```
compare_norms_refs/ifsMASTER.SP.CPU.GPP/tco79-eORCA1/nsteps1/nnodes1/
```

### 4.2 Compare Against a "Lite" Binary

We don't actually have a `ifsLITE.SP.CPU.GPP` binary to compare, so we will fake one:

```bash
ln -sf ifsMASTER.SP.CPU.GPP/ ifsLITE.SP.CPU.GPP
```

Then run:

```bash
python3 compare_norms.py compare \
  -g ifsMASTER.SP.CPU.GPP/ \
  -t ifsLITE.SP.CPU.GPP/ \
  -r tco79-eORCA1 -s 1 -n 1
```

Results will flag any non-zero differences in the two binaries' output L2 norms, or missing/extra timesteps.

Since the two binaries are the same, we expect no differences.
