#!/usr/bin/env python3
import os, time
import shutil
import sys
import argparse
import itertools
import subprocess
import tempfile

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
        bufsize=1, # line-buffered
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
                pass # Ignore malformed "Job ID" lines

    if proc.returncode != 0:
        print(f"\nWarning: '{' '.join(cmd)}' exited with status {proc.returncode}", file=sys.stderr)

    if not jobid:
        raise RuntimeError("Could not find Job ID in psubmit output")

    return [jobid, full_output]

#Section 3: Task Loops

def create_runs(subdirs, root, resolutions, nthreads, ppn, nnodes, nsteps, gpus, runtype):
    """
    For each combination of subdir, res, nsteps, nnodes:
      1) submits the job via run_and_tee()
      2) moves results.<jobid> into the right spot under 'root'

    :param subdirs:      list of test names 
    :param resolutions:  list of resolution strings
    :param nthreads:     list of ints
    :param ppn:          list of ints
    :param nnodes:       list of ints
    :param nsteps:       list of ints or strings
    :param gpus:         list of ints
    :param runtype:      "ref" or "test"
    """
    if runtype not in ("ref", "test"):
        raise ValueError("runtype must be 'ref' or 'test'")
    
    for subdir, res, nthreads, ppn, nnodes, gpus, nsteps in itertools.product(
        subdirs,
        resolutions,
        nthreads,
        ppn,
        nnodes, 
        gpus,
        nsteps
    ):

        # Build path components, include gpus part only when non-zero
        parts = [
                root[0],
                os.path.basename(subdir.rstrip(os.sep)),
                str(res),
                "nthreads"+str(nthreads),
                "ppn"+str(ppn),
                "nnodes"+str(nnodes),
        ]
        if gpus != 0:
            parts.append("gpus"+str(gpus))
        parts.append("nsteps"+str(nsteps))

        run_logdir = os.path.join(*parts)

        run_logfile = f"{runtype}.res={res}_nt={nthreads}_ppn={ppn}_nn={nnodes}_g={gpus}_nst={nsteps}.log"

        run_logfilepath = os.path.join(
            run_logdir,
            run_logfile
        )
        if os.path.isfile(run_logfilepath) and runtype == "ref":
            print(f"[SKIP] {run_logdir} already contains a run log and we are running reference creation")
            continue

        print(f"Creating {run_logdir}")
        ensure_dir(run_logdir)

        ## (A) Run the reference job
        print(f"Running reference {subdir}:  res={res} nthreads={nthreads} ppn={ppn} nnodes={nnodes} gpus={gpus} nsteps={nsteps}\n")
                # when building psubmit_cmd in compare_norms.py
        psubmit_cmd = [
            "psubmit.sh",
            "-t", str(nthreads), "-p", str(ppn), "-n", str(nnodes),
            "-u", subdir,
            "-l", f"time={120}:ngpus={gpus}",
        ]
        
        run_jobid, ref_out = run_and_tee(psubmit_cmd,
                                         env={"RESOLUTION":res, "NSTEPS":str(nsteps), "PSUBMIT_OMIT_STACKTRACE_SCAN": "ON"})
        
        ## Log ref output
        print(f"Creating {run_logfilepath}")
        with open(run_logfilepath, "w") as f:
            f.write(ref_out)
        print(f"output of {runtype} run {run_jobid} in {run_logfilepath}")

        ## Copy psubmit results to the run_logdir folder
        copy_results(run_jobid, run_logdir)



def compare(ref_subdir, test_subdirs, ref_root, test_root, resolutions, nthreads, ppn, nnodes, nsteps, gpus):
    """
    Iterating over the parameters:
    - Run the reference branch test
    - Capture the <test_jobid>; the test results are in results.<test_jobid>
    - Compare norms with the reference results in `<root>/<ref_subdir>/...`
    """
    for test in test_subdirs:
        for res, nthreads, ppn, nnodes, gpus, nsteps in itertools.product(resolutions, nthreads, ppn, nnodes, gpus, nsteps):
            # Build reference path components, include gpus part only when non-zero
            ref_parts = [
                ref_root[0],
                ref_subdir,
                f"{res}",
                f"nthreads{nthreads}",
                f"ppn{ppn}",
                f"nnodes{nnodes}",
            ]
            if gpus != 0:
                ref_parts.append(f"gpus{gpus}")
            ref_parts.append(f"nsteps{nsteps}")
            base_ref = os.path.join(*ref_parts, "results")

            print(f"Expecting reference dir at {base_ref}")
            if not os.path.isdir(base_ref):
                print(f"[WARN] missing reference dir {base_ref}: skipping")
                continue

            # Build test path components, include gpus part only when non-zero
            test_parts = [
                test_root[0],
                test,
                f"{res}",
                f"nthreads{nthreads}",
                f"ppn{ppn}",
                f"nnodes{nnodes}",
            ]
            if gpus != 0:
                test_parts.append(f"gpus{gpus}")
            test_parts.append(f"nsteps{nsteps}")
            base_test = os.path.join(*test_parts, "results")

            print(f"Expecting test dir at {base_test}")
            if not os.path.isdir(base_test):
                print(f"[WARN] missing test dir {base_test}: skipping")
                continue

            compare_cmd = ["./compare.sh", base_ref, base_test]
            result = subprocess.run(
                compare_cmd,
                capture_output=True,
                text=True
            )            
            print(f"\n>>> {compare_cmd[0]} exited {result.returncode}")
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
                    help="One or more reference binary directories")
    p1.add_argument("-og", "--output-refdir", nargs=1, required=True,
                    help="The directory in which to store the result output")
    p1.add_argument("-r", "--resolutions", nargs="+", default=["tco79-eORCA1"],
                    help="RESolution names")
    p1.add_argument("-nt", "--nthreads", nargs="+", type=int, default=[1],
                    help="Number of threads")
    p1.add_argument("-p", "--ppn", nargs="+", type=int, default=[1],
                    help="Number of processes per node")
    p1.add_argument("-n", "--nnodes", nargs="+", type=int, default=[1],
                    help="Number of nodes")
    p1.add_argument("-s", "--nsteps", nargs="+", default=["d1"],
                    help="Number of steps (can be string, e.g., 'd1')")
    p1.add_argument("--gpus", nargs="+", type=int, default=[0],
                    help="Number of gpus")
    p1.set_defaults(func=lambda args: create_runs(
        args.ref_subdirs, args.output_refdir, args.resolutions, args.nthreads, args.ppn, args.nnodes, args.nsteps, args.gpus, runtype="ref"
    ))

    # run tests
    p2 = subs.add_parser("run-tests", help="Run the tests")
    p2.add_argument("-t", "--test-subdirs", nargs="+", required=True,
                    help="One or more test binary directories")
    p2.add_argument("-ot", "--output-testdir", nargs=1, required=True,
                    help="The directory in which to store the test result output")
    p2.add_argument("-r", "--resolutions", nargs="+", default=["tco79-eORCA1"])
    p2.add_argument("-nt", "--nthreads", nargs="+", type=int, default=[1],
                    help="Number of threads")
    p2.add_argument("-p", "--ppn", nargs="+", type=int, default=[1],
                    help="Number of processes per node")
    p2.add_argument("-n", "--nnodes", nargs="+", type=int, default=[1],
                    help="Number of nodes")
    p2.add_argument("-s", "--nsteps", nargs="+", default=["d1"],
                    help="Number of steps (can be string, e.g., 'd1')")
    p2.add_argument("--gpus", nargs="+", type=int, default=[0],
                    help="Number of gpus")

    p2.set_defaults(func=lambda args: create_runs(
        args.test_subdirs, args.output_testdir, args.resolutions, args.nthreads, args.ppn, args.nnodes, args.nsteps, args.gpus, runtype="test"
    ))

    # compare
    p3 = subs.add_parser("compare", help="Diff refs vs. tests")
    p3.add_argument("-g", "--ref-subdir", required=True,
                    help="Which reference binary to compare against")
    p3.add_argument("-t", "--test-subdirs", nargs="+", required=True,
                    help="One or more test binary directories")
    p3.add_argument("-og", "--output-refdir", nargs=1, required=True,
                    help="The directory in which the references are stored")
    p3.add_argument("-ot", "--output-testdir", nargs=1, required=True,
                    help="The directory in which the test result outputs are stored")
    p3.add_argument("-r", "--resolutions", nargs="+", default=["tco79-eORCA1"])
    p3.add_argument("-nt", "--nthreads", nargs="+", type=int, default=[1],
                    help="Number of threads")
    p3.add_argument("-p", "--ppn", nargs="+", type=int, default=[1],
                    help="Number of processes per node")
    p3.add_argument("-n", "--nnodes", nargs="+", type=int, default=[1],
                    help="Number of nodes")
    p3.add_argument("-s", "--nsteps", nargs="+", default=["d1"],
                    help="Number of steps (can be string, e.g., 'd1')")
    p3.add_argument("--gpus", nargs="+", type=int, default=[0],
                    help="Number of gpus")
    p3.set_defaults(func=lambda args: compare(
        args.ref_subdir, args.test_subdirs,
        args.output_refdir, args.output_testdir,
        args.resolutions, args.nthreads, args.ppn, args.nnodes, args.nsteps, args.gpus
    ))

    return p.parse_args()

def main():
    args = parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
