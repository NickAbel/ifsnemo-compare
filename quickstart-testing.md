# Getting Started Guide

## 0. Introduction

This document describes how to use the `ifsnemo-compare` tool to run regression tests for the IFS-NEMO model. 

The tool automates the process of building the model, running a set of predefined tests, and comparing the results against a set of gold standards.

> **Tip:** `install.py` walks you through Sections 1-3 of this guide interactively, checking what's already done and only prompting for what's missing. It's safe to re-run.

## 1. Prerequisites

Before you begin, ensure you have:

### 1.1. Access to the required repositories

You need read access to:
- the [ifsnemo-build repository](https://earth.bsc.es/gitlab/digital-twins/nvidia/ifsnemo-build) (Earth GitLab)
- the following ecmwf-ifs GitHub repositories:
  - [ifs-source](https://github.com/ecmwf-ifs/ifs-source)
  - [ifs-raps](https://github.com/ecmwf-ifs/ifs-raps)

**Note: For assistance with access to the repositories, please contact your supervisor! The ifsnemo-compare maintainers do not have any ability to grant access.** The steps below configure credentials for access you've already been granted; they can't grant access itself.

#### 1.1.a. Earth GitLab (ifsnemo-build)

The token is stored on shared HPC systems, so give it read-only access to code and nothing else. A leaked read-only token cannot push, change settings or act on your behalf.

1. Generate a fine-grained token at [gitlab.earth.bsc.es → Personal access tokens → Generate fine-grained token](https://gitlab.earth.bsc.es/-/user_settings/personal_access_tokens/granular/new):
   - **Name**: anything, e.g. `ifsnemo-build read-only`.
   - **Expiration date**: the maximum is 365 days; renew the token when GitLab reminds you.
   - **Group and project access**: *All groups and projects that I'm a member of*.
   - **Resource permissions**: under **Group and project**, add **Repository → Code** with only the **Download** permission. Leave every other resource unselected.

2. Create the token and copy it immediately; it is shown only once.

3. Add it to your `~/.netrc` and ensure it is only readable by you:

```ini
machine gitlab.earth.bsc.es
  login YOUR_USERNAME
  password YOUR_NEW_PERSONAL_ACCESS_TOKEN
```

```bash
chmod 600 ~/.netrc
```

4. Check that the token can read code:

```bash
git ls-remote https://gitlab.earth.bsc.es/digital-twins/nvidia/ifsnemo-build.git HEAD
```

   This should print a commit hash without asking for a password.

#### 1.1.b. ecmwf-ifs GitHub (ifs-raps, ifs-source)

1. From your [GitHub Keys page](https://github.com/settings/keys), under the SSH key you've created for your local machine, click "Configure SSO" and authorize "**ecmwf-ifs**", following the instructions.

2. Check access:

```bash
git ls-remote git@github.com:ecmwf-ifs/ifs-raps.git HEAD
git ls-remote git@github.com:ecmwf-ifs/ifs-source.git HEAD
```

   Each should print a commit hash. If you have not been granted access to `ifs-raps` and `ifs-source` in the ecmwf-ifs GitHub organization, the "Configure SSO" option won't be available -- see the note above.

### 1.2. Required Python packages (installed on local machine)
- [fabric](https://github.com/fabric/fabric), a remote execution package used by ifsnemo-compare's `pipeline.py` for automating commands on remote nodes.
- [pyyaml](https://github.com/yaml/pyyaml), a YAML parser used to read the pipeline YAML configuration files that drive ifsnemo-compare's `pipeline.py`.

Both are dependencies of ifsnemo-compare and must be installed.

### 1.3. Access to your target platform
- [MareNostrum 5](https://www.bsc.es/marenostrum/marenostrum-5)

## 2. Local Machine Setup

Create a dedicated project directory to organize all the components:
```bash
mkdir ifsnemo-compare-project
cd ifsnemo-compare-project
```

### 2.1. Install `yq`

[yq](https://github.com/mikefarah/yq) is a portable command-line YAML processor and a dependency of [ifsnemo-build](https://earth.bsc.es/gitlab/digital-twins/nvidia/ifsnemo-build), a necessary component of `ifsnemo-compare`.

`yq` must be in your PATH. For example, here is a simple way to add `yq` to `~/bin` and `~/bin` to your PATH:

```bash
mkdir -p ~/bin
wget https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64 -O ~/bin/yq
chmod +x ~/bin/yq

# Ensure ~/bin is in your PATH
echo 'export PATH="$HOME/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

> Note: While this example installs `yq` in `~/bin`, you can install it anywhere in your PATH. `ifsnemo-build`'s `dnb.sh` script shown elsewhere expects `yq` to be available in PATH.

### 2.2. Clone and Configure ifsnemo-build
In this step, we'll clone the ifsnemo-build repository and set up the necessary configuration:

```bash
git clone --recursive https://earth.bsc.es/gitlab/digital-twins/nvidia/ifsnemo-build.git
cd ifsnemo-build
git checkout cy49r3

# Link to generic machine config
ln -s dnb-generic.yaml machine.yaml
```

### 2.3. Clone ifsnemo-compare
If you have not done so already, be sure to clone the main comparison tool repository:

```bash
cd ..  # Return to project root directory
git clone https://github.com/NickAbel/ifsnemo-compare.git
```

---

## 3. Target Machine Setup

`yq` and `psubmit` are dependencies of `ifsnemo-build` and `ifsnemo-compare`, they both must be in `PATH` on your target machine.

[psubmit](https://github.com/a-v-medvedev/psubmit) is a software package for automated, generalized submission of batch jobs on a number of HPC systems. It is a dependency of both [ifsnemo-build](earth.bsc.es/gitlab/digital-twins/nvidia/ifsnemo-build) and ifsnemo-compare.

For example, to add `yq` to `~/bin` and `~/bin` to `PATH` on `glogin4`:

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
  remote_transfer_machine: string # Optional: a separate machine for file transfer, if your target's login node isn't the right place for it
  machine_file: string           # Machine configuration file to use (e.g., dnb-mn5-gpp.yaml)

# Execution mode (optional). 'direct' if this machine has filesystem access and can
# submit jobs on the target HPC system directly; 'proxy' if you need SSH to reach it.
# If omitted, pipeline.py prompts interactively (or pass --exec-mode on the command line).
exec_mode: string              # "direct" or "proxy"

# Path configuration
paths:
  local_build_dir: string        # Path to ifsnemo-build directory on local machine. (Step 2.2)
  remote_project_dir: string     # Path to remote project directory. Will be created if it doesn't exist.

# Override settings
overrides:
  DNB_SANDBOX_SUBDIR: string     # Sandbox subdirectory name (e.g., "ifsFOOBAR.SP.CPU.GPP") 
  DNB_IFSNEMO_URL: string        # IFSNEMO URL (e.g., "https://git.ecmwf.int/scm/~ecmeXXXX") (see pipeline-yaml-examples/pipeline.CY49R3_20260921.mn5-gpp.yaml)
  IFS_RAPS_IFS_SOURCE_GIT: string # IFS source Git URL (can use $DNB_IFSNEMO_URL variable); IFS_BUNDLE_IFS_SOURCE_GIT is also accepted as an older alias, but this (IFS_RAPS_*) wins if both are set, with a note printed (see pipeline-yaml-examples/pipeline.CY49R3_20260921.mn5-gpp.yaml)
  IFS_RAPS_IFS_SOURCE_VERSION: string # Branch or version to use; IFS_BUNDLE_IFS_SOURCE_VERSION is also accepted as an older alias, but this (IFS_RAPS_*) wins if both are set, with a note printed (see pipeline-yaml-examples/pipeline.CY49R3_20260921.mn5-gpp.yaml)
  DNB_IFSNEMO_BUNDLE_BRANCH: string    # Optional bundle branch specification (see pipeline-yaml-examples/pipeline.CY49R3_20260921.mn5-gpp.yaml)
  DNB_IFSNEMO_INPROOT: string          # Optional override for the bundle's input-root path
  DNB_IFSNEMO_BUNDLE_GIT: string       # Optional bundle git repository URL (see pipeline-yaml-examples/pipeline.CY49R3_20260921.mn5-gpp.yaml)
  IFS_BUNDLE_RAPS_GIT: string          # Optional RAPS git repository URL (see pipeline-yaml-examples/pipeline.CY49R3_20260921.mn5-gpp.yaml)
  IFS_BUNDLE_RAPS_VERSION: string      # Optional RAPS version (see pipeline-yaml-examples/pipeline.CY49R3_20260921.mn5-gpp.yaml)
  DNB_IFSNEMO_WITH_GPU: string         # Enable GPU support (e.g., "TRUE" or "FALSE")
  DNB_IFSNEMO_WITH_GPU_EXTRA: string   # Enable extra GPU support (e.g., "TRUE" or "FALSE")
  DNB_IFSNEMO_WITH_STATIC_LINKING: string # Enable static linking (e.g., "TRUE" or "FALSE")
  DNB_IFSNEMO_USE_ARCH_AND_RAPS: string # Defaults to "TRUE"; set "FALSE" to override
  env:                                 # Optional: arbitrary extra environment variables, passed through as-is
    SOME_VAR: string                   #   (e.g. SOME_VAR: "value" -> export SOME_VAR="value")

# SLURM submission settings
psubmit:
  queue_name: string             # Queue name (can be empty string) (see pipeline-yaml-examples/pipeline.CY49R3_20260921.mn5-gpp.yaml for guidance)
  account: string               # Account name (e.g., ehpcXX) (see pipeline-yaml-examples/pipeline.CY49R3_20260921.mn5-gpp.yaml for guidance)
  node_type: string            # Node type (e.g., gp_ehpc) (see pipeline-yaml-examples/pipeline.CY49R3_20260921.mn5-gpp.yaml for guidance)

# IFS-NEMO comparison settings
ifsnemo_compare:
  gold_standard_tag: string     # Reference tag (e.g., "ifs.DE_CY48R1.0_climateDT_20250521.SP.CPU.GPP") (see https://gitlab.earth.bsc.es/ces/hpc-for-es-team/ifsnemo-compare-references/-/tree/main/references for all available tags)

  # Test suite selection (optional - defaults defined in test_definitions.yaml)
  build_suites: []            # Build-time test suites to run (e.g., ["bundle_validator"])
  test_suites: []             # Runtime test suites to run (e.g., ["compare_norms"])

  # Test configuration arrays (resolution/steps/threads/ppn/nodes must all have matching
  # lengths; gpus is only required, and must also match, when overrides.DNB_IFSNEMO_WITH_GPU is "TRUE")
  resolution: []               # Array of resolutions (e.g., ["tco79-eORCA1", "tco399-eORCA025"])
  steps: []                   # Array of steps (e.g., ["d1", "d1"])
  threads: []                 # Array of thread counts (e.g., [4, 4])
  ppn: []                    # Array of processes per node (e.g., [28, 28])
  nodes: []                  # Array of node counts (e.g., [1, 16])
  gpus: []                   # Array of GPU counts, only used when DNB_IFSNEMO_WITH_GPU is "TRUE" (e.g., [1, 1])

# Reference configuration (optional block; if included, url and path_in_repo are required)
references:
  url: string                 # Required if this block is present. Git URL for references repository (e.g https://gitlab.earth.bsc.es/ces/hpc-for-es-team/ifsnemo-compare-references.git) (see pipeline-yaml-examples/pipeline.CY49R3_20260921.mn5-gpp.yaml for guidance)
  branch: string             # Branch to use (defaults to "main" if not specified) (see pipeline-yaml-examples/pipeline.CY49R3_20260921.mn5-gpp.yaml for guidance)
  path_in_repo: string       # Required if this block is present. Path within the repository where references are located (probably "references") (see https://gitlab.earth.bsc.es/ces/hpc-for-es-team/ifsnemo-compare-references/-/tree/main/references)
```

For guidance on specific values, refer to [a personal pipeline.yaml to test CY49R3](./pipeline-yaml-examples/pipeline.CY49R3_20260921.mn5-gpp.yaml).[^48r1]

[^48r1]: Earlier CY48R1 examples are archived under [pipeline-yaml-examples/48r1/](./pipeline-yaml-examples/48r1/).

> Note: The available test suites are defined in `test_definitions.yaml`. If `build_suites` or `test_suites` are not specified in your `pipeline.yaml`, the defaults set in `test_definitions.yaml` will be used. This ensures backwards compatibility with existing pipeline.yaml files.

---

## 5. Run the pipeline on your local machine

Run the pipeline:
```bash
python3 pipeline.py
```

This will execute the pipeline using the configuration specified in `pipeline.yaml`, building, installing, running, and post-processing the output, then delivering the test results.

## 6. Advanced Topics

This section groups a couple of advanced or alternative ways to operate the project: (1) pipeline command-line options for pipeline.py, and (2) how to invoke compare_norms.py directly on the remote/login node when you want more direct control.

### 6.1 Pipeline Options

The pipeline script (`pipeline.py`) accepts several optional arguments to change its behavior:

- `-y, --yaml <path>`: Specify a custom path to the pipeline YAML file (default: `pipeline.yaml`)
- `-s, --skip-build`: Skip the build and install steps, only run tests and compare
- `--no-run`: Do the build/install but skip the run and compare stages
- `--partial-build`: Use partial build (`dnb.sh :r`) instead of full build (`dnb.sh :b`); for quick rebuilds involving small code changes, and does not invoke ifs-bundle
- `--no-install`: Skip the install step (`dnb.sh :i`) after building
- `--force-rebuild`: Skip the confirmation prompt that otherwise appears before a full rebuild against an existing sandbox
- `--exec-mode {direct,proxy}`: Set execution mode without being prompted interactively (see `exec_mode` in `pipeline.yaml`, Section 4)

Example usage:
```bash
python3 pipeline.py --yaml custom-pipeline.yaml  # Use a custom config file
python3 pipeline.py --skip-build                # Skip build steps, only run tests
python3 pipeline.py --no-run                    # Only do build/install, no tests
python3 pipeline.py --partial-build             # Partial rebuild only
python3 pipeline.py --no-install                # Build but skip the install step
python3 pipeline.py --force-rebuild             # Suppress the full-rebuild confirmation prompt
python3 pipeline.py --exec-mode direct          # Skip the direct/proxy prompt
```

Notes:
- `--skip-build` is useful when you have already built and installed artifacts on the remote and want to re-run tests only (the script will clean remote test directories for the configured sandbox).
- `--no-run` is useful for producing the build/install artifacts and uploading them without executing test runs; the output JSON (test_results.json) will reflect that no runs were executed.
- `--partial-build` is intended for when only source code changes have occurred and a full bundle rebuild is not needed. If in doubt, run a full build instead.
- Without `--force-rebuild`, `--skip-build`, or `--partial-build`, a full rebuild against an existing sandbox prompts for confirmation (it can take ~1 hour); `--force-rebuild` suppresses that prompt.

### 6.2 Using `compare_norms.py` tool directly at the command line

The `compare_norms.py` helper provides three subcommands to manage reference creation, test runs, and comparisons. This tool is useful on the remote/login node where `psubmit.sh` (or `psubmit`) and `yq` are available.

After running the install portion of the pipeline, `compare_norms.py` and its companion scripts (`cmp.sh`, `compare.sh`) are located at:
```
<paths:remote_project_dir>/ifsnemo-build/ifsnemo-compare/tests/compare_norms/
```

For standalone use, you can either:
- Call with full path: `python3 /path/to/ifsnemo-compare/tests/compare_norms/compare_norms.py`
- Or symlink into the sandbox for convenience:
  ```bash
  cd <paths:remote_project_dir>/ifsnemo-build/src/sandbox
  ln -s ../../ifsnemo-compare/tests/compare_norms/compare_norms.py .
  ln -s ../../ifsnemo-compare/tests/compare_norms/compare.sh .
  ln -s ../../ifsnemo-compare/tests/compare_norms/cmp.sh .
  ```

General usage:
```bash
python3 compare_norms.py <command> [options...]
```

Commands and important options:

#### 6.2.1 `create-refs`

**Purpose:** submit jobs to create and store reference results.

> **Note:** unless you are working on CI/CD and know what you are doing, you do not need this command.

**Key options:**

- `-g, --ref-subdirs` — which reference binary to compare against (single string; required). Following the pipeline, choose from any directory within `<paths:remote_project_dir>/ifsnemo-build/src/sandbox/references`.
- `-og, --output-refdir` — directory in which the created references are stored (required; single value). Following the pipeline: `references/`.
- `-r, --resolutions` — list of resolution names (default: `tco79-eORCA1`)
- `-nt, --nthreads` — number of threads (list)
- `-p, --ppn` — processes per node (list)
- `-n, --nnodes` — number of nodes (list)
- `-s, --nsteps` — number of steps (list; can be strings like `"d1"`)

**Example:**
```bash
python3 compare_norms.py create-refs \
  -g /path/to/ref/bin/dir \
  -og /path/to/output_refs \
  -r tco79-eORCA1 \
  -nt 4 \
  -p 28 \
  -n 1 \
  -s d1
```

**Pipeline-following example** (creating references for `ifsMASTER.SP.CPU.GPP`):

> Unless you know what you are doing, you don't need to worry about this.

```bash
# TCO79, 1 day
python3 compare_norms.py create-refs -g ifsMASTER.SP.CPU.GPP/ -og references -r tco79-eORCA1 -nt 4 -p 28 -n 1 -s d1

# TCO399, 1 day
python3 compare_norms.py create-refs -g ifsMASTER.SP.CPU.GPP/ -og references -r tco399-eORCA025 -nt 4 -p 28 -n 16 -s d1

# TCO1279, 1 day
python3 compare_norms.py create-refs -g ifsMASTER.SP.CPU.GPP/ -og references -r tco1279-eORCA12 -nt 8 -p 14 -n 125 -s d1

# TCO2559, 1 day
python3 compare_norms.py create-refs -g ifsMASTER.SP.CPU.GPP/ -og references -r tco2559-eORCA12 -nt 14 -p 8 -n 260 -s d1
```

**Behavior:** for each combination of the supplied arrays, this calls `psubmit.sh` (expecting it in `PATH`), captures "Job ID \<id\>" from the submission output, writes a run log file, and copies `results.<jobid>` into the organized output directory structure.

---

#### 6.2.2 `run-tests`

**Purpose:** submit jobs for test binaries (same parameterization as `create-refs`).

**Key options:**

- `-t, --test-subdirs` — one or more test binary directories (required). Following the pipeline, `<overrides:DNB_SANDBOX_SUBDIR>/` may be used to run tests with the pipeline-built binary.
- `-ot, --output-testdir` — directory to store test outputs (required; single value). Following the pipeline: `tests/`.
- `-r`, `-nt`, `-p`, `-n`, `-s` — same meaning as above.

**Example:**
```bash
python3 compare_norms.py run-tests \
  -t  /path/to/test/bin/dir \
  -ot /path/to/output_tests \
  -r tco79-eORCA1 \
  -nt 4 \
  -p 28 \
  -n 1 \
  -s d1
```

**Pipeline-following example** (using `pipeline-yaml-examples/pipeline.CY49R3_20260921.mn5-gpp.yaml`):
```bash
# TCO79, 1 day
python3 compare_norms.py run-tests -t ifsMASTER.SP.CPU.GPP/ -ot tests -r tco79-eORCA1 -nt 4 -p 28 -n 1 -s d1

# TCO399, 1 day
python3 compare_norms.py run-tests -t ifsMASTER.SP.CPU.GPP/ -ot tests -r tco399-eORCA025 -nt 4 -p 28 -n 16 -s d1

# TCO1279, 1 day
python3 compare_norms.py run-tests -t ifsMASTER.SP.CPU.GPP/ -ot tests -r tco1279-eORCA12 -nt 8 -p 14 -n 125 -s d1

# TCO2559, 1 day
python3 compare_norms.py run-tests -t ifsMASTER.SP.CPU.GPP/ -ot tests -r tco2599-eORCA12 -nt 14 -p 8 -n 260 -s d1
```

**Behavior:** similar to `create-refs`, but labels logs as test runs and stores `results.<jobid>` under the test output directory.

---

#### 6.2.3 `compare`

**Purpose:** compare stored reference results against test results using the repository's `compare.sh`.

**Key options:**

- `-g, --ref-subdir` — which reference binary to compare against (single string; required). Following the pipeline, choose from any directory within `<paths:remote_project_dir>/ifsnemo-build/src/sandbox/references`.
- `-t, --test-subdirs` — one or more test binary directories (required). Following the pipeline, `<overrides:DNB_SANDBOX_SUBDIR>/` may be used to run tests with the pipeline-built binary.
- `-og, --output-refdir` — directory in which references are stored (required; single value). Following the pipeline: `references/`.
- `-ot, --output-testdir` — directory in which test outputs are stored (required; single value). Following the pipeline: `tests/`.
- `-r, -nt, -p, -n, -s` — as above, to iterate parameter combinations.

**Example:**
```bash
python3 compare_norms.py compare \
  -g /path/to/ref/bin/dir \
  -t /path/to/test/bin/dir \
  -og /path/to/output_refs \
  -ot /path/to/output_tests \
  -r tco79-eORCA1 \
  -nt 4 \
  -p 28 \
  -n 1 \
  -s d1
```

**Pipeline-following example** (using `pipeline-yaml-examples/pipeline.CY49R3_20260921.mn5-gpp.yaml`):
```bash
# TCO79, 1 day
python3 compare_norms.py compare -t ifs.DE_CY49R3_climateDT_20260921.SP.CPU.GPP/ -ot tests -g ifs.DE_CY49R3_climateDT_20260526.SP.CPU.GPP/ -og references -r tco79-eORCA1 -nt 4 -p 28 -n 1 -s d1

# TCO399, 1 day
python3 compare_norms.py compare -t ifs.DE_CY49R3_climateDT_20260921.SP.CPU.GPP/ -ot tests -g ifs.DE_CY49R3_climateDT_20260526.SP.CPU.GPP/ -og references -r tco399-eORCA025 -nt 4 -p 28 -n 16 -s d1

# TCO1279, 1 day
python3 compare_norms.py compare -t ifs.DE_CY49R3_climateDT_20260921.SP.CPU.GPP/ -ot tests -g ifs.DE_CY49R3_climateDT_20260526.SP.CPU.GPP/ -og references -r tco1279-eORCA12 -nt 8 -p 14 -n 125 -s d1

# TCO2559, 1 day
python3 compare_norms.py compare -t ifs.DE_CY49R3_climateDT_20260921.SP.CPU.GPP/ -ot tests -g ifs.DE_CY49R3_climateDT_20260526.SP.CPU.GPP/ -og references -r tco2559-eORCA12 -nt 14 -p 8 -n 260 -s d1
```

**Behavior:** for each parameter combination, the tool looks for the reference results directory and the test results directory, then executes `./compare.sh <ref> <test>`. Output and exit codes are printed so you can capture and inspect them.

---

#### 6.2.4 `stat-test`

Runs statistical tests on the norm arrays extracted from stored ref and test `result.<jobid>.yaml`s. The following tests are applied per-variable:

- **Effect-size test**: the difference of the means, in terms of the standard deviation, $`d = \dfrac{ \overline{ref} − \overline{test} } { \sigma_d } `$, where $` { \sigma_d } `$ is the pooled standard deviation of both groups:
  - $` \sigma_d  = \dfrac{ (n - 1)(s_1^2 + s_2^2) } { 2n - 2 } `$, where
  - $` s_i^2 = \dfrac{1}{n-1}\sum_{j=1}^n ( x_{i,j} - \overline{x_i} ) ^2, \quad i=1,2 `$ are the variances corresponding to the reference and test norm arrays $` x_1, x_2\in \mathbb{R}^n `$.
  - Warns when $`\left| d \right| >`$ `EFFECT_SIZE_THRESHOLD` (default `1.0`).
- Two-sample **Kolmogorov-Smirnov test** (`scipy.stats.ks_2samp`), using the default optional arguments.
  - Warns when $` p < `$ `KS_PVAL_THRESHOLD` (default `0.05`).
- Two-sample **Welch t-test** (`scipy.stats.ttest_ind` with `equal_var=False` and `alternative='two-sided'`).
  - Warns when $` p < `$ `KS_PVAL_THRESHOLD` (default `0.05`).
  - `equal_var=False` is what makes it Welch's t-test specifically (allows unequal variances between the two groups).
  - Uses `alternative='two-sided'` for a two-tailed test.

Takes identical arguments to `compare` — same `-g`, `-t`, `-og`, `-ot`, `-r`, `-nt`, `-p`, `-n`, `-s`, `--gpus`.

**Example:**
```bash
python3 compare_norms.py stat-test \
  -g /path/to/ref/bin/dir \
  -t /path/to/test/bin/dir \
  -og /path/to/output_refs \
  -ot /path/to/output_tests \
  -r tco79-eORCA1 \
  -nt 4 \
  -p 28 \
  -n 1 \
  -s d1
```

**Pipeline-following example** (using `pipeline-yaml-examples/pipeline.CY49R3_20260921.mn5-gpp.yaml`):
```bash
# TCO79, 1 day
python3 compare_norms.py stat-test -t ifs.DE_CY49R3_climateDT_20260921.SP.CPU.GPP/ -ot tests -g ifs.DE_CY49R3_climateDT_20260526.SP.CPU.GPP/ -og references -r tco79-eORCA1 -nt 4 -p 28 -n 1 -s d1

# TCO399, 1 day
python3 compare_norms.py stat-test -t ifs.DE_CY49R3_climateDT_20260921.SP.CPU.GPP/ -ot tests -g ifs.DE_CY49R3_climateDT_20260526.SP.CPU.GPP/ -og references -r tco399-eORCA025 -nt 4 -p 28 -n 16 -s d1

# TCO1279, 1 day
python3 compare_norms.py stat-test -t ifs.DE_CY49R3_climateDT_20260921.SP.CPU.GPP/ -ot tests -g ifs.DE_CY49R3_climateDT_20260526.SP.CPU.GPP/ -og references -r tco1279-eORCA12 -nt 8 -p 14 -n 125 -s d1

# TCO2559, 1 day
python3 compare_norms.py stat-test -t ifs.DE_CY49R3_climateDT_20260921.SP.CPU.GPP/ -ot tests -g ifs.DE_CY49R3_climateDT_20260526.SP.CPU.GPP/ -og references -r tco2559-eORCA12 -nt 14 -p 8 -n 260 -s d1
```

Variables with insufficient data (`n1 + n2 ≤ 2`), mismatched array lengths, or a zero pooled standard deviation are reported as `[SKIP]` or `[degenerate]` with an explanation.

---

**Notes and tips:**
- `compare_norms.py` expects `psubmit.sh` (or psubmit wrapper) in PATH to submit jobs; `psubmit` prints a "Job ID <id>" line which `compare_norms.py` parses.
- The tool expects job results to be available under directories named results.<jobid> after the job completes; those directories are moved/copied into your organized ref/test output tree.

## 7. Interpreting the Results

After the pipeline completes, results are placed in a timestamped subdirectory within `results/` in your `ifsnemo-compare` directory:

```
results/<YYYYMMDD>_<HHMMSS>__<pipeline-filename>/
```

For example: `results/20260122_143052__pipeline.develop.mn5-gpp/`

### 7.1. Output Files

Within this results directory, you will find:

-   **`test_results.json`**: Summary of all test executions, indicating pass/fail status for each step.
-   **`{suite}_{command}_{test_id}.log`**: Detailed log files for each test command. For example:
    - `bundle_validator_bundle_validate_build.log` - build suite validation
    - `bundle_validator_bundle_compare_build.log` - build suite comparison
    - `compare_norms_run_tests_*.log` - runtime test execution
    - `compare_norms_compare_*.log` - runtime test comparison

### 7.2. Analyzing `test_results.json`

The `test_results.json` file provides a high-level overview of the test outcomes. Results are grouped by test configuration (or `"build"` for build-time tests). A `true` value for `*_passed` indicates success; `false` indicates failure requiring investigation.

Example `test_results.json`:
```json
{
    "build": {
        "bundle_validate_passed": true,
        "bundle_validate_output": "results/{results_dir}/bundle_validator_bundle_validate_build.log",
        "bundle_compare_passed": true,
        "bundle_compare_output": "results/{results_dir}/bundle_validator_bundle_compare_build.log"
    },
    "rtco79-eORCA1_sd1_t4_p28_n1": {
        "run_tests_passed": true,
        "run_tests_output": "results/{results_dir}/compare_norms_run_tests_rtco79-eORCA1_sd1_t4_p28_n1.log",
        "compare_passed": true,
        "compare_output": "results/{results_dir}/compare_norms_compare_rtco79-eORCA1_sd1_t4_p28_n1.log"
    }
}
```

### 7.3. Inspecting Log Files

For any failed steps, the corresponding `.log` files are essential for debugging.

-   **`{suite}_run_tests_*.log`**: Check these files for errors related to test execution. Search for error messages or stack traces that could indicate what went wrong.
-   **`{suite}_compare_*.log`**: These files contain the comparison output. For `compare_norms`, this shows differences between your test run and the gold standard. For `bundle_validator`, this shows configuration differences.

By examining these files, you can diagnose the root cause of any test failures and determine the next steps for your development work.

---

## 8. How to Add a Test to the Test Suite

This section explains how to add a new test to the ifsnemo-compare framework.

### 8.1. Directory Structure

For a new test called `my_test`, create a directory under `tests/`:

```
tests/my_test/
├── my_test.py          # Main test script
├── helper_script.sh    # Optional helper scripts
└── ...
```

> **Important:** Comparison standards (reference data) do NOT belong in these folders unless they are universal across all configurations. References should be stored in the repository pointed to by the `references` section in your `pipeline.yaml`. This can be any git repository.

### 8.2. Adding to test_definitions.yaml

Add your test under the appropriate section in `test_definitions.yaml`:

- **`build_suites`**: For tests that run once per build, independent of runtime parameters
- **`test_suites`**: For tests that need to run for each combination of resolution/threads/ppn/nodes/steps

Example entry:

```yaml
test_suites:
  my_test:
    working_dir: "{remote_path}/ifsnemo-build/src/sandbox"
    script: "python3 {remote_path}/ifsnemo-build/ifsnemo-compare/tests/my_test/my_test.py"
    commands:
      run-tests:
        args: "-t {test_subdir}/ -o {remote_path}/ifsnemo-build/ifsnemo/tests"
        output_prefix: "run_tests"
      compare:
        args: "-g {gold_standard_tag}/ -t {test_subdir}/"
        output_prefix: "compare"
    sequence:
      - run-tests
      - compare
```

### 8.3. Configuration Options Explained

| Option | Description |
|--------|-------------|
| `working_dir` | Directory from which the script is executed. Template variables like `{remote_path}` are expanded. |
| `script` | The command to invoke, e.g., `python3 /path/to/script.py`. Template variables are expanded. |
| `commands` | Named commands with their arguments. Each command becomes a subcommand to your script. |
| `commands.{name}.args` | Arguments passed to the script. Template variables are expanded. |
| `commands.{name}.output_prefix` | Prefix for the log filename (e.g., `run_tests` → `my_test_run_tests_*.log`). |
| `sequence` | Order in which commands are executed. |

### 8.4. Example: Multiple Commands

If your test script supports multiple operations like `my_test.py abc -a -b -c` and `my_test.py xyz -x -y -z`:

```yaml
commands:
  abc:
    args: "-a -b -c"
    output_prefix: "abc"
  xyz:
    args: "-x -y -z"
    output_prefix: "xyz"
sequence:
  - abc
  - xyz
```

### 8.5. Default Suites

If your test should run by default (when `build_suites` or `test_suites` is not specified in the pipeline.yaml), add it to the respective default list:

```yaml
default_build_suites:
  - bundle_validator
  - my_new_build_test    # Add here for build-time tests

default_test_suites:
  - compare_norms
  - my_new_runtime_test  # Add here for runtime tests
```

> **Caution:** Legacy pipeline.yaml files (before February 2026) do not specify test suites, so they will run all default suites. Be careful when adding new defaults.

### 8.6. Required Parameters

The `build_required_params` and `test_required_params` lists specify which context variables must be available:

```yaml
build_required_params:
  - remote_path
  - bundle_yaml
  - build_dir
  - gold_standard_tag

test_required_params:
  - remote_path
  - test_subdir
  - gold_standard_tag
  - resolution
  - threads
  - ppn
  - nodes
  - steps
```

If your test needs additional parameters, add them to `build_required_params` or `test_required_params` in `test_definitions.yaml` and update `pipeline.py` to provide them in the context.
