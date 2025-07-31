#!/usr/bin/env python3
import os
import shutil
import sys
import argparse
import itertools
import subprocess

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

def create_runs(subdirs, root, resolutions, nthreads, ppn, nnodes, nsteps, runtype):
    """
    For each combination of subdir, res, nsteps, nnodes:
      1) submits the job via run_and_tee()
      2) moves results.<jobid> into the right spot under 'root'

    :param subdirs:      list of test names 
    :param resolutions:  list of resolution strings
    :param nthreads:     list of ints
    :param ppn:          list of ints
    :param nnodes:       list of ints
    :param nsteps:       list of ints
    :param runtype:      "ref" or "test"
    """
    if runtype not in ("ref", "test"):
        raise ValueError("runtype must be 'ref' or 'test'")
    
    for subdir, res, nthreads, ppn, nnodes, nsteps in itertools.product(
        subdirs,
        resolutions,
        nthreads,
        ppn,
        nnodes, 
        nsteps
    ):

        run_logdir = os.path.join(
                root[0],
                os.path.basename(subdir.rstrip(os.sep)),
                str(res),
                "nthreads"+str(nthreads),
                "ppn"+str(ppn),
                "nnodes"+str(nnodes),
                "nsteps"+str(nsteps))

        run_logfile = f"{runtype}.res={res}_nt={nthreads}_ppn={ppn}_nn={nnodes}_nst={nsteps}.log"

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
        print(f"Running reference {subdir}:  res={res} nthreads={nthreads} ppn={ppn} nnodes={nnodes} nsteps={nsteps}\n")
        psubmit_cmd = ["psubmit.sh", "-t", str(nthreads), "-p", str(ppn), "-n", str(nnodes), "-u", subdir]
        run_jobid, ref_out = run_and_tee(psubmit_cmd,
                                         env={"RESOLUTION":res, "NSTEPS":str(nsteps)})
        
        ## Log ref output
        print(f"Creating {run_logfilepath}")
        with open(run_logfilepath, "w") as f:
            f.write(ref_out)
        print(f"output of {runtype} run {run_jobid} in {run_logfilepath}")

        ## Copy psubmit results to the run_logdir folder
        copy_results(run_jobid, run_logdir)

def compare(ref_subdir, test_subdirs, ref_root, test_root, resolutions, nthreads, ppn, nnodes, nsteps):
    """
    Iterating over the parameters:
    - Run the reference branch test
    - Capture the <test_jobid>; the test results are in results.<test_jobid>
    - Compare norms with the reference results in `<root>/<ref_subdir>/...`
    """
    for test in test_subdirs:
        for res, nthreads, ppn, nnodes, nsteps in itertools.product(resolutions, nthreads, ppn, nnodes, nsteps):
            base_ref = os.path.join(ref_root,
                                    ref_subdir,
                                    f"{res}", 
                                    f"nthreads{nthreads}",
                                    f"ppn{ppn}",
                                    f"nnodes{nnodes}",
                                    f"nsteps{nsteps}", 
                                    "results")

            print(f"Expecting reference dir at {base_ref}")
            if not os.path.isdir(base_ref):
                print(f"[WARN] missing reference dir {base_ref}: skipping")
                continue
            # Run the test run and capture its jobid
            print(f"Running test resolution {res} nthreads {nthreads} ppn {ppn} nnodes {nnodes} nsteps {nsteps}")
            test_cmd = ["psubmit.sh", "-t", str(nthreads), "-p", str(ppn), "-n", str(nnodes), "-u", test]
            test_jobid, _ = run_and_tee(test_cmd,
                                        env={"RESOLUTION":res, "NSTEPS":str(nsteps)})

            print(f"[COMPLETED] jobid {test_jobid}: test resolution {res} nthreads {nthreads} ppn {ppn} nnodes {nnodes} nsteps {nsteps}")


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
    p1.add_argument("-s", "--nsteps", nargs="+", type=int, default=[1],
                    help="Number of steps")
    p1.set_defaults(func=lambda args: create_runs(
        args.ref_subdirs, args.output_refdir, args.resolutions, args.nthreads, args.ppn, args.nnodes, args.nsteps, runtype="ref"
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
    p2.add_argument("-s", "--nsteps", nargs="+", type=int, default=[1],
                    help="Number of steps")

    p2.set_defaults(func=lambda args: create_runs(
        args.test_subdirs, args.output_testdir, args.resolutions, args.nthreads, args.ppn, args.nnodes, args.nsteps, runtype="test"
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
    p3.add_argument("-s", "--nsteps", nargs="+", type=int, default=[1],
                    help="Number of steps")
    p3.set_defaults(func=lambda args: compare(
        args.ref_subdir, args.test_subdirs,
        args.output_refdir, args.output_testdir,
        args.resolutions, args.nthreads, args.ppn, args.nnodes, args.nsteps
    ))

    return p.parse_args()

def main():
    args = parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
