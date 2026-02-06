# Getting Started Guide

## 0. Introduction

This document describes how to use the `ifsnemo-compare` tool to run regression tests for the IFS-NEMO model. The tool automates the process of building the model, running a set of predefined tests, and comparing the results against a set of gold standards.

## 1. Prerequisites

Before you begin, ensure you have:

### 1.1. ifsnemo-build access
- For full setup details, visit:
  - [ifsnemo-build repository](https://earth.bsc.es/gitlab/digital-twins/nvidia/ifsnemo-build)
  - [ifsnemo-build instructions](https://hackmd.io/@mxKVWCKbQd6NvRm0h72YpQ/SkHOb6FZgg)

### 1.2. Required Python packages (installed on local machine)
[fabric](https://github.com/fabric/fabric) is a remote execution package used by ifsnemo-compare's ´pipeline.py´ for automating commands on remote nodes.
[pyyaml](https://github.com/yaml/pyyaml) is a YAML parser used to read the `pipeline.yaml` input files that drive ifsnemo-compare's `pipeline.py`.
Both are dependencies of ifsnemo-compare and must be installed.
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
- [MareNostrum5](https://www.bsc.es/marenostrum/marenostrum-5) (if you do not have access, please contact your supervisor)
- [ECMWF Bitbucket](https://git.ecmwf.int/) (see section 2.3 for detailed access requirements)

---

## 2. Local Machine Setup

First, create a dedicated project directory to organize all the components:
```bash
mkdir ifsnemo-compare-project
cd ifsnemo-compare-project
# All subsequent clone operations will be performed in this directory
```

### 2.1. Install `yq`

[yq](https://github.com/mikefarah/yq) is a portable command-line YAML, JSON, XML, CSV, TOML and properties processor. It is a dependency of [ifsnemo-build](earth.bsc.es/gitlab/digital-twins/nvidia/ifsnemo-build).

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
[psubmit](https://github.com/a-v-medvedev/psubmit) is a software package for automated, generalized submission of batch jobs on a number of HPC systems. It is a dependency of both [ifsnemo-build](earth.bsc.es/gitlab/digital-twins/nvidia/ifsnemo-build) and ifsnemo-compare, and must be installed and in `PATH` on the target system where jobs will be submitted. This step performs this automatically.
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
  local_build_dir: string        # Path to ifsnemo-build directory on local machine. (Step 2.4)
  remote_project_dir: string     # Path to remote project directory. Will be created if it doesn't exist.

# Override settings
overrides:
  DNB_SANDBOX_SUBDIR: string     # Sandbox subdirectory name (e.g., "ifsFOOBAR.SP.CPU.GPP") 
  DNB_IFSNEMO_URL: string        # IFSNEMO URL (e.g., "https://git.ecmwf.int/scm/~ecmeXXXX") (see pipeline-20250521-nabel.yaml and quickstart.md for guidance)
  IFS_BUNDLE_IFS_SOURCE_GIT: string # IFS source Git URL (can use $DNB_IFSNEMO_URL variable) (see pipeline-20250521-nabel.yaml and quickstart.md for guidance)
  IFS_BUNDLE_IFS_SOURCE_VERSION: string # Branch or version to use (see pipeline-20250521-nabel.yaml and quickstart.md for guidance)
  DNB_IFSNEMO_BUNDLE_BRANCH: string    # Optional bundle branch specification (see pipeline-20250521-nabel.yaml and quickstart.md for guidance)
  DNB_IFSNEMO_BUNDLE_GIT: string       # Optional bundle git repository URL (see pipeline-20250521-nabel.yaml and quickstart.md for guidance)
  IFS_BUNDLE_RAPS_GIT: string          # Optional RAPS git repository URL (see pipeline-20250521-nabel.yaml and quickstart.md for guidance)
  IFS_BUNDLE_RAPS_VERSION: string      # Optional RAPS version (see pipeline-20250521-nabel.yaml and quickstart.md for guidance)
  DNB_IFSNEMO_WITH_GPU: string         # Enable GPU support (e.g., "TRUE" or "FALSE")
  DNB_IFSNEMO_WITH_GPU_EXTRA: string   # Enable extra GPU support (e.g., "TRUE" or "FALSE")
  DNB_IFSNEMO_WITH_STATIC_LINKING: string # Enable static linking (e.g., "TRUE" or "FALSE")

# SLURM submission settings
psubmit:
  queue_name: string             # Queue name (can be empty string) (see pipeline-20250521-nabel.yaml for guidance)
  account: string               # Account name (e.g., ehpc01) (see pipeline-20250521-nabel.yaml for guidance)
  node_type: string            # Node type (e.g., gp_ehpc) (see pipeline-20250521-nabel.yaml for guidance)

# IFS-NEMO comparison settings
ifsnemo_compare:
  gold_standard_tag: string     # Reference tag (e.g., "ifs.DE_CY48R1.0_climateDT_20250521.SP.CPU.GPP") (see https://github.com/kellekai/bsc-ndse/tree/main/references for all available tags)

  # Test suite selection (optional - defaults defined in test_definitions.yaml)
  build_suites: []            # Build-time test suites to run (e.g., ["bundle_validator"])
  test_suites: []             # Runtime test suites to run (e.g., ["compare_norms"])

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

For guidance on specific values, refer to [a personal pipeline.yaml to test the develop branch](https://github.com/NickAbel/ifsnemo-compare/blob/7f0e0a34a084b661914d796a0c9df109a288ea57/pipeline-yaml-examples/pipeline.develop.mn5-gpp.yaml). For instructions on creating your own fork in ECMWF Bitbucket for testing, see [quickstart.md](./quickstart.md).

> Note: The available test suites are defined in `test_definitions.yaml`. If `build_suites` or `test_suites` are not specified in your pipeline.yaml, the defaults from `test_definitions.yaml` will be used. This ensures backwards compatibility with existing pipeline.yaml files.

---

## 5. Run the pipeline on your local machine

Ensure your Python virtual environment is activated:
```bash
source ifsnemo-compare/bin/activate
```

Then run the pipeline:
```bash
python3 pipeline.py
```

This will execute the pipeline using the configuration specified in `pipeline.yaml`.

## 6. Advanced Topics

This section groups a couple of advanced or alternative ways to operate the project: (1) pipeline command-line options for pipeline.py, and (2) how to invoke compare_norms.py directly on the remote/login node when you want more direct control.

### 6.1 Pipeline Options

The pipeline script (`pipeline.py`) accepts several optional arguments to change its behavior:

- `-y, --yaml <path>`: Specify a custom path to the pipeline YAML file (default: `pipeline.yaml`)
- `-s, --skip-build`: Skip the build and install steps, only run tests and compare
- `--no-run`: Do the build/install but skip the run and compare stages
- `--partial-build`: Use incremental rebuild instead of full build (only recompiles changed sources)

Example usage:
```bash
python3 pipeline.py --yaml custom-pipeline.yaml  # Use a custom config file
python3 pipeline.py --skip-build                # Skip build steps, only run tests
python3 pipeline.py --no-run                    # Only do build/install, no tests
python3 pipeline.py --partial-build             # Incremental rebuild only
```

Notes:
- `--skip-build` is useful when you have already built and installed artifacts on the remote and want to re-run tests only (the script will clean remote test directories for the configured sandbox).
- `--no-run` is useful for producing the build/install artifacts and uploading them without executing test runs; the output JSON (test_results.json) will reflect that no runs were executed.
- `--partial-build` is intended for when only source code changes have occurred and a full bundle rebuild is not needed. If in doubt, run a full build instead.

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

1) `create-refs`
- Purpose: submit jobs to create and store reference results. **NOTE** Unless you are working on CI/CD and know what you are doing, you do not need this option.
- Key options:
  - `-g, --ref-subdirs` which reference binary to compare against (single string; required) (following the pipeline, may choose from any directory within the `<paths:remote_project_dir>/ifsnemo-build/src/sandbox/references` directory
  - `-og, --output-refdir` directory in which the references created are to be stored (required; single value) (following the pipeline, `references/`)
  - `-r, --resolutions` list of resolution names (default: tco79-eORCA1)
  - `-nt, --nthreads` number of threads (list)
  - `-p, --ppn` processes per node (list)
  - `-n, --nnodes` number of nodes (list)
  - `-s, --nsteps` number of steps (list; can be strings like "d1")
- Example:
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
- Pipeline-Following Example (To create references for `ifsMASTER.SP.CPU.GPP`) **NOTE** Unless you know what you are doing, you don't need to worry about this.
```bash
#TCO79 1day
python3 compare_norms.py create-refs -g ifsMASTER.SP.CPU.GPP/ -og references -r tco79-eORCA1 -nt 4 -p 28 -n 1 -s d1
#TCO399 1day  
python3 compare_norms.py create-refs -g ifsMASTER.SP.CPU.GPP/ -og references -r tco399-eORCA025 -nt 4 -p 28 -n 16 -s d1
#TCO1279 1day
python3 compare_norms.py create-refs -g ifsMASTER.SP.CPU.GPP/ -og references -r tco1279-eORCA12 -nt 8 -p 14 -n 125 -s d1
#TCO2559 1day 
python3 compare_norms.py create-refs -g ifsMASTER.SP.CPU.GPP/ -og references -r tco2559-eORCA12 -nt 14 -p 8 -n 260 -s d1   
```
- Behavior: for each combination of the supplied arrays, this will call `psubmit.sh` (expecting it in PATH), capture "Job ID <id>" from the submission output, write a run log file, and copy `results.<jobid>` into the organized output directory structure.

2) `run-tests`
- Purpose: submit jobs for test binaries (same parameterization as create-refs)
- Key options:
  - `-t, --test-subdirs` one or more test binary directories (required) (following the pipeline, `<overrides:DNB_SANDBOX_SUBDIR>/` may be used to run tests with the pipeline-built binary)
  - `-ot, --output-testdir` directory to store test outputs (required; single value) (following the pipeline, `tests/`)
  - parameters: `-r`, `-nt`, `-p`, `-n`, `-s` (same meaning as above)
- Example:
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
- Pipeline-Following Example (If Using `pipeline-20250521-nabel.yaml`):
```bash
#TCO79 1day
python3 compare_norms.py run-tests -t ifsMASTER.SP.CPU.GPP/ -ot tests -r tco79-eORCA1 -nt 4 -p 28 -n 1 -s d1
#TCO399 1day  
python3 compare_norms.py run-tests -t ifsMASTER.SP.CPU.GPP/ -ot tests -r tco399-eORCA025 -nt 4 -p 28 -n 16 -s d1
#TCO1279 1day
python3 compare_norms.py run-tests -t ifsMASTER.SP.CPU.GPP/ -ot tests -r tco1279-eORCA12 -nt 8 -p 14 -n 125 -s d1
#TCO2559 1day 
python3 compare_norms.py run-tests -t ifsMASTER.SP.CPU.GPP/ -ot tests -r tco2599-eORCA12 -nt 14 -p 8 -n 260 -s d1      
```
- Behavior: similar to create-refs, but labels logs as test runs and stores `results.<jobid>` under the test output directory.

3) `compare`
- Purpose: compare stored reference results against test results using the repository's compare.sh
- Key options:
  - `-g, --ref-subdir` which reference binary to compare against (single string; required) (following the pipeline, may choose from any directory within the `<paths:remote_project_dir>/ifsnemo-build/src/sandbox/references` directory
  - `-t, --test-subdirs` one or more test binary directories (required) (following the pipeline, `<overrides:DNB_SANDBOX_SUBDIR>/` may be used to run tests with the pipeline-built binary)
  - `-og, --output-refdir` directory in which references are stored (required; single value) (following the pipeline, `references/`)
  - `-ot, --output-testdir` directory in which test outputs are stored (required; single value) (following the pipeline, `tests/`)
  - `-r, -nt, -p, -n, -s` as above to iterate parameter combinations
- Example:
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
- Pipeline-Following Example (If Using `pipeline-20250521-nabel.yaml`):
```bash
#TCO79 1day
python3 compare_norms.py compare -t ifs.DE_CY48R1.0_climateDT_20250826.SP.CPU.GPP/ -ot tests -g ifs.DE_CY48R1.0_climateDT_20250521.SP.CPU.GPP/ -og references -r tco79-eORCA1 -nt 4 -p 28 -n 1 -s d1
#TCO399 1day  
python3 compare_norms.py compare -t ifs.DE_CY48R1.0_climateDT_20250826.SP.CPU.GPP/ -ot tests -g ifs.DE_CY48R1.0_climateDT_20250521.SP.CPU.GPP/ -og references -r tco399-eORCA025 -nt 4 -p 28 -n 16 -s d1
#TCO1279 1day
python3 compare_norms.py compare -t ifs.DE_CY48R1.0_climateDT_20250826.SP.CPU.GPP/ -ot tests -g ifs.DE_CY48R1.0_climateDT_20250521.SP.CPU.GPP/ -og references -r tco1279-eORCA12 -nt 8 -p 14 -n 125 -s d1
#TCO2559 1day 
python3 compare_norms.py compare -t ifs.DE_CY48R1.0_climateDT_20250826.SP.CPU.GPP/ -ot tests -g ifs.DE_CY48R1.0_climateDT_20250521.SP.CPU.GPP/ -og references -r tco2559-eORCA12 -nt 14 -p 8 -n 260 -s d1   
```
- Behavior: for each parameter combination, the tool looks for the reference results directory and the test results directory and then executes `./compare.sh <ref> <test>`. Output and exit codes are printed so you can capture and inspect them.

Notes and tips:
- `compare_norms.py` expects `psubmit.sh` (or psubmit wrapper) in PATH to submit jobs; `psubmit` prints a "Job ID <id>" line which `compare_norms.py` parses.
- The tool expects job results to be available under directories named results.<jobid> after the job completes; those directories are moved/copied into your organized ref/test output tree.
- Ensure `compare.sh` (or equivalent comparison scripts) are present and executable where `compare_norms.py` runs.
- Use the tools interactively on the remote/login node if you want step-by-step control, or use `pipeline.py` to automate the full build/upload/run/compare flow from your local machine.

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
