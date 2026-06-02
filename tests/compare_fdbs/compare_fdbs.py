#!/usr/bin/env python3
"""
FDB comparison test suite for ifsnemo-compare.

This suite:
1. Runs IFS-NEMO with FDB output enabled
2. Generates checksums for FDB .data files
3. Compares test FDB checksums against reference checksums
"""

import argparse
import sys
import os
from pathlib import Path
import json
import hashlib

# Import common utilities
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils import run_and_tee, copy_results, ensure_dir


def run_tests(test_subdir, test_root, resolutions, nthreads, ppn, nnodes, nsteps, gpus):
    """
    Run test with FDB output enabled.

    Similar to compare_norms run-tests but with IFSNEMO_ENABLE_FDB_OUTPUT=1
    """
    print(f"=== FDB Test: {test_subdir} ===\n")

    configs = zip(resolutions, nthreads, ppn, nnodes, nsteps, gpus)

    for res, nt, p, nn, nst, g in configs:
        subdir = test_subdir

        # Create output directory structure
        run_logdir = f"{test_root}/{subdir}/{res}/nthreads{nt}/ppn{p}/nnodes{nn}/nsteps{nst}"
        ensure_dir(run_logdir)

        run_logfilepath = f"{run_logdir}/fdb_test.res={res}_nt={nt}_ppn={p}_nn={nn}_g={g}_nst={nst}.log"

        print(f"Running FDB test {subdir}:  res={res} nthreads={nt} ppn={p} nnodes={nn} gpus={g} nsteps={nst}\n")

        psubmit_cmd = [
            "psubmit.sh",
            "-t", str(nt), "-p", str(p), "-n", str(nn),
            "-u", subdir,
            "-l", f"time={120}:ngpus={g}",
        ]

        # Key difference: Enable FDB output via environment variable
        env = {
            "RESOLUTION": res,
            "NSTEPS": str(nst),
            "PSUBMIT_OMIT_STACKTRACE_SCAN": "ON",
            "IFSNEMO_ENABLE_FDB_OUTPUT": "1"  # <-- Enable FDB
        }

        run_jobid, ref_out = run_and_tee(psubmit_cmd, env=env)

        # Log output
        print(f"Creating {run_logfilepath}")
        with open(run_logfilepath, "w") as f:
            f.write(ref_out)
        print(f"Output of FDB test run {run_jobid} in {run_logfilepath}")

        # Copy psubmit results
        copy_results(run_jobid, run_logdir)

    sys.exit(0)


def generate_checksums(test_subdir, test_root, resolutions, nthreads, ppn, nnodes, nsteps, gpus):
    """
    Generate MD5 checksums for all FDB .data files.

    Scans the FDB directory and creates a manifest of checksums.
    """
    print(f"=== Generating FDB checksums: {test_subdir} ===\n")

    configs = zip(resolutions, nthreads, ppn, nnodes, nsteps, gpus)

    for res, nt, p, nn, nst, g in configs:
        subdir = test_subdir
        results_dir = f"{test_root}/{subdir}/{res}/nthreads{nt}/ppn{p}/nnodes{nn}/nsteps{nst}/results"

        fdb_dir = Path(results_dir) / "fdb"

        if not fdb_dir.exists():
            print(f"WARNING: FDB directory not found: {fdb_dir}")
            print("This means either:")
            print("  1. FDB output was not enabled (check IFSNEMO_ENABLE_FDB_OUTPUT)")
            print("  2. The postproc script didn't collect FDB (needs modification)")
            print("  3. The test failed before producing FDB output")
            continue

        # Find all .data files
        data_files = sorted(fdb_dir.rglob("*.data"))

        if not data_files:
            print(f"WARNING: No .data files found in {fdb_dir}")
            continue

        print(f"Found {len(data_files)} FDB .data files in {fdb_dir}")

        # Generate checksums
        checksums = {}
        for data_file in data_files:
            rel_path = data_file.relative_to(fdb_dir)

            # Calculate MD5
            md5 = hashlib.md5()
            with open(data_file, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    md5.update(chunk)

            checksums[str(rel_path)] = md5.hexdigest()

        # Write checksums to JSON
        checksum_file = Path(results_dir) / "fdb_checksums.json"
        with open(checksum_file, 'w') as f:
            json.dump(checksums, f, indent=2, sort_keys=True)

        print(f"Checksums written to: {checksum_file}")
        print(f"Total files: {len(checksums)}\n")

    sys.exit(0)


def compare(ref_subdir, test_subdir, ref_root, test_root, resolutions, nthreads, ppn, nnodes, nsteps, gpus):
    """
    Compare FDB checksums between test and reference.
    """
    print(f"=== Comparing FDB checksums: {ref_subdir} vs {test_subdir} ===\n")

    configs = zip(resolutions, nthreads, ppn, nnodes, nsteps, gpus)

    all_match = True

    for res, nt, p, nn, nst, g in configs:
        print(f"Comparing: res={res} nt={nt} ppn={p} nn={nn} nst={nst}")

        ref_checksum_file = f"{ref_root}/{ref_subdir}/{res}/nthreads{nt}/ppn{p}/nnodes{nn}/nsteps{nst}/results/fdb_checksums.json"
        test_checksum_file = f"{test_root}/{test_subdir}/{res}/nthreads{nt}/ppn{p}/nnodes{nn}/nsteps{nst}/results/fdb_checksums.json"

        # Check files exist
        if not os.path.exists(ref_checksum_file):
            print(f"ERROR: Reference checksums not found: {ref_checksum_file}")
            all_match = False
            continue

        if not os.path.exists(test_checksum_file):
            print(f"ERROR: Test checksums not found: {test_checksum_file}")
            all_match = False
            continue

        # Load checksums
        with open(ref_checksum_file) as f:
            ref_checksums = json.load(f)

        with open(test_checksum_file) as f:
            test_checksums = json.load(f)

        # Compare
        ref_files = set(ref_checksums.keys())
        test_files = set(test_checksums.keys())

        # Check for missing/extra files
        missing = ref_files - test_files
        extra = test_files - ref_files
        common = ref_files & test_files

        if missing:
            print(f"  Missing files in test: {len(missing)}")
            for f in sorted(missing):
                print(f"    - {f}")
            all_match = False

        if extra:
            print(f"  Extra files in test: {len(extra)}")
            for f in sorted(extra):
                print(f"    + {f}")
            all_match = False

        # Compare checksums for common files
        differences = []
        for fpath in sorted(common):
            if ref_checksums[fpath] != test_checksums[fpath]:
                differences.append(fpath)

        if differences:
            print(f"  Files with different checksums: {len(differences)}")
            for fpath in differences:
                print(f"    ! {fpath}")
                print(f"      ref: {ref_checksums[fpath]}")
                print(f"      test: {test_checksums[fpath]}")
            all_match = False

        if not missing and not extra and not differences:
            print(f"  ✓ All FDB files match ({len(common)} files)")

        print()

    if all_match:
        print("SUCCESS: All FDB checksums match")
        sys.exit(0)
    else:
        print("FAILURE: FDB checksums differ")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description='FDB comparison test suite')
    subparsers = parser.add_subparsers(dest='command', required=True)

    # run-tests subcommand
    p_run = subparsers.add_parser('run-tests', help='Run tests with FDB output enabled')
    p_run.add_argument('-t', '--test-subdir', required=True, help='Test subdirectory')
    p_run.add_argument('-ot', '--output-test-root', required=True, help='Output test root directory')
    p_run.add_argument('-r', '--resolution', required=True, nargs='+', help='Resolutions')
    p_run.add_argument('-nt', '--nthreads', required=True, type=int, nargs='+', help='Thread counts')
    p_run.add_argument('-p', '--ppn', required=True, type=int, nargs='+', help='Processes per node')
    p_run.add_argument('-n', '--nodes', required=True, type=int, nargs='+', help='Node counts')
    p_run.add_argument('-s', '--steps', required=True, nargs='+', help='Step counts')
    p_run.add_argument('-g', '--gpus', type=int, nargs='+', default=None, help='GPU counts')

    # generate-checksums subcommand
    p_gen = subparsers.add_parser('generate-checksums', help='Generate FDB checksums')
    p_gen.add_argument('-t', '--test-subdir', required=True, help='Test subdirectory')
    p_gen.add_argument('-ot', '--output-test-root', required=True, help='Output test root directory')
    p_gen.add_argument('-r', '--resolution', required=True, nargs='+', help='Resolutions')
    p_gen.add_argument('-nt', '--nthreads', required=True, type=int, nargs='+', help='Thread counts')
    p_gen.add_argument('-p', '--ppn', required=True, type=int, nargs='+', help='Processes per node')
    p_gen.add_argument('-n', '--nodes', required=True, type=int, nargs='+', help='Node counts')
    p_gen.add_argument('-s', '--steps', required=True, nargs='+', help='Step counts')
    p_gen.add_argument('-g', '--gpus', type=int, nargs='+', default=None, help='GPU counts')

    # compare subcommand
    p_cmp = subparsers.add_parser('compare', help='Compare FDB checksums')
    p_cmp.add_argument('-t', '--test-subdir', required=True, help='Test subdirectory')
    p_cmp.add_argument('-ot', '--output-test-root', required=True, help='Output test root directory')
    p_cmp.add_argument('-g', '--gold-subdir', required=True, help='Reference subdirectory')
    p_cmp.add_argument('-og', '--output-gold-root', required=True, help='Output reference root directory')
    p_cmp.add_argument('-r', '--resolution', required=True, nargs='+', help='Resolutions')
    p_cmp.add_argument('-nt', '--nthreads', required=True, type=int, nargs='+', help='Thread counts')
    p_cmp.add_argument('-p', '--ppn', required=True, type=int, nargs='+', help='Processes per node')
    p_cmp.add_argument('-n', '--nodes', required=True, type=int, nargs='+', help='Node counts')
    p_cmp.add_argument('-s', '--steps', required=True, nargs='+', help='Step counts')
    p_cmp.add_argument('--gpus', type=int, nargs='+', default=None, help='GPU counts')

    args = parser.parse_args()

    # Default GPUs to 0 if not specified
    if args.gpus is None:
        args.gpus = [0] * len(args.resolution)

    if args.command == 'run-tests':
        run_tests(
            args.test_subdir, args.output_test_root,
            args.resolution, args.nthreads, args.ppn, args.nodes, args.steps, args.gpus
        )
    elif args.command == 'generate-checksums':
        generate_checksums(
            args.test_subdir, args.output_test_root,
            args.resolution, args.nthreads, args.ppn, args.nodes, args.steps, args.gpus
        )
    elif args.command == 'compare':
        compare(
            args.gold_subdir, args.test_subdir, args.output_gold_root, args.output_test_root,
            args.resolution, args.nthreads, args.ppn, args.nodes, args.steps, args.gpus
        )


if __name__ == '__main__':
    main()
