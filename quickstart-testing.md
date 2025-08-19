## Prerequisites

1. **ifsnemo-build** access. Full setup instructions:
   
   [ifsnemo-build repository](https://earth.bsc.es/gitlab/digital-twins/nvidia/ifsnemo-build)

   [ifsnemo-build instructions](https://hackmd.io/@mxKVWCKbQd6NvRm0h72YpQ/SkHOb6FZgg)
   
2. `pyyaml` and `fabric` Python packages.

3. **MN5 and ECMWF Bitbucket**  access.

---

### Install `yq` on your local machine

```bash
mkdir -p ~/bin
wget https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64 -O ~/bin/yq
chmod +x ~/bin/yq

# Ensure ~/bin is in your PATH
echo 'export PATH="$HOME/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

> **Tip:** `yq` doesn't have to be placed in `~/bin`, this is shown for example only. The `dnb.sh` script run below expects `yq` to be in the PATH.

### Configure GitLab Access (for `generic-hpc-scripts`) on your local machine

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

### Configure ECMWF Bitbucket Access on your local machine

Log in to your ECMWF account and access your account management page here:
https://git.ecmwf.int/account

Go to "HTTP access tokens -> Create token"

You may choose any name you like and the default options as below are acceptable

<img width="617" height="586" alt="image" src="https://github.com/user-attachments/assets/ce1a17c2-4e3a-407c-8980-7755a5cecbab" />

On the following page, you will see "New access token created
You'll not be able to view this token again."

Add to the ~/.netrc:

```
machine git.ecmwf.int
login XXXXXX
password XXXXXXXXXXXXXXXX
```

where you may see your login name at https://git.ecmwf.int/profile
for instance
mine is `ecme0874`
<img width="324" height="130" alt="image" src="https://github.com/user-attachments/assets/c34813c4-eb30-472d-bd53-ab06ce507fe9" />


### Clone and Configure `ifsnemo-build` on your local machine

```bash
git clone --recursive https://earth.bsc.es/gitlab/digital-twins/nvidia/ifsnemo-build.git
cd ifsnemo-build

# Link to generic machine config
ln -s dnb-generic.yaml machine.yaml
```

### Prepare Utilities on your Login Node

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

> **Tip:** `yq` and `psubmit` do not necessarily have to be placed in `~/bin`, this is shown for example only. The `dnb.sh` script and `ifsnemo-compare` tools expect `yq` and `psubmit` to be in the PATH.

### Create your pipeline.yaml

`pipeline.yaml.example` is a template, but I can explain anything else

### Run the pipeline on your local machine

From the command line, run
`python3 pipeline.py`
