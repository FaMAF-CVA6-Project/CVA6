#!/usr/bin/env python3
"""Check that the patched gem5 build with the patch disabled matches stock.

Two runs of the config benchmarks, compared counter by counter. If they
disagree, something in MinorCPU_CVA6.patch is active when every switch says
it should not be, which no ablation would reveal: every TEST in the campaign
is measured against the patched build, so a patch that changes behaviour with
its switches off moves the whole table and nothing flags it.

Run it from the gem5 root, inside the container, where it sits in scripts/.

    python3 scripts/check_patch_parity.py                 # run both, compare
    python3 scripts/check_patch_parity.py -n              # print the commands
    python3 scripts/check_patch_parity.py --compare A B   # two metrics files

Traces are off on both sides, since only the counters are being compared.
The OFFICIAL column is what is read, not NET: the two builds carry different
overhead profiles, and subtracting them would hide a real difference or
invent one.
"""
import argparse
import glob
import os
import re
import subprocess
import sys

BATCH = "run_all_gem5_benchmarks.py"
STOCK_CONFIG = "gem5_config_CVA6.py"
PATCH_CONFIG = "gem5_config_CVA6_patch.py"

# The fetch geometry is the one place the two configs disagree on purpose,
# while the fetch depth is undecided. Stock is the reference, so the patched
# run is brought down to it rather than the other way about.
STOCK_FETCH_LIMIT = 2
STOCK_FETCH2_BUFFER = 2

# Where each side's batch writes, kept apart so one does not overwrite the
# other and both survive for a second look.
STOCK_OUT = os.path.join("results", "parity", "stock")
PATCH_OUT = os.path.join("results", "parity", "patch")

# The patched build, which the driver needs naming since it is not the
# default. Its binary check is turned off, since it refuses a patched binary
# under --variant stock, which is exactly what this run is.
PATCH_BUILD = "RISCV_PATCH"

# A metrics block opens with this, followed by the program's label.
BLOCK_MARKER = ">>> "

# Derived figures, times and ratios rather than counts. They are compared with
# a tolerance, since the last digit of a float is not a behavioural difference.
FLOAT_METRICS = ("Sim Seconds", "IPC", "Time")
FLOAT_TOLERANCE = 1e-9


def find_batch():
    """The batch driver, beside this script first, which is where the image
    puts it, then in the working directory for a container made before the
    tools moved into scripts/."""
    here = os.path.dirname(os.path.abspath(__file__))
    for candidate in (os.path.join(here, BATCH), os.path.abspath(BATCH)):
        if os.path.isfile(candidate):
            return candidate
    return None


def run(cmd, dry_run):
    print("  $ " + " ".join(cmd), flush=True)
    if dry_run:
        return 0
    return subprocess.run(cmd).returncode


def stock_command(args):
    return ["python3", args.batch, STOCK_CONFIG, args.folder,
            "--variant", "stock", "--no-trace",
            "--out-dir", args.stock_out, "-j", str(args.jobs)]


def patch_command(args):
    """The patched build with every mechanism off and the stock geometry, so
    the only thing left that could differ is the patch itself."""
    return ["python3", args.batch, PATCH_CONFIG, args.folder,
            "--variant", "stock", "--build", PATCH_BUILD,
            "--skip-build-check", "--no-trace",
            "--out-dir", args.patch_out, "-j", str(args.jobs),
            "--", "--no-patch",
            "--fetch-limit", str(args.fetch_limit),
            "--fetch2-buffer", str(args.fetch2_buffer)]


def metrics_file(out_dir):
    """The metrics file the batch gathered, or None."""
    found = sorted(glob.glob(os.path.join(out_dir, "metrics*.txt")))
    return found[-1] if found else None


def parse_metrics(path):
    """{program: {metric: official}} from a gathered metrics file.

    The OFFICIAL column is the first number on a row, which is gem5's own
    counter before any overhead is taken off it."""
    table = {}
    program = None
    for line in open(path, encoding="utf-8", errors="replace"):
        line = line.rstrip("\n")
        if line.startswith(BLOCK_MARKER):
            program = line[len(BLOCK_MARKER):].strip()
            table.setdefault(program, {})
            continue
        if program is None or "|" not in line:
            continue
        cells = [c.strip() for c in line.split("|")]
        if len(cells) < 2 or not cells[0] or cells[0] == "METRIC":
            continue
        value = cells[1].replace(",", "")
        if re.fullmatch(r"-?\d+(\.\d+)?([eE][-+]?\d+)?", value):
            table[program][cells[0]] = value
    return table


def differs(metric, left, right):
    """Whether two readings of one counter disagree in a way that matters."""
    if left == right:
        return False
    if any(metric.startswith(name) for name in FLOAT_METRICS):
        try:
            return abs(float(left) - float(right)) > FLOAT_TOLERANCE
        except ValueError:
            return True
    return True


def compare(stock, patched):
    """Report lines, empty when the two agree everywhere."""
    bad = []
    only_stock = sorted(set(stock) - set(patched))
    only_patch = sorted(set(patched) - set(stock))
    for name in only_stock:
        bad.append(f"{name}: in the stock run only")
    for name in only_patch:
        bad.append(f"{name}: in the patched run only")
    for program in sorted(set(stock) & set(patched)):
        left, right = stock[program], patched[program]
        for metric in sorted(set(left) | set(right)):
            a, b = left.get(metric), right.get(metric)
            if a is None or b is None:
                bad.append(f"{program}: {metric} is missing from one side")
            elif differs(metric, a, b):
                bad.append(f"{program}: {metric} stock {a} patched {b}")
    return bad


def summarise(stock, patched, bad):
    shared = sorted(set(stock) & set(patched))
    counters = sum(len(stock[p]) for p in shared)
    print(f"\n{len(shared)} benchmark(s), {counters} counter(s) compared")
    if not bad:
        print("[ ok ] the patched build with the patch disabled matches stock")
        return 0
    print(f"[FAIL] {len(bad)} difference(s)")
    for line in bad:
        print(f"         {line}")
    print("\nA difference here means a patch mechanism is active with its "
          "switch off.")
    return 1


def main():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Check the patched build with the patch disabled against "
                    "stock.",
        epilog="Run from the gem5 root. The two runs write to separate\n"
               "folders, so both survive for a second look.")
    parser.add_argument("folder", nargs="?", default="benchmarks/config",
                        help="Benchmarks to run. Defaults to "
                             "benchmarks/config")
    parser.add_argument("--compare", nargs=2, metavar=("STOCK", "PATCHED"),
                        help="Compare two gathered metrics files and stop")
    parser.add_argument("--stock-out", default=STOCK_OUT, metavar="DIR",
                        help=f"Where the stock run writes. Defaults to "
                             f"{STOCK_OUT}")
    parser.add_argument("--patch-out", default=PATCH_OUT, metavar="DIR",
                        help=f"Where the patched run writes. Defaults to "
                             f"{PATCH_OUT}")
    parser.add_argument("--fetch-limit", type=int,
                        default=STOCK_FETCH_LIMIT, metavar="N",
                        help="fetch1FetchLimit for the patched run "
                             f"(default {STOCK_FETCH_LIMIT}, the stock value)")
    parser.add_argument("--fetch2-buffer", type=int,
                        default=STOCK_FETCH2_BUFFER, metavar="N",
                        help="fetch2InputBufferSize for the patched run "
                             f"(default {STOCK_FETCH2_BUFFER}, the stock "
                             f"value)")
    parser.add_argument("-j", "--jobs", type=int, default=4, metavar="N",
                        help="Benchmarks at a time (default 4)")
    parser.add_argument("-n", "--dry-run", action="store_true",
                        help="Print the commands without running them")
    args = parser.parse_args()

    if args.compare:
        left, right = args.compare
        for path in (left, right):
            if not os.path.isfile(path):
                print(f"[ERROR] No such metrics file: {path}")
                return 2
        stock, patched = parse_metrics(left), parse_metrics(right)
        return summarise(stock, patched, compare(stock, patched))

    args.batch = find_batch()
    if args.batch is None:
        print(f"[ERROR] No {BATCH} beside this script or in the working "
              f"directory. Run it from the gem5 root, inside the container.")
        return 2

    print(f"[INFO] Stock build, {STOCK_CONFIG}")
    if run(stock_command(args), args.dry_run) != 0 and not args.dry_run:
        print("[ERROR] The stock run failed, so there is nothing to compare.")
        return 1
    print(f"\n[INFO] Patched build, {PATCH_CONFIG} with every switch off")
    if run(patch_command(args), args.dry_run) != 0 and not args.dry_run:
        print("[ERROR] The patched run failed, so there is nothing to "
              "compare.")
        return 1
    if args.dry_run:
        print("\n[INFO] Dry run, so nothing was measured and nothing "
              "compared.")
        return 0

    left, right = metrics_file(args.stock_out), metrics_file(args.patch_out)
    for path, where in ((left, args.stock_out), (right, args.patch_out)):
        if path is None:
            print(f"[ERROR] No metrics file in {where}. The run gathered "
                  f"none, so check its log.")
            return 1
    print(f"\n[INFO] Comparing {left} with {right}")
    stock, patched = parse_metrics(left), parse_metrics(right)
    return summarise(stock, patched, compare(stock, patched))


if __name__ == "__main__":
    sys.exit(main())
