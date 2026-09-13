#!/usr/bin/env python3
"""Run the CVA6 cache sweep on the real core, the RTL side of the question
run_gem5_config_sweep.py asks of the simulator.

The work itself is run_CVA6Flow_sweep.py's: it installs a configuration
package, rebuilds the model, runs the workloads and gathers every metrics table
into one file. This points it at this side of the project instead of the
viewer's, so the defaults are the cache geometry package, the calibration
benchmarks and a results folder of its own. Every other flag is passed through.

    python3 scripts/run_CVA6_config_sweep.py --list
    python3 scripts/run_CVA6_config_sweep.py --configs 2-8
    python3 scripts/run_CVA6_config_sweep.py --configs 15,16 --no-vcd

The geometries are the ones in CACHE_TESTS on the gem5 side, in the same order:
a CFG id here plus 199 is the TEST id there.
"""
import argparse
import os
import subprocess
import sys

# The sweep that does the work, beside this script inside the container and in
# the viewer's own folder in a checkout.
WORKER = "run_CVA6Flow_sweep.py"
WORKER_DIRS = (".", os.path.join("viewers", "CVA6Flow", "scripts"))

# The package this sweep installs, rather than the viewer's.
CONFIG_PKG = "cv64a6_imafdc_sv39_hpdcache_wb_config_testing_pkg.sv"
CONFIG_DIRS = ("CVA6_configs",
               os.path.join("gem5_config_CVA6", "CVA6", "configs"))

# The calibration programs, which is what the gem5 side measures.
TESTS_DIRS = (os.path.join("benchmarks", "config"),
              os.path.join("gem5_config_CVA6", "CVA6", "benchmarks"))

OUT_DIR = os.path.join("results", "sweep_CVA6_config")


def beside_script(name, folders):
    """The first of the named folders holding name, looked for beside this
    script first and then under the working directory, since the container has
    everything in scripts/ and a checkout keeps it where it belongs."""
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    for base in (here, os.curdir, root):
        for folder in folders:
            candidate = os.path.join(base, folder, name)
            if os.path.isfile(candidate):
                return os.path.abspath(candidate)
    return None


def first_dir(folders):
    """The first of the folders that exists, beside this script or under the
    working directory."""
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    for base in (os.curdir, here, root):
        for folder in folders:
            candidate = os.path.join(base, folder)
            if os.path.isdir(candidate):
                return os.path.abspath(candidate)
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Run the CVA6 cache sweep. Unknown flags go to "
                    f"{WORKER}, so its --list, --configs, --tests and "
                    "--no-vcd all work here.",
        add_help=False)
    parser.add_argument("-h", "--help", action="store_true",
                        help="Show this help and the worker's")
    args, passthrough = parser.parse_known_args()

    worker = beside_script(WORKER, WORKER_DIRS)
    if worker is None:
        print(f"[ERROR] {WORKER} is not beside this script or in "
              f"{WORKER_DIRS[1]}/. It does the work, so there is nothing to "
              f"drive.")
        return 2

    if args.help:
        print(__doc__.strip() + "\n")
        print(f"[INFO] The flags below are {WORKER}'s, and all of them work "
              f"here:\n", flush=True)
        return subprocess.run([sys.executable, worker, "--help"]).returncode

    package = beside_script(CONFIG_PKG, CONFIG_DIRS)
    if package is None:
        print(f"[ERROR] {CONFIG_PKG} not found in "
              f"{' or '.join(d + '/' for d in CONFIG_DIRS)}. That package "
              f"carries the cache table this sweep installs.")
        return 2

    tests_dir = first_dir(TESTS_DIRS)
    if tests_dir is None:
        print(f"[ERROR] No benchmark folder found: looked for "
              f"{' and '.join(d + '/' for d in TESTS_DIRS)}")
        return 2

    print(f"[INFO] Package  : {package}")
    print(f"[INFO] Workloads: {tests_dir}")
    print(f"[INFO] Driving  : {worker}", flush=True)
    # The defaults go first so a flag the caller repeats wins, which is how
    # argparse reads a repeated option.
    cmd = [sys.executable, worker,
           "--config-pkg", package,
           "--tests-dir", tests_dir,
           "--out-dir", OUT_DIR] + passthrough
    return subprocess.run(cmd).returncode


if __name__ == "__main__":
    sys.exit(main())
