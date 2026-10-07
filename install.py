#!/usr/bin/env python3
"""
Guided, idempotent setup for ifsnemo-compare.

Walks through quickstart-testing.md one step at a time, checking whether
each is already done before doing anything. Built and tested incrementally,
one step at a time -- see quickstart-testing.md for the manual equivalent
of any step not yet covered here.

Deliberately stdlib-only: part of this script's job is installing
pyyaml/fabric, so it can't depend on either of them itself.
"""
import getpass
import os
import subprocess
import sys
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


def ask(prompt, secret=False):
    getter = getpass.getpass if secret else input
    while True:
        val = getter(f"{prompt}: ").strip()
        if val:
            return val
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


def main():
    print(f"{BOLD}ifsnemo-compare guided setup{RESET}")
    print("Safe to re-run: already-completed steps are detected and skipped.\n")

    step_repo_access()

    print(f"\n{BOLD}(more steps to come){RESET}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(1)
