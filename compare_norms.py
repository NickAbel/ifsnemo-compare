#!/usr/bin/env python3
import os
import shutil
import sys
import argparse
import itertools
import subprocess

REF_DIR_ROOT = "compare_norms_refs"

#Section 1: File+Dir Utilities

def ensure_dir(path):
    """Make dir if missing; no error if it already exists."""
    os.makedirs(path, exist_ok=True)

def skip_if_done(path, marker="foo"):
    """
    Return True (and skip) if `path/marker` exists.
    """
    return os.path.isfile(os.path.join(path, marker))

def copy_results(jobid, ref_dir):
    src = f"results.{jobid}"
    dst = os.path.join(ref_dir, f"results")

    # Make sure destination exists
    os.makedirs(dst, exist_ok=True)

    for name in os.listdir(src):
        src_path = os.path.join(src, name)
        dst_path = os.path.join(dst, name)

        if os.path.isfile(src_path):
            print(f"Copying file: {src_path} -> {dst_path}")
            shutil.copy2(src_path, dst_path)

#Section 2: Job Runner

def run_and_tee(cmd, env=None):
    """
    Launch subprocess(cmd), stream stdout to console, capture all output,
    detect 'Job ID <id>' line, and return (jobid, full_output).
    Raises on nonzero exit.
    """
    full_env = os.environ.copy()
    if env:
        full_env.update(env)

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=full_env,
    )

    lines = []
    for line in proc.stdout:
        sys.stdout.write(line)   # tee
        lines.append(line)       # capture for later
        if line.startswith("Job ID"):
            jobid = line.split(" ", 1)[1].split()[1]

    proc.wait()
 
    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, cmd)
    if not jobid:
        raise RuntimeError("Could not find Job ID in psubmit output")

    return [jobid, ''.join(lines)]

#Section 3: Task Loops

def create_refs(subdirs, resolutions, nsteps, ntasks):
    for subdir, res, nsteps, ntasks in itertools.product(
        subdirs,
        resolutions,
        nsteps,
        ntasks
    ):

        run_ref_dir = os.path.join(
                REF_DIR_ROOT,
                os.path.basename(subdir.rstrip(os.sep)),
                str(res),
                "nsteps"+str(nsteps),
                "ntasks"+str(ntasks))

        ref_log = f"ref.res={res}_nst={nsteps}_nt={ntasks}.log"

        ref_logpath = os.path.join(
            run_ref_dir,
            ref_log
        )
        if os.path.isfile(ref_logpath):
            print(f"[SKIP] {run_ref_dir} already contains a run log")
            continue

        print(f"Creating {run_ref_dir}")
        ensure_dir(run_ref_dir)

        ## (A) Run the reference job
        print(f"Running reference {subdir}:  res={res} nsteps={nsteps} ntasks={ntasks}\n")
        ref_cmd = ["psubmit.sh", "-n", str(ntasks), "-u", subdir]
        ref_jobid, ref_out = run_and_tee(ref_cmd,
                                         env={"RESOLUTION":res, "NSTEPS":str(nsteps)})
        
        ## Log ref output
        print(f"Creating {ref_logpath}")
        with open(ref_logpath, "w") as f:
            f.write(ref_out)
        print(f"Reference run output at: {ref_logpath}")

        ## Copy psubmit results to the compare_norms ref folder
        copy_results(ref_jobid, run_ref_dir)

def compare(ref_subdir, test_subdirs, resolutions, nsteps, ntasks):
    """
    Iterating over the parameters:
    - Run the reference branch test
    - Capture the <test_jobid>; the test results are in results.<test_jobid>
    - Compare norms with the reference results in `<REF_DIR_ROOT>/<ref_subdir>/...`
    """
    for test in test_subdirs:
        for res, nsteps, ntasks in itertools.product(resolutions, nsteps, ntasks):
            base_ref = os.path.join(REF_DIR_ROOT,
                                    ref_subdir,
                                    f"{res}", 
                                    f"nsteps{nsteps}", 
                                    f"ntasks{ntasks}",
                                    "results")

            print(f"Expecting reference dir at {base_ref}")
            if not os.path.isdir(base_ref):
                print(f"[WARN] missing reference dir {base_ref}: skipping")
                continue
            # Run the test run and capture its jobid
            print(f"Running test resolution {res} nsteps {nsteps} ntasks {ntasks}")
            test_cmd = ["psubmit.sh", "-n", str(ntasks), "-u", test]
            test_jobid, _ = run_and_tee(test_cmd,
                                        env={"RESOLUTION":res, "NSTEPS":str(nsteps)})

            print(f"[COMPLETED] jobid {test_jobid}: test resolution {res} nsteps {nsteps} ntasks {ntasks}")

            base_test = "results." + str(test_jobid)
            cmp_cmd = ["./cmp.sh", base_ref, base_test]
            compare_cmd = ["./compare.sh", base_ref, base_test]

            for cmd in (cmp_cmd, compare_cmd):
                result = subprocess.run(
                    cmd,
                    capture_output=True,  # grabs stdout/stderr
                    text=True             # returns strings not bytes
                )
                print(f"\n>>> {cmd[0]} exited {result.returncode}")
                print("stdout:", result.stdout)
                print("stderr:", result.stderr)


#Section 4: CLI Glue

def parse_args():
    p = argparse.ArgumentParser(prog="compare_norms",
                                description="Automate psubmit refs & diffs")
    subs = p.add_subparsers(dest="cmd", required=True)

    # create-refs
    p1 = subs.add_parser("create-refs", help="Submit jobs and store refs")
    p1.add_argument("-g", "--ref-subdirs", nargs="+", required=True,
                    help="One or more ref subdirectories")
    p1.add_argument("-r", "--resolutions", nargs="+", default=["tco79-eORCA1"],
                    help="RESolution names")
    p1.add_argument("-s", "--nsteps", nargs="+", type=int, default=[100],
                    help="Number of steps")
    p1.add_argument("-n", "--ntasks", nargs="+", type=int, default=[1],
                    help="Number of tasks")
    p1.set_defaults(func=lambda args: create_refs(
        args.ref_subdirs, args.resolutions, args.nsteps, args.ntasks
    ))

    # compare
    p2 = subs.add_parser("compare", help="Diff refs vs. tests")
    p2.add_argument("-g", "--ref-subdir", required=True,
                    help="Which ref subdir to compare against")
    p2.add_argument("-t", "--test-subdirs", nargs="+", required=True,
                    help="One or more test subdirectories")
    p2.add_argument("-r", "--resolutions", nargs="+", default=["tco79-eORCA1"])
    p2.add_argument("-s", "--nsteps", nargs="+", type=int, default=[100])
    p2.add_argument("-n", "--ntasks", nargs="+", type=int, default=[1])
    p2.set_defaults(func=lambda args: compare(
        args.ref_subdir, args.test_subdirs,
        args.resolutions, args.nsteps, args.ntasks
    ))

    return p.parse_args()

def main():
    args = parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
