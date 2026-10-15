#!/usr/bin/env python3
"""
create_reference.py  —  Promote a successful test run to a gold-standard reference tag.

Five-stage pipeline (Template Method):

    Stage 1  validate_prerequisites   – all run outputs must exist before anything is touched
    Stage 2  init_reference_layout    – idempotent directory scaffolding under the new tag
    Stage 3  archive_bundle_artifacts – invoke bundle_validator create-refs → bundle_validation.json
    Stage 4  archive_norm_results     – copy highest-numbered result.*.yaml per config
    Stage 5  push_to_git              – shallow-clone references repo, commit, push

Usage (remote HPC, from ifsnemo-compare/tests/create_reference/):

    python3 create_reference.py \\
        --tag          ifs.DE_CY49R3_climateDT_20261014.SP.CPU.GPP \\
        --test-subdir  ifsMASTER.SP.CPU.GPP \\
        --tests-root   /gpfs/.../ifsnemo/tests \\
        --refs-root    /gpfs/.../ifsnemo/references \\
        --raps-bundle-yaml /gpfs/.../ifsnemo-build/src/ifsnemo-XXX.src/49r3.yml \\
        --build-dir    /gpfs/.../ifsnemo-build/build \\
        --resolution   tco79-eORCA1 tco399-eORCA025 \\
        --threads      4 4 \\
        --ppn          28 28 \\
        --nodes        1 16 \\
        --steps        d1 d1 \\
        --repo-url     https://gitlab.earth.bsc.es/ces/hpc-for-es-team/ifsnemo-compare-references.git

Add --dry-run to preview all actions without writing anything.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


# ---------------------------------------------------------------------------
# Stage 1 — validate
# ---------------------------------------------------------------------------

def validate_prerequisites(
    tests_root: Path,
    test_subdir: str,
    configs: list,
    bundle_tests_dir: Path,
) -> None:
    """
    Assert every expected output exists before touching the reference tree.

    Checks:
    - bundle_validator test directory is present
    - every config has at least one result.*.yaml in its results/ dir

    Raises SystemExit with a clear message on the first missing item.
    """
    _banner("Stage 1: Validating prerequisites")

    if not bundle_tests_dir.is_dir():
        _fail(f"Bundle validator test output directory not found: {bundle_tests_dir}\n"
              f"  Run bundle_validator run-tests first.")

    missing = []
    for cfg in configs:
        result_dir = _norm_test_result_dir(tests_root, test_subdir, cfg)
        yamls = sorted(result_dir.glob("result.*.yaml"))
        if not yamls:
            missing.append(str(result_dir))
        else:
            _info(f"  [{cfg['resolution']}]  {len(yamls)} yaml(s)  → {yamls[-1].name}")

    if missing:
        _fail("Missing norm results for config(s):\n" +
              "\n".join(f"  {p}" for p in missing) +
              "\n  Run compare_norms run-tests first.")

    _info("  All prerequisites satisfied.")


# ---------------------------------------------------------------------------
# Stage 2 — layout
# ---------------------------------------------------------------------------

def init_reference_layout(refs_root: Path, tag: str, configs: list) -> Path:
    """
    Create the directory skeleton for the new tag.  Idempotent — safe to call
    if a partial tag directory already exists.

    Tree created:
        <refs_root>/<tag>/
            bundle_validator/
            <resolution>/nthreads<t>/ppn<p>/nnodes<n>/nsteps<s>/results/  (per config)

    Returns the tag root Path.
    """
    _banner("Stage 2: Initialising reference layout")

    tag_dir = refs_root / tag
    if tag_dir.exists():
        _warn(f"Tag directory already exists, will overwrite: {tag_dir}")
    (tag_dir / "bundle_validator").mkdir(parents=True, exist_ok=True)
    for cfg in configs:
        _norm_ref_result_dir(tag_dir, cfg).mkdir(parents=True, exist_ok=True)
        _info(f"  mkdir  {_norm_ref_result_dir(tag_dir, cfg).relative_to(refs_root)}")

    return tag_dir


# ---------------------------------------------------------------------------
# Stage 3 — bundle artifacts
# ---------------------------------------------------------------------------

def archive_bundle_artifacts(
    bundle_yaml: Path,
    build_dir: Path,
    tag_dir: Path,
    dry_run: bool = False,
) -> None:
    """
    Invoke bundle_validator.py create-refs to regenerate and store the
    normalized bundle_validation.json directly into the reference tree.

    Delegates path-normalisation to bundle_validator so the JSON is portable
    across machines with different scratch roots.

    Dest: <tag_dir>/bundle_validator/bundle_validation.json
    """
    _banner("Stage 3: Archiving bundle_validator artifacts")

    script = Path(__file__).parent.parent / "bundle_validator" / "bundle_validator.py"
    dest_dir = tag_dir / "bundle_validator"
    cmd = [
        sys.executable, str(script),
        "create-refs",
        str(bundle_yaml),
        str(build_dir),
        "-og", str(dest_dir),
    ]
    _run(cmd, dry_run)
    _info(f"  bundle_validation.json → {dest_dir}")


# ---------------------------------------------------------------------------
# Stage 4 — norm results
# ---------------------------------------------------------------------------

def archive_norm_results(
    tests_root: Path,
    test_subdir: str,
    tag_dir: Path,
    configs: list,
    dry_run: bool = False,
) -> None:
    """
    For each config, select the highest job ID from result.*.yaml, then copy
    ALL files suffixed with that job ID plus job-ID-free files (e.g. parser.awk).

    Skips plot/image files (parse-and-plot outputs, not reference material).
    ENV_BEFORE.* is intentionally included — scan_for_secrets() gates the push.

    Source: <tests_root>/<test_subdir>/<res>/.../results/*.<jobid>
    Dest:   <tag_dir>/<res>/.../results/*.<jobid>
    """
    _banner("Stage 4: Archiving norm results")

    _SKIP_SUFFIXES = (".png", ".jpg", ".jpeg", ".pdf")

    for cfg in configs:
        src_dir = _norm_test_result_dir(tests_root, test_subdir, cfg)
        yamls = sorted(src_dir.glob("result.*.yaml"))
        jobid = yamls[-1].stem.split(".")[-1]  # highest job-id = most recent run

        dest_dir = _norm_ref_result_dir(tag_dir, cfg)
        copied = []

        for f in src_dir.iterdir():
            if not f.is_file():
                continue
            # only files from the chosen job or job-ID-free files
            if not (f.name.endswith(f".{jobid}") or "." not in f.name):
                continue
            if any(f.name.endswith(s) for s in _SKIP_SUFFIXES):
                continue
            _copy(f, dest_dir / f.name, dry_run)
            copied.append(f.name)

        _info(f"  [{cfg['resolution']}]  job {jobid}  →  {len(copied)} file(s)")


# ---------------------------------------------------------------------------
# Stage 5 — secrets scan
# ---------------------------------------------------------------------------

def scan_for_secrets(tag_dir: Path, dry_run: bool = False) -> None:
    """
    Run gitleaks over the written reference tree before anything is pushed.

    Uses --no-git so gitleaks treats the directory as plain files rather than
    a repository.  Exits with a loud error if any secrets are detected, or if
    gitleaks is missing — the push stage must never run on an unscanned tree.
    """
    _banner("Stage 5: Scanning for secrets")

    if dry_run:
        _info("  [dry] gitleaks detect --no-git --source <tag_dir>")
        return

    # Appended, so a gitleaks already in the user's PATH is found first.
    os.environ["PATH"] += os.pathsep + str(Path(__file__).resolve().parents[2] / "tools")
    if not shutil.which("gitleaks"):
        _fail("gitleaks not found in PATH or tools/ — refusing to continue without a secrets scan.\n"
              "  Install it with:  bash tools/install_gitleaks.sh")

    result = subprocess.run(
        ["gitleaks", "detect", "--no-git", "--source", str(tag_dir)],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(result.stdout, file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        print("\n" + "!" * 70, file=sys.stderr)
        print("  ⛔  SECRETS DETECTED in reference tree — PUSH ABORTED", file=sys.stderr)
        print("  Review the findings above, remove the offending files,", file=sys.stderr)
        print("  and re-run before pushing to the references repository.", file=sys.stderr)
        print("!" * 70 + "\n", file=sys.stderr)
        sys.exit(1)

    _info("  No secrets detected.")


# ---------------------------------------------------------------------------
# Stage 5 — git push
# ---------------------------------------------------------------------------

def push_to_git(
    tag_dir: Path,
    tag: str,
    repo_url: str,
    branch: str,
    path_in_repo: str,
    dry_run: bool = False,
) -> None:
    """
    Shallow-clone the references repo into a temp directory, copy the new
    tag tree into <path_in_repo>/<tag>/, commit with the tag name as the
    message, and push.

    A shallow clone is used to avoid pulling the full history of a repo
    that accumulates large reference blobs over time.
    """
    _banner("Stage 6: Pushing to references git repository")

    # Explicit dir: tempfile would silently fall back to /tmp if TMPDIR were unset or unusable.
    with tempfile.TemporaryDirectory(prefix="ifsnemo-ref-", dir=os.environ["TMPDIR"]) as tmp:
        clone_dir = Path(tmp) / "repo"
        _run(["git", "clone", "--depth=1", "-b", branch, repo_url, str(clone_dir)], dry_run)

        dest_root = clone_dir / path_in_repo / tag
        if dry_run:
            _info(f"  [dry] copytree {tag_dir} → {dest_root}")
        else:
            if dest_root.exists():
                shutil.rmtree(dest_root)
            shutil.copytree(tag_dir, dest_root)

        _run(["git", "-C", str(clone_dir), "add", "-A"], dry_run)
        _run(["git", "-C", str(clone_dir), "commit",
              "-m", f"Add reference tag: {tag}"], dry_run)
        _run(["git", "-C", str(clone_dir), "push", "origin", branch], dry_run)

    _info(f"  Pushed tag '{tag}' to {repo_url} ({branch}/{path_in_repo}/)")


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def create_reference(args: argparse.Namespace) -> None:
    """
    Drive the six-stage pipeline.  Stages run in dependency order;
    failure in any stage aborts before later stages can modify state.

    Template Method: each stage is an independently-testable function,
    called here in a fixed sequence with shared context.
    """
    tests_root = Path(args.tests_root)
    refs_root  = Path(args.refs_root)
    bundle_yaml = Path(args.bundle_yaml)
    build_dir   = Path(args.build_dir)
    configs = _parse_configs(args)

    bundle_tests_dir = tests_root / "bundle_validator"

    print(f"\n{'='*60}")
    print(f"  Creating reference tag:  {args.tag}")
    if args.dry_run:
        print("  DRY RUN — no files will be written or pushed")
    print(f"{'='*60}")

    validate_prerequisites(tests_root, args.test_subdir, configs, bundle_tests_dir)
    tag_dir = init_reference_layout(refs_root, args.tag, configs)
    archive_bundle_artifacts(bundle_yaml, build_dir, tag_dir, args.dry_run)
    archive_norm_results(tests_root, args.test_subdir, tag_dir, configs, args.dry_run)
    scan_for_secrets(tag_dir, args.dry_run)

    if args.repo_url:
        push_to_git(tag_dir, args.tag, args.repo_url, args.branch,
                    args.path_in_repo, args.dry_run)
    else:
        _info("\n(Stage 6 skipped — no --repo-url provided; reference written locally only)")

    print(f"\n{'='*60}")
    print(f"  Done.  Reference: {tag_dir}")
    print(f"{'='*60}\n")


# ---------------------------------------------------------------------------
# Shared path helpers
# ---------------------------------------------------------------------------

def _norm_test_result_dir(tests_root: Path, test_subdir: str, cfg: dict) -> Path:
    return (tests_root / test_subdir / cfg["resolution"]
            / f"nthreads{cfg['threads']}" / f"ppn{cfg['ppn']}"
            / f"nnodes{cfg['nodes']}" / f"nsteps{cfg['steps']}" / "results")


def _norm_ref_result_dir(tag_dir: Path, cfg: dict) -> Path:
    return (tag_dir / cfg["resolution"]
            / f"nthreads{cfg['threads']}" / f"ppn{cfg['ppn']}"
            / f"nnodes{cfg['nodes']}" / f"nsteps{cfg['steps']}" / "results")


# ---------------------------------------------------------------------------
# Internal utilities
# ---------------------------------------------------------------------------

def _parse_configs(args: argparse.Namespace) -> list:
    lists = [args.resolution, args.threads, args.ppn, args.nodes, args.steps]
    names = ["--resolution", "--threads", "--ppn", "--nodes", "--steps"]
    lengths = [len(x) for x in lists]
    if len(set(lengths)) != 1:
        _fail("All of " + ", ".join(names) + " must have the same number of values.\n"
              "  Got: " + ", ".join(f"{n}={l}" for n, l in zip(names, lengths)))
    return [
        {"resolution": r, "threads": t, "ppn": p, "nodes": n, "steps": s}
        for r, t, p, n, s in zip(*lists)
    ]


def _copy(src: Path, dest: Path, dry_run: bool) -> None:
    if dry_run:
        _info(f"  [dry] cp  {src.name}  →  {dest.parent.parent.parent.parent.name}/…/{dest.name}")
    else:
        shutil.copy2(src, dest)


def _run(cmd: list, dry_run: bool) -> None:
    _info("  $  " + " ".join(str(c) for c in cmd))
    if not dry_run:
        subprocess.run(cmd, check=True)


def _banner(msg: str) -> None:
    print(f"\n--- {msg}", flush=True)


def _info(msg: str) -> None:
    print(msg, flush=True)


def _warn(msg: str) -> None:
    print(f"[WARN] {msg}", file=sys.stderr, flush=True)


def _fail(msg: str) -> None:
    print(f"\n❌  ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Reference identity
    p.add_argument("--tag", required=True,
                   help="New reference tag name  (e.g. ifs.DE_CY49R3_climateDT_20261014.SP.CPU.GPP)")

    # Source paths
    p.add_argument("--test-subdir", required=True, dest="test_subdir",
                   help="Build subdirectory containing test outputs  (e.g. ifsMASTER.SP.CPU.GPP)")
    p.add_argument("--tests-root",  required=True, dest="tests_root",
                   help="Path to ifsnemo/tests/")
    p.add_argument("--refs-root",   required=True, dest="refs_root",
                   help="Path to ifsnemo/references/")
    p.add_argument("--raps-bundle-yaml", required=True, dest="bundle_yaml",
                   help="Path to the RAPS bundle yaml used for this build (e.g. 49r3.yml)")
    p.add_argument("--build-dir",   required=True, dest="build_dir",
                   help="Path to the CMake build directory (for bundle_validator)")

    # Configuration matrix — must all be the same length
    p.add_argument("--resolution", required=True, nargs="+",
                   help="Resolution(s)  e.g. tco79-eORCA1 tco399-eORCA025")
    p.add_argument("--threads",    required=True, nargs="+",
                   help="OMP thread count(s) matching --resolution order")
    p.add_argument("--ppn",        required=True, nargs="+",
                   help="MPI ranks per node matching --resolution order")
    p.add_argument("--nodes",      required=True, nargs="+",
                   help="Node count(s) matching --resolution order")
    p.add_argument("--steps",      required=True, nargs="+",
                   help="Step spec(s)  e.g. d1 d1")

    # Git push (optional)
    p.add_argument("--repo-url",     default=None, dest="repo_url",
                   help="References git repo URL  (omit to skip push)")
    p.add_argument("--branch",       default="main",
                   help="References repo branch  (default: main)")
    p.add_argument("--path-in-repo", default="references", dest="path_in_repo",
                   help="Subdirectory inside the repo  (default: references)")

    p.add_argument("--dry-run", action="store_true", dest="dry_run",
                   help="Print all actions without writing or pushing anything")

    return p


if __name__ == "__main__":
    create_reference(build_parser().parse_args())
