#!/usr/bin/env python3
"""
Guided, idempotent setup for ifsnemo-compare.

Covers quickstart-testing.md Sections 1-3 (repository access, required
Python packages, yq, ifsnemo-build, and target machine setup), checking
whether each step is already done before doing anything. Creating
pipeline.yaml (Section 4) is out of scope -- see that section manually.

Deliberately stdlib-only: part of this script's job is installing
pyyaml/fabric, so it can't depend on either of them itself.
"""
import getpass
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

BOLD = '\033[1m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
RESET = '\033[0m'

NETRC_PATH = Path.home() / ".netrc"


def ok(msg):
    print(f"{GREEN}✓{RESET} {msg}")


def warn(msg):
    print(f"{YELLOW}![WARN]{RESET} {msg}")


def fail(msg):
    print(f"{RED}✗{RESET} {msg}")


def ask(prompt, default=None, secret=False):
    getter = getpass.getpass if secret else input
    suffix = f" [{default}]" if default is not None else ""
    while True:
        val = getter(f"{prompt}{suffix}: ").strip()
        if val:
            return val
        if default is not None:
            return default
        print("  (a value is required)")


def ask_yn(prompt, default=True):
    suffix = " [Y/n]" if default else " [y/N]"
    while True:
        val = input(f"{prompt}{suffix}: ").strip().lower()
        if not val:
            return default
        if val in ("y", "yes"):
            return True
        if val in ("n", "no"):
            return False


def netrc_has_machine(machine):
    if not NETRC_PATH.exists():
        return False
    tokens = NETRC_PATH.read_text().split()
    return any(tokens[i] == "machine" and tokens[i + 1] == machine
               for i in range(len(tokens) - 1))


def netrc_append(machine, login, password):
    existing = NETRC_PATH.read_text() if NETRC_PATH.exists() else ""
    if existing and not existing.endswith("\n"):
        existing += "\n"
    block = f"machine {machine}\n  login {login}\n  password {password}\n"
    NETRC_PATH.write_text(existing + block)
    NETRC_PATH.chmod(0o600)


def git_ls_remote_ok(url, timeout=20):
    """Check a URL is reachable (via netrc or SSH key), no password prompt, no hang."""
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    try:
        result = subprocess.run(["git", "ls-remote", url, "HEAD"], env=env,
                                 text=True, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False
    return result.returncode == 0 and result.stdout.strip() != ""


# ---------------------------------------------------------------------------
# Step 1.1: Access to the required repositories
# ---------------------------------------------------------------------------
GITLAB_MACHINE = "gitlab.earth.bsc.es"
GITLAB_CHECK_URL = f"https://{GITLAB_MACHINE}/digital-twins/nvidia/ifsnemo-build.git"
GITHUB_REPOS = ["ifs-raps", "ifs-source"]


def fix_gitlab_token():
    """1.1.a: add/verify the Earth GitLab fine-grained token."""
    if netrc_has_machine(GITLAB_MACHINE):
        warn(f"An existing ~/.netrc entry for {GITLAB_MACHINE} is present but didn't verify "
             "just now. This script won't modify or remove it -- its scope or reason isn't "
             "known here. Most .netrc readers use the FIRST matching entry for a host, so if "
             "that entry stays ahead of whatever you add below, the new one may be ignored.")

    print("  Generate a fine-grained, read-only token:")
    print(f"    https://{GITLAB_MACHINE}/-/user_settings/personal_access_tokens/granular/new")
    print("  Settings: any name, max expiry, 'All groups and projects', and under")
    print("  Group and project add Repository -> Code with only the Download permission.")
    if not ask_yn("Add a token now?", default=True):
        return False

    username = ask("  GitLab username")
    token = ask("  Paste the token (input hidden)", secret=True)
    netrc_append(GITLAB_MACHINE, username, token)
    return git_ls_remote_ok(GITLAB_CHECK_URL)


def fix_github_sso():
    """1.1.b: walk through ecmwf-ifs SSO authorization (no token/netrc -- SSH key based)."""
    print("  From your GitHub Keys page, under the SSH key you use on this machine,")
    print("  click 'Configure SSO' and authorize 'ecmwf-ifs':")
    print("    https://github.com/settings/keys")
    print("  If you don't have access to ifs-raps/ifs-source yet, that option won't")
    print("  appear -- contact your supervisor instead of continuing here.")
    ask_yn("Press Enter once you've done this (or to re-check)", default=True)
    return [repo for repo in GITHUB_REPOS
            if not git_ls_remote_ok(f"git@github.com:ecmwf-ifs/{repo}.git")]


def step_repo_access():
    print(f"\n{BOLD}1.1. Access to the required repositories{RESET}")

    gitlab_ok = git_ls_remote_ok(GITLAB_CHECK_URL)
    if gitlab_ok:
        ok("ifsnemo-build (GitLab)")
    else:
        fail("ifsnemo-build (GitLab)")

    missing_gh = [repo for repo in GITHUB_REPOS
                  if not git_ls_remote_ok(f"git@github.com:ecmwf-ifs/{repo}.git")]
    for repo in GITHUB_REPOS:
        if repo not in missing_gh:
            ok(f"ecmwf-ifs/{repo} (GitHub)")
        else:
            fail(f"ecmwf-ifs/{repo} (GitHub)")

    if not gitlab_ok:
        print(f"\n{BOLD}1.1.a. Earth GitLab access{RESET}")
        gitlab_ok = fix_gitlab_token()
        ok("ifsnemo-build (GitLab)") if gitlab_ok else fail("Still not reachable.")

    if missing_gh:
        print(f"\n{BOLD}1.1.b. ecmwf-ifs GitHub access{RESET}")
        missing_gh = fix_github_sso()
        if not missing_gh:
            ok("ecmwf-ifs/ifs-raps and ecmwf-ifs/ifs-source")
        else:
            fail(f"Still not reachable: {', '.join(missing_gh)}")

    all_ok = gitlab_ok and not missing_gh
    if not all_ok:
        print("\n  Still missing access above? Contact your supervisor -- ifsnemo-compare")
        print("  maintainers can't grant access to any of these repositories.")
    return all_ok


# ---------------------------------------------------------------------------
# Execution mode: mirrors pipeline.py's own resolve_exec_mode() exactly, so
# this installer and the tool it's setting up use the same question and the
# same vocabulary ('direct' / 'proxy'). Not imported from pipeline.py itself:
# pipeline.py does an unconditional `import yaml` at module level, which may
# not exist yet at this point in setup.
# ---------------------------------------------------------------------------
def ask_exec_mode():
    print("""
Cannot determine execution mode automatically.

This tool needs to know whether it should run commands directly on this machine or connect to a remote system via SSH. We cannot infer this from the environment because filesystem paths (e.g. /gpfs) can exist in many unrelated contexts — a different HPC cluster, a local SSHFS mount, etc. Using the wrong mode could cause unintended writes to an unknown system.

Two modes are available:

  [1] direct  — This machine has direct filesystem access to the target HPC system's storage AND can submit jobs there from its command line (e.g. you are on a login node of the target cluster).

  [2] proxy   — This machine cannot do the above from its command line, but can SSH to a machine that can (e.g. you are on a laptop connecting to the cluster over SSH).
""")
    while True:
        answer = input("Enter 1 (direct) or 2 (proxy): ").strip()
        if answer == '1':
            return 'direct'
        if answer == '2':
            return 'proxy'
        print("Please enter 1 or 2.")


# ---------------------------------------------------------------------------
# Step 1.2: Python packages
# ---------------------------------------------------------------------------
def step_python_packages(exec_mode):
    needed_mods = ["yaml"] if exec_mode == 'direct' else ["yaml", "fabric"]
    label = "pyyaml" if exec_mode == 'direct' else "pyyaml, fabric"
    print(f"\n{BOLD}1.2. Python packages ({label}){RESET}")
    if exec_mode == 'direct':
        print("  fabric (the SSH connection library) isn't needed in direct mode --")
        print("  there's no SSH hop to make from the login node to itself.")

    missing = []
    for mod in needed_mods:
        try:
            __import__(mod)
        except ImportError:
            missing.append("pyyaml" if mod == "yaml" else mod)

    if not missing:
        if len(needed_mods) == 1:
            ok(f"{label} is already importable")
        else:
            ok("pyyaml and fabric are both already importable")
        return

    warn(f"Missing: {', '.join(missing)}")
    if not ask_yn(f"Install with 'pip3 install {' '.join(missing)}' now?", default=True):
        warn(f"Skipped. Install them yourself before running pipeline.py:\n"
             f"    pip3 install {' '.join(missing)}")
        return

    print(f"  pip3 install {' '.join(missing)}")
    result = subprocess.run([sys.executable, "-m", "pip", "install", "--user", *missing],
                            text=True, capture_output=True)
    if result.returncode != 0:
        fail("pip install failed:")
        print(result.stdout)
        print(result.stderr)
    else:
        ok(f"Installed {', '.join(missing)}")


# ---------------------------------------------------------------------------
# Step 2.1: yq
# ---------------------------------------------------------------------------
def step_yq():
    print(f"\n{BOLD}2.1. yq{RESET}")
    existing = shutil.which("yq")
    if existing:
        ok(f"yq is already in PATH ({existing})")
        return True

    print("  yq not found.")
    bin_dir = Path(ask("  Directory to install it in (must be in PATH, or you'll "
                        "need to add it)", default=str(Path.home() / "bin"))).expanduser()
    bin_dir.mkdir(parents=True, exist_ok=True)
    dest = bin_dir / "yq"
    if dest.exists():
        warn(f"{dest} already exists but isn't the yq found via PATH above (or {bin_dir} "
             f"isn't on PATH at all) -- this script won't overwrite it without asking.")
        if not ask_yn(f"Overwrite {dest} with a fresh yq download?", default=False):
            warn(f"Skipped. Resolve {dest} manually, or make sure it (or another yq) is in PATH.")
            return False
    url = "https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64"
    try:
        urllib.request.urlretrieve(url, dest)
    except Exception as e:
        fail(f"Could not download yq: {e}")
        warn(f"Install it manually and ensure it's in PATH: {url}")
        return False

    dest.chmod(dest.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    ok(f"Installed yq to {dest}")

    if shutil.which("yq") is None:
        warn(f"{bin_dir} is not in your PATH yet. Add this to your shell rc file:\n"
             f"    export PATH=\"{bin_dir}:$PATH\"\n"
             "  then restart your shell (or `source` the rc file) before running pipeline.py.")
        return False
    return True


# ---------------------------------------------------------------------------
# Step 2.2: Clone and configure ifsnemo-build
# ---------------------------------------------------------------------------
IFSNEMO_BUILD_URL = "https://earth.bsc.es/gitlab/digital-twins/nvidia/ifsnemo-build.git"
IFSNEMO_BUILD_BRANCH = "cy49r3"


def run(cmd, **kwargs):
    return subprocess.run(cmd, text=True, capture_output=True, **kwargs)


def current_branch(repo_path):
    result = run(["git", "-C", str(repo_path), "symbolic-ref", "--short", "HEAD"])
    return result.stdout.strip() if result.returncode == 0 else None


def has_uncommitted_changes(repo_path):
    result = run(["git", "-C", str(repo_path), "status", "--porcelain"])
    return result.returncode == 0 and result.stdout.strip() != ""


def step_ifsnemo_build():
    print(f"\n{BOLD}2.2. Clone and configure ifsnemo-build{RESET}")
    default_path = Path(__file__).resolve().parent.parent / "ifsnemo-build"
    path = Path(ask("  ifsnemo-build install directory (will be cloned if not already present)",
                     default=str(default_path))).expanduser()
    target_branch = ask("  Branch to use", default=IFSNEMO_BUILD_BRANCH)

    if path.exists():
        if not (path / ".git").exists():
            fail(f"{path} exists and is not a git repository. Resolve this manually.")
            return None
        actual_branch = current_branch(path)
        if actual_branch == target_branch:
            ok(f"Already cloned at {path}, on {target_branch}")
        else:
            warn(f"Already cloned at {path}, but on branch '{actual_branch}', not "
                 f"'{target_branch}'.")
            proceed = True
            if has_uncommitted_changes(path):
                warn(f"{path} has uncommitted changes. git won't discard anything that "
                     f"conflicts with '{target_branch}' -- it'll refuse the checkout instead "
                     f"-- but changes that don't conflict will silently carry over onto "
                     f"'{target_branch}' rather than staying on '{actual_branch}'.")
                proceed = ask_yn(f"Proceed with checking out {target_branch} anyway?", default=False)
            if proceed and ask_yn(f"Check out {target_branch}?", default=True):
                result = run(["git", "-C", str(path), "checkout", target_branch])
                if result.returncode != 0:
                    fail("Checkout failed:")
                    print(result.stderr)
                else:
                    ok(f"Checked out {target_branch}")
        return path

    print(f"  Cloning ifsnemo-build ({target_branch}) to {path}")
    result = run(["git", "clone", "--recursive", "--branch", target_branch,
                  IFSNEMO_BUILD_URL, str(path)])
    if result.returncode != 0:
        fail("Clone failed:")
        print(result.stderr)
        return None
    ok(f"Cloned to {path}")
    return path


# ---------------------------------------------------------------------------
# Step 3: Target machine setup (yq, psubmit)
# ---------------------------------------------------------------------------
PSUBMIT_URL = "https://github.com/a-v-medvedev/psubmit.git"


def step_target_machine(exec_mode):
    print(f"\n{BOLD}3. Target machine setup (yq, psubmit){RESET}")

    if exec_mode != 'direct':
        print("  In proxy mode, this needs to happen ON the target machine (the one")
        print("  pipeline.py will SSH into), not here. Run this there:\n")
        print("""    ssh <remote_username>@<remote_machine_url>
    mkdir -p ~/bin && cd ~/bin

    # yq (if not already present)
    wget -q https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64 -O ./yq && chmod +x ./yq

    # psubmit helper
    git clone https://github.com/a-v-medvedev/psubmit.git tmp-ps
    chmod +x tmp-ps/*.sh
    mv tmp-ps/*.sh . && rm -fr tmp-ps

    # Ensure bin is in PATH
    echo 'export PATH="$HOME/bin:$PATH"' >> ~/.bashrc && source ~/.bashrc
""")
        input("  Press Enter to continue... ")
        return

    # direct mode: target machine == this machine. yq was already handled in
    # step 2.1; only psubmit.sh (and its sibling scripts) remain.
    existing = shutil.which("psubmit.sh")
    if existing:
        ok(f"psubmit.sh is already in PATH ({existing})")
        return

    print("  psubmit.sh not found.")
    bin_dir = Path(ask("  Directory to install it in (must be in PATH, or you'll "
                        "need to add it)", default=str(Path.home() / "bin"))).expanduser()
    bin_dir.mkdir(parents=True, exist_ok=True)

    tmp_dir = Path(tempfile.mkdtemp(prefix="psubmit-"))
    try:
        clone_dir = tmp_dir / "psubmit"
        result = run(["git", "clone", PSUBMIT_URL, str(clone_dir)])
        if result.returncode != 0:
            fail("Clone failed:")
            print(result.stderr)
            return

        scripts = list(clone_dir.glob("*.sh"))
        if not scripts:
            fail("No .sh scripts found in the cloned psubmit repo.")
            return

        conflicts = [s for s in scripts if (bin_dir / s.name).exists()]
        if conflicts:
            names = ", ".join(s.name for s in conflicts)
            warn(f"{bin_dir} already has: {names}. This script won't overwrite "
                 f"{'them' if len(conflicts) > 1 else 'it'} without asking.")
            if not ask_yn(f"Overwrite {'them' if len(conflicts) > 1 else 'it'}?", default=False):
                warn("Skipped. Resolve manually, or make sure psubmit.sh is in PATH.")
                return

        for script in scripts:
            dest = bin_dir / script.name
            shutil.copy2(script, dest)
            dest.chmod(dest.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        ok(f"Installed {len(scripts)} psubmit script(s) to {bin_dir}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    if shutil.which("psubmit.sh") is None:
        warn(f"{bin_dir} is not in your PATH yet. Add this to your shell rc file:\n"
             f"    export PATH=\"{bin_dir}:$PATH\"\n"
             "  then restart your shell (or `source` the rc file) before running pipeline.py.")


def main():
    print(f"{BOLD}ifsnemo-compare guided setup{RESET}")
    print("Safe to re-run: already-completed steps are detected and skipped.\n")

    step_repo_access()
    exec_mode = ask_exec_mode()
    step_python_packages(exec_mode)
    step_yq()
    step_ifsnemo_build()
    step_target_machine(exec_mode)

    print(f"\n{BOLD}Setup complete.{RESET}")
    print("Remaining: create pipeline.yaml -- see quickstart-testing.md, Section 4.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(1)
