#!/usr/bin/env python3
"""
lbclnk_v40 optional test module for ifsnemo-compare.

Commands (first positional arg):
  clone       - git clone/update from URL + ./dnb.sh :du  (login node, needs internet)
  build       - write overrides.yaml + machine.yaml, run ./dnb.sh :bi  (no internet)
  run-tests   - submit lbclnk job via psubmit.sh and wait for completion
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def run_and_tee(cmd, cwd=None, env=None):
    """Run cmd, stream output live, return (job_id_or_None, full_output)."""
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, env=full_env, bufsize=1, cwd=cwd,
    )
    lines = []
    for line in proc.stdout:
        sys.stdout.write(line)
        lines.append(line)
    proc.wait()
    full = "".join(lines)
    job_id = None
    for line in full.splitlines():
        if line.startswith("Job ID"):
            try:
                job_id = line.split()[2]
                break
            except IndexError:
                pass
    if proc.returncode != 0:
        print(f"\nWarning: '{' '.join(str(c) for c in cmd)}' exited {proc.returncode}", file=sys.stderr)
    return job_id, full


def cmd_clone(args):
    """Clone or update lbclnk_v40 source, then run dnb.sh :du (login node, needs internet)."""
    lbclnk_path = Path(args.lbclnk_path)

    if not lbclnk_path.exists():
        print(f"Cloning {args.lbclnk_url} (branch {args.lbclnk_branch}) -> {lbclnk_path}")
        subprocess.run([
            "git", "clone", "--recursive",
            "--branch", args.lbclnk_branch,
            args.lbclnk_url, str(lbclnk_path),
        ], check=True)
    else:
        print(f"Updating existing clone at {lbclnk_path}")
        subprocess.run(["git", "fetch", "origin"], cwd=lbclnk_path, check=True)
        subprocess.run(["git", "checkout", args.lbclnk_branch], cwd=lbclnk_path, check=True)
        subprocess.run(["git", "pull", "--ff-only"], cwd=lbclnk_path, check=True)
        subprocess.run(
            ["git", "submodule", "update", "--init", "--recursive"],
            cwd=lbclnk_path, check=True,
        )

    subprocess.run(["./dnb.sh", ":du"], cwd=lbclnk_path, check=True)
    print(f"lbclnk clone/update OK: {lbclnk_path}")


def cmd_build(args):
    """Overlay LBC source from ifs-source, write config files, compile (no internet)."""
    lbclnk_path = Path(args.lbclnk_path)

    if not lbclnk_path.exists():
        print(f"ERROR: {lbclnk_path} not found — run 'clone' first.", file=sys.stderr)
        sys.exit(1)

    # Overlay LBC source files from the ifs-source that was built by the main pipeline.
    lbc_src = Path(args.ifs_source_lbc_dir)
    if not lbc_src.is_dir():
        print(f"ERROR: ifs_source_lbc_dir not found: {lbc_src}", file=sys.stderr)
        sys.exit(1)
    dest_src = lbclnk_path / "src"
    lbc_files = list(lbc_src.glob("*.f90")) + list(lbc_src.glob("*.h90"))
    print(f"Overlaying {len(lbc_files)} LBC files from {lbc_src} -> {dest_src}")
    for f in lbc_files:
        shutil.copy2(f, dest_src / f.name)

    # Symlink machine.yaml
    machine_link = lbclnk_path / "machine.yaml"
    if machine_link.exists() or machine_link.is_symlink():
        machine_link.unlink()
    os.symlink(args.machine_file, str(machine_link))
    print(f"Linked machine.yaml -> {args.machine_file}")

    # Write overrides.yaml
    overrides_text = "\n".join([
        "---",
        "environment:",
        f'  - export DNB_SANDBOX_SUBDIR="{args.sandbox}"',
        "  - export LBCLNK_WITH_NORMS=TRUE",
        "  - export LBCLNK_WITH_TIME_MEASUREMENTS=FALSE",
    ]) + "\n"
    (lbclnk_path / "overrides.yaml").write_text(overrides_text)
    print("Wrote overrides.yaml")

    subprocess.run(["./dnb.sh", ":bi"], cwd=lbclnk_path, check=True)

    binary = lbclnk_path / "src" / "sandbox" / args.sandbox / "main"
    if binary.exists():
        print(f"lbclnk build OK: {binary}")
    else:
        print(f"ERROR: expected binary not found at {binary}", file=sys.stderr)
        sys.exit(1)


def cmd_run_tests(args):
    sandbox_dir = Path(args.lbclnk_path) / "src" / "sandbox"
    binary = sandbox_dir / args.sandbox / "main"
    if not binary.exists():
        print(f"ERROR: {binary} not found — run 'build' first.", file=sys.stderr)
        sys.exit(1)

    psubmit_cmd = [
        "psubmit.sh",
        f"-u{args.sandbox}",
        f"-n{args.nodes}",
        f"-p{args.ppn}",
        f"-t{args.threads}",
    ]
    print(f"Submitting: {' '.join(psubmit_cmd)}  (cwd={sandbox_dir})")
    job_id, _ = run_and_tee(psubmit_cmd, cwd=sandbox_dir)

    if not job_id:
        print("WARNING: could not parse Job ID from psubmit output.", file=sys.stderr)
        return

    result_dir = sandbox_dir / f"results.{job_id}"
    if result_dir.exists():
        print(f"lbclnk run-tests done: {result_dir}")
    else:
        print(f"WARNING: result dir {result_dir} not found after job.")


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=["clone", "build", "run-tests"])
    p.add_argument("--lbclnk-path",   required=True)
    p.add_argument("--lbclnk-url",    default="https://gitlab.earth.bsc.es/digital-twins/nvidia/lbclnk_v40.git")
    p.add_argument("--lbclnk-branch", default="baseline")
    p.add_argument("--sandbox",        default="cpu")
    p.add_argument("--machine-file",       default="dnb-mn5-gpp.yaml")
    p.add_argument("--ifs-source-lbc-dir", default="")
    p.add_argument("--nodes",              default="1")
    p.add_argument("--ppn",            default="8")
    p.add_argument("--threads",        default="10")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    {"clone": cmd_clone, "build": cmd_build, "run-tests": cmd_run_tests}[args.command](args)
