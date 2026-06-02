"""Common utilities for ifsnemo-compare test suites."""

import os
import sys
import shutil
import subprocess


def ensure_dir(path):
    """Make dir if missing; no error if it already exists."""
    os.makedirs(path, exist_ok=True)


def copy_results(jobid, ref_dir):
    """Copy results from results.<jobid> to destination directory."""
    src = f"results.{jobid}"
    dst = os.path.join(ref_dir, "results")

    # Make sure destination exists
    os.makedirs(dst, exist_ok=True)

    if not os.path.exists(src):
        print(f"WARNING: Source directory {src} not found")
        return

    for name in os.listdir(src):
        src_path = os.path.join(src, name)
        dst_path = os.path.join(dst, name)

        if os.path.isfile(src_path):
            print(f"Copying file: {src_path} -> {dst_path}")
            shutil.copy2(src_path, dst_path)


def run_and_tee(cmd, env=None):
    """
    Launch subprocess(cmd), stream all output to console,
    detect 'Job ID <id>' line, and return (jobid, full_output).

    This implementation streams output to avoid deadlocks.
    It warns on non-zero exit from the subprocess but does not raise an exception,
    as some submission scripts may exit non-zero on success.
    """
    full_env = os.environ.copy()
    if env:
        full_env.update(env)

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=full_env,
        bufsize=1,  # line-buffered
    )

    stdout_lines = []
    for line in proc.stdout:
        sys.stdout.write(line)
        stdout_lines.append(line)

    proc.wait()
    full_output = "".join(stdout_lines)

    jobid = None
    for line in full_output.splitlines():
        if line.startswith("Job ID"):
            try:
                jobid = line.split(" ", 1)[1].split()[1]
                break
            except IndexError:
                pass  # Ignore malformed "Job ID" lines

    if proc.returncode != 0:
        print(f"\nWarning: '{' '.join(cmd)}' exited with status {proc.returncode}", file=sys.stderr)

    if not jobid:
        raise RuntimeError("Could not find Job ID in psubmit output")

    return [jobid, full_output]
