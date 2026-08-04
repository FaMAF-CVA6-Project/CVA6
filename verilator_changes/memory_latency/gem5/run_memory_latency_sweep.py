#!/usr/bin/env python3
"""
Run the CVA6 memory latency sweep.

Reads the MEM_POINTS table out of gem5_config_memory_latency.py and, for each
point, sets MEM to it and runs the benchmarks against that main-memory
latency. The core is identical at every point, only the latency moves.

Each point is paired with a Verilator build carrying axi_lat_delayer_intf at
the stated MemLatencyCycles, and the plan prints that pairing, since the
results are only meaningful next to the RTL run they are being compared with.

The table names no workloads, so every point runs DEFAULT_ALL_TESTS below,
the same benchmark set the CVA6 calibration sweep uses. Annotating a row as

    #     2  140ns   MemLatencyCycles = 5   calibrated   workload: daxpy

restricts that point to those workloads.

Outputs are collected as <test>_trace.mem<N>.txt, <test>_clean.mem<N>.txt and
<test>.mem<N>.list, so one point's results never overwrite another's.

Run this from the gem5 root, like run_gem5.py. The configuration file is
restored when the sweep ends, fails or is interrupted.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import time

# ==============================================================================
# CONFIGURATION
# ==============================================================================
DEFAULT_CONFIG = "gem5_config_memory_latency.py"
DEFAULT_TESTS_DIR = "programs"
DEFAULT_OUT_DIR = "mem_tests_results"

RUNNER_NAME = "run_gem5.py"

# What run_gem5.py needs from the gem5 root, used to check where we are.
GEM5_BIN = os.path.join("build", "RISCV", "gem5.opt")

# Where run_gem5.py has gem5 write, cleared after each collected run.
GEM5_OUT_DIR = "m5out"

# Workloads to use for 'all', since this table annotates none. The same set
# the CVA6 calibration sweep runs. Override at the command line with --tests.
DEFAULT_ALL_TESTS = [
    "atomic_fence",
    "basic_test",
    "branch_full_test",
    "btb_pressure",
    "daxpy",
    "fetch2_probe",
    "fp_addmul",
    "fp_divsqrt",
    "full_test",
    "int_div",
    "matmul_small",
    "store_fwd",
]

# Extensions tried when turning a workload name into a file, in this order.
EXT_PRIORITY = [".c", ".S", ".s", ".asm", ".sx"]

# '    2: ("D5 calibrated",  "140ns", 5),' in the MEM_POINTS table. These ids
# are authoritative: the comment table only annotates them.
ENTRY_RE = re.compile(
    r'^\s*(\d+):\s*\(\s*"([^"]*)"\s*,\s*"([^"]*)"\s*,\s*(\d+)\s*\)', re.M)
# Fallback if the tuple is reformatted: ids and names only.
ENTRY_LOOSE_RE = re.compile(r'^\s*(\d+):\s*\(\s*"([^"]*)"', re.M)

# '#     2  140ns         MemLatencyCycles = 5      calibrated'
ROW_RE = re.compile(r'^#\s+(\d+)\s+(\S.*)$')
CONTINUATION_RE = re.compile(r'^#\s{4,}(\S.*)$')

# 'MEM = 1'. Written so it cannot match the 'MEM_POINTS = {' table.
SELECTOR_RE = re.compile(r'^(MEM[ \t]*=[ \t]*)(\d+)([ \t]*(?:#.*)?)$', re.M)

SEP = "=" * 70


def find_beside_script(name, what, extra=()):
    """Locate a file next to this script, then in the cwd, then anywhere in
    extra."""
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [os.path.join(here, name), os.path.abspath(name)]
    candidates += [os.path.join(here, p, name) for p in extra]
    for candidate in candidates:
        if os.path.isfile(candidate):
            return os.path.abspath(candidate)
    print(f"[ERROR] {what} ({name}) not found next to this script or in the "
          f"current directory.")
    sys.exit(2)


def parse_table(text):
    """Parse MEM_POINTS into {id: (description, latency, rtl_cycles,
    workloads)}.

    Ids, names, latencies and the paired RTL delay come from the table itself,
    workloads from the comment block above it, whose rows may wrap onto
    continuation lines."""
    entries = {int(n): (name, latency, int(cycles))
               for n, name, latency, cycles in ENTRY_RE.findall(text)}
    if not entries:
        # The tuple shape changed, fall back to ids and names.
        entries = {int(n): (name, "", None)
                   for n, name in ENTRY_LOOSE_RE.findall(text)}
    if not entries:
        return {}

    # Accumulate each comment row, including its continuation lines.
    comments = {}
    current = None
    for line in text.splitlines():
        row = ROW_RE.match(line)
        if row:
            current = int(row.group(1))
            comments[current] = row.group(2).strip()
            continue
        continuation = CONTINUATION_RE.match(line)
        if continuation and current is not None:
            comments[current] += " " + continuation.group(1).strip()
            continue
        if not line.startswith("#"):
            current = None

    table = {}
    for point_id, (name, latency, cycles) in entries.items():
        comment = comments.get(point_id, "")
        workloads = []
        if "workload:" in comment:
            tail = comment.split("workload:", 1)[1]
            tail = re.sub(r"\(.*?\)", "", tail)
            workloads = [w.strip() for w in tail.split(",") if w.strip()]
        table[point_id] = (name, latency, cycles, workloads)
    return table


def resolve_all(table):
    """The 'all' workload set: the benchmark set.

    Annotating one point must not change what the unannotated points run, so
    DEFAULT_ALL_TESTS wins whenever there is one. Only with it emptied does
    'all' become the union of the workloads the table names."""
    if DEFAULT_ALL_TESTS:
        return list(DEFAULT_ALL_TESTS)

    named = []
    for _, _, _, workloads in table.values():
        for workload in workloads:
            if workload.lower() != "all" and workload not in named:
                named.append(workload)
    return sorted(named)


def suggest(name, tests_dir):
    """Files that look close to a workload name that did not resolve."""
    try:
        entries = sorted(os.listdir(tests_dir))
    except OSError:
        return []
    return [e for e in entries
            if os.path.splitext(e)[1] in EXT_PRIORITY
            and name.lower() in os.path.splitext(e)[0].lower()]


def resolve_test_file(name, tests_dir):
    """Turn a workload name into a path, trying the known extensions."""
    matches = [os.path.join(tests_dir, name + ext) for ext in EXT_PRIORITY
               if os.path.isfile(os.path.join(tests_dir, name + ext))]
    if not matches:
        return None
    if len(matches) > 1:
        print(f"[WARN] '{name}' matches more than one file: " +
              ", ".join(os.path.basename(m) for m in matches) +
              f". Using {os.path.basename(matches[0])}.")
    return matches[0]


def parse_point_selection(spec, table):
    """Parse '1,4-6' into a sorted list of sweep point ids."""
    if not spec:
        return sorted(table)

    selected = set()
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            low, _, high = chunk.partition("-")
            try:
                selected.update(range(int(low), int(high) + 1))
            except ValueError:
                print(f"[ERROR] Bad sweep point range: '{chunk}'")
                sys.exit(2)
        else:
            try:
                selected.add(int(chunk))
            except ValueError:
                print(f"[ERROR] Bad sweep point id: '{chunk}'")
                sys.exit(2)

    unknown = sorted(selected - set(table))
    if unknown:
        print(f"[ERROR] No such sweep point(s): "
              f"{', '.join(str(u) for u in unknown)}. "
              f"The table has {min(table)}-{max(table)}.")
        sys.exit(2)
    return sorted(selected)


def build_plan(table, point_ids, tests_dir, override_tests):
    """Build [(point_id, description, latency, rtl_cycles, [test paths])],
    warning about workloads with no matching file."""
    all_tests = override_tests if override_tests else resolve_all(table)
    plan = []
    missing = []

    for point_id in point_ids:
        description, latency, cycles, workloads = table[point_id]

        if override_tests:
            names = list(override_tests)
        elif not workloads or any(w.lower() == "all" for w in workloads):
            names = list(all_tests)
        else:
            names = list(workloads)

        paths = []
        for name in names:
            path = resolve_test_file(name, tests_dir)
            if path:
                paths.append(path)
            elif name not in missing:
                missing.append(name)
        plan.append((point_id, description, latency, cycles, paths))

    for name in missing:
        hints = suggest(name, tests_dir)
        print(f"[WARN] No file in {tests_dir} for the workload '{name}' "
              f"(looked for {name} plus {', '.join(EXT_PRIORITY)})." +
              (f" Did you mean {' or '.join(hints)}?" if hints else ""))

    # A point left with nothing to run would otherwise be skipped in silence,
    # which reads as 'swept' when it was not.
    empty = [point_id for point_id, _, _, _, paths in plan if not paths]
    if empty:
        print(f"[WARN] {len(empty)} sweep point(s) have no runnable workload "
              f"and will be skipped: " +
              ", ".join(f"mem{p}" for p in empty))
    if missing or empty:
        print()
    return plan


def select_point(text, point_id, config_path):
    """Write the configuration file with MEM set to point_id."""
    new_text, count = SELECTOR_RE.subn(
        lambda m: f"{m.group(1)}{point_id}{m.group(3)}", text, count=1)
    if count != 1:
        print(f"[ERROR] No 'MEM = <n>' line found in {config_path}, so the "
              f"sweep point cannot be selected.")
        sys.exit(2)
    with open(config_path, "w") as f:
        f.write(new_text)


def driver_results_dir(runner):
    """The run_results/ folder run_gem5.py copies its keepers into."""
    return os.path.join(os.path.dirname(os.path.abspath(runner)), "run_results")


def output_paths(results_dir, test_name):
    """The three files run_gem5.py leaves in run_results/ for this test."""
    return {
        "trace": os.path.join(results_dir, f"{test_name}_trace.txt"),
        "clean": os.path.join(results_dir, f"{test_name}_clean.txt"),
        "list": os.path.join(results_dir, f"{test_name}.list"),
    }


def discard_run(results_dir, test_name):
    """Delete what this run left behind, once it has been collected.

    A debug trace runs to hundreds of megabytes and one is produced per run,
    so keeping them would cost far more disk than the results are worth. Only
    this test's files are removed, so a failed run's output survives the rest
    of the batch."""
    if os.path.isdir(results_dir):
        shutil.rmtree(results_dir, ignore_errors=True)
    for name in (f"{test_name}_trace.txt", f"{test_name}_clean.txt",
                 f"{test_name}.list"):
        path = os.path.join(GEM5_OUT_DIR, name)
        if os.path.isfile(path):
            try:
                os.remove(path)
            except OSError:
                pass


def discard_gem5_out():
    """Remove gem5's output folder, once nothing in it is worth keeping."""
    if os.path.isdir(GEM5_OUT_DIR):
        shutil.rmtree(GEM5_OUT_DIR, ignore_errors=True)


def collect(results_dir, test_name, point_id, out_dir, want_trace):
    """Move this run's three files out under their .mem<N> names."""
    produced = output_paths(results_dir, test_name)
    wanted = {
        "trace": f"{test_name}_trace.mem{point_id}.txt",
        "clean": f"{test_name}_clean.mem{point_id}.txt",
        "list": f"{test_name}.mem{point_id}.list",
    }

    collected = 0
    for key, source in produced.items():
        if key == "trace" and not want_trace:
            continue
        if not os.path.isfile(source):
            print(f"[WARN] Expected output missing: {source}")
            continue
        try:
            shutil.move(source, os.path.join(out_dir, wanted[key]))
            collected += 1
        except OSError as e:
            print(f"[WARN] Could not collect {source}: {e}")

    if collected:
        print(f"[INFO] Collected {collected} file(s) into {out_dir} as "
              f"{test_name}*.mem{point_id}.*")
    return collected


def clear_stale_outputs(results_dir, test_name):
    """Remove the previous run's files so nothing stale gets collected."""
    for path in output_paths(results_dir, test_name).values():
        if os.path.isfile(path):
            try:
                os.remove(path)
            except OSError:
                pass


def format_duration(seconds):
    minutes, secs = divmod(int(seconds), 60)
    if minutes:
        return f"{minutes}m{secs:02d}s"
    return f"{seconds:.1f}s"


def describe_point(description, latency, cycles):
    """One line naming the point and the Verilator build it pairs with."""
    label = f"{description} at {latency}" if latency else description
    if cycles is not None:
        label += f", compare against MemLatencyCycles = {cycles}"
    return label


def print_plan(plan, all_tests, source):
    print(f"[INFO] 'all' resolves to {len(all_tests)} workload(s), from "
          f"{source}: " +
          (", ".join(all_tests) if all_tests else "nothing") + "\n")
    total = 0
    for point_id, description, latency, cycles, paths in plan:
        names = [os.path.basename(p) for p in paths]
        total += len(paths)
        print(f"  mem{point_id:<4} {describe_point(description, latency, cycles)}")
        print(f"      {len(names)} test(s): " +
              (", ".join(names) if names else "none"))
    print(f"\n[INFO] {len(plan)} sweep point(s), {total} run(s) total.")
    return total


def print_summary(results, total_elapsed):
    print("\n" + SEP)
    print("SWEEP SUMMARY")
    print(SEP)
    print(f"{'POINT':>6} | {'TEST':<28} | {'STATUS':>10} | {'TIME':>9}")
    print(SEP)

    for point_id, name, code, elapsed in results:
        status = "OK" if code == 0 else f"FAILED ({code})"
        print(f"{('mem' + str(point_id)):>6} | {name[:28]:<28} | "
              f"{status:>10} | {format_duration(elapsed):>9}")

    passed = sum(1 for _, _, code, _ in results if code == 0)
    failed = len(results) - passed

    print(SEP)
    print(f"{len(results)} run, {passed} passed, {failed} failed, "
          f"total {format_duration(total_elapsed)}")
    print(SEP + "\n")

    if failed:
        print("[WARN] Failed: " + ", ".join(
            f"mem{p}/{n}" for p, n, code, _ in results if code != 0))
    return failed


def main():
    parser = argparse.ArgumentParser(
        description="Run the CVA6 memory latency sweep: each point of the "
                    "MEM_POINTS table, with the benchmarks.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"Always sweeps {DEFAULT_CONFIG}, which it is written for. A "
               f"point whose\nworkload is 'all' runs the benchmark set in "
               f"DEFAULT_ALL_TESTS.\nRun this from the gem5 root, like "
               f"run_gem5.py.")
    parser.add_argument("--config", default="",
                        help=f"Sweep a different configuration file. The "
                             f"sweep is written for {DEFAULT_CONFIG} and uses "
                             f"it unless this says otherwise, so only pass it "
                             f"for a copy or a variant of that file")
    parser.add_argument("--configs", default="",
                        help="Which sweep points to run, e.g. '1,4-6'. "
                             "Defaults to all of them")
    parser.add_argument("--tests-dir", default=DEFAULT_TESTS_DIR,
                        help=f"Folder holding the workloads. Defaults to "
                             f"{DEFAULT_TESTS_DIR}/")
    parser.add_argument("--tests", default="",
                        help="Comma-separated workloads to run for every "
                             "point, instead of the ones the table names")
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR,
                        help=f"Where to collect the results. Defaults to "
                             f"{DEFAULT_OUT_DIR}/")
    parser.add_argument("--no-trace", action="store_true",
                        help="Forwarded to run_gem5.py: no debug trace, "
                             "metrics only")
    parser.add_argument("--list", action="store_true",
                        help="Print the plan and exit, touching nothing")
    args = parser.parse_args()

    # Keep our output interleaved correctly with each run_gem5.py run.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)

    config_path = (os.path.abspath(args.config) if args.config
                   else find_beside_script(
                       DEFAULT_CONFIG, "Sweep config",
                       # Where the config lives in the repository.
                       extra=[os.path.join("..", "..", "verilator_changes",
                                           "memory_latency", "gem5")]))
    if not os.path.isfile(config_path):
        print(f"[ERROR] The configuration file '{config_path}' does not exist")
        sys.exit(2)

    with open(config_path) as f:
        config_text = f.read()

    table = parse_table(config_text)
    if not table:
        print(f"[ERROR] No MEM_POINTS table found in {config_path}. Expected "
              f"a 'MEM_POINTS = {{...}}' dict keyed by integer.")
        sys.exit(2)

    point_ids = parse_point_selection(args.configs, table)
    override_tests = [t.strip() for t in args.tests.split(",") if t.strip()]
    all_tests = override_tests if override_tests else resolve_all(table)

    print(SEP)
    print("CVA6 MEMORY LATENCY SWEEP")
    print(SEP)
    print(f"Config    : {config_path}")
    print(f"Tests dir : {os.path.abspath(args.tests_dir)}")
    print(f"Out dir   : {os.path.abspath(args.out_dir)}")
    print(f"Tracing   : "
          f"{'disabled (--no-trace)' if args.no_trace else 'enabled'}")
    print(SEP + "\n")

    if not os.path.isdir(args.tests_dir):
        print(f"[ERROR] The tests folder {args.tests_dir} does not exist")
        sys.exit(2)

    plan = build_plan(table, point_ids, args.tests_dir, override_tests)
    total_runs = print_plan(
        plan, all_tests,
        "--tests" if override_tests else
        "DEFAULT_ALL_TESTS" if DEFAULT_ALL_TESTS else "the table")

    if args.list:
        print("[INFO] Listing only, nothing run.")
        return 0
    if not total_runs:
        print("[ERROR] Nothing to run.")
        sys.exit(2)

    # run_gem5.py resolves the gem5 root from the cwd, so this has to be run
    # from there. Say so now instead of failing later on a missing binary.
    if not os.path.isfile(GEM5_BIN):
        print(f"[ERROR] {GEM5_BIN} not found in {os.getcwd()}. "
              f"Run this from the gem5 root.")
        sys.exit(2)

    runner = find_beside_script(RUNNER_NAME, "Runner")
    results_dir = driver_results_dir(runner)
    os.makedirs(args.out_dir, exist_ok=True)

    print(f"\n[INFO] Backed up {config_path}, restored when the sweep ends.")

    results = []
    sweep_start = time.time()

    try:
        for point_id, description, latency, cycles, paths in plan:
            if not paths:
                continue

            print("\n" + SEP)
            print(f"mem{point_id}: {describe_point(description, latency, cycles)}")
            print(SEP)
            select_point(config_text, point_id, config_path)
            print(f"[INFO] MEM = {point_id}\n")

            for index, path in enumerate(paths, 1):
                test_name = os.path.splitext(os.path.basename(path))[0]
                print("\n" + "-" * 70)
                print(f"[mem{point_id}] [{index}/{len(paths)}] "
                      f"{os.path.basename(path)}")
                print("-" * 70 + "\n")

                clear_stale_outputs(results_dir, test_name)

                cmd = [sys.executable, runner, config_path, path]
                if args.no_trace:
                    cmd.append("--no-trace")

                start = time.time()
                code = subprocess.run(cmd).returncode
                elapsed = time.time() - start

                if code != 0:
                    # Leave the outputs in place: they are what there is
                    # to debug with.
                    print(f"\n[WARN] '{test_name}' failed with exit code "
                          f"{code}. Continuing with the rest.")
                else:
                    collect(results_dir, test_name, point_id,
                            args.out_dir, not args.no_trace)
                    discard_run(results_dir, test_name)
                results.append((point_id, test_name, code, elapsed))

    except KeyboardInterrupt:
        print("\n[WARN] Interrupted. Stopping the sweep.")
    finally:
        with open(config_path, "w") as f:
            f.write(config_text)
        print(f"\n[INFO] Restored {config_path}")

    failed = print_summary(results, time.time() - sweep_start)
    print(f"[INFO] Results in {os.path.abspath(args.out_dir)}")
    if failed:
        print(f"[INFO] The failed run(s) left their output in "
              f"{os.path.abspath(GEM5_OUT_DIR)}")
    else:
        # Nothing in there is worth keeping now, so take the folder with it.
        discard_gem5_out()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
