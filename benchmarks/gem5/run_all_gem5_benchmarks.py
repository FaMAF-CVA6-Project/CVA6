#!/usr/bin/env python3
"""
Run every benchmark in a folder through run_gem5.py.

Collects the C and assembly programs in a directory, drops the templates,
and runs them one by one against the same gem5 configuration, printing a
pass/fail summary at the end. Each program is handed to run_gem5.py
untouched, so its metrics table and its debug trace are exactly what a
single run would produce.

Run this from the gem5 root: run_gem5.py takes the current directory as the
gem5 root, and the default test folder is relative to it.
"""
import argparse
import concurrent.futures
import os
import shutil
import subprocess
import sys
import threading
import time

# ==============================================================================
# CONFIGURATION
# ==============================================================================
# Default folder, relative to the gem5 root.
DEFAULT_TESTS_DIR = "benchmarks"

# The driver this script delegates to, looked up next to it and then in cwd.
RUNNER_NAME = "run_gem5.py"

# What run_gem5.py needs from the gem5 root, used to check where we are.
GEM5_BIN = os.path.join("build", "RISCV", "gem5.opt")

# Where run_gem5.py has gem5 write, cleared after each collected run.
GEM5_OUT_DIR = "m5out"

# Where the batch gathers what it keeps, one folder for the whole run.
DEFAULT_OUT_DIR = "batch_results"

# Tests to run at a time. Deliberately below the core count: each run holds
# a gem5 process and writes a trace, so memory and disk bind before cores do.
DEFAULT_JOBS = min(4, os.cpu_count() or 1)

# Recognised test extensions, matching run_gem5.py. Case-sensitive: .S is
# assembly and .s is too, but .c is the only C spelling accepted.
SOURCE_EXTS = {".c", ".S", ".s", ".asm", ".sx"}

# A file whose name contains this is a starting point, not a benchmark.
TEMPLATE_MARKER = "template"

# What run_gem5.py writes above its metrics table, and where the batch gathers
# every one of those tables once the runs are done.
METRICS_MARKER = "RESULTS TABLE"
METRICS_FILE = "metrics.txt"

SEP = "=" * 70


def find_runner():
    """Locate run_gem5.py next to this script, then in the cwd."""
    here = os.path.dirname(os.path.abspath(__file__))
    for candidate in (os.path.join(here, RUNNER_NAME),
                      os.path.abspath(RUNNER_NAME)):
        if os.path.isfile(candidate):
            return candidate
    print(f"[ERROR] {RUNNER_NAME} not found next to this script or in the "
          f"current directory.")
    sys.exit(2)


def split_own_args(argv):
    """Split the command line into this script's arguments and the ones meant
    for the configuration.

    Everything after a '--' is the configuration's, verbatim. That is the
    unambiguous form, and the one to use for a flag that takes a value or that
    shares a name with one of ours."""
    if "--" in argv:
        cut = argv.index("--")
        return argv[:cut], argv[cut + 1:]
    return argv, []


def discover(folder, recursive):
    """Return (tests, templates), both sorted lists of paths."""
    found = []
    if recursive:
        for root, _, names in os.walk(folder):
            found.extend(os.path.join(root, n) for n in names)
    else:
        found.extend(os.path.join(folder, n) for n in os.listdir(folder)
                     if os.path.isfile(os.path.join(folder, n)))

    sources = sorted(p for p in found
                     if os.path.splitext(p)[1] in SOURCE_EXTS)

    tests, templates = [], []
    for path in sources:
        stem = os.path.splitext(os.path.basename(path))[0]
        if TEMPLATE_MARKER in stem.lower():
            templates.append(path)
        else:
            tests.append(path)
    return tests, templates


def warn_duplicates(tests, folder):
    """Warn about tests sharing a name, since their outputs collide."""
    by_stem = {}
    for path in tests:
        stem = os.path.splitext(os.path.basename(path))[0]
        by_stem.setdefault(stem, []).append(path)

    duplicates = {s: p for s, p in by_stem.items() if len(p) > 1}
    if not duplicates:
        return

    print(f"[WARN] {len(duplicates)} test name(s) appear more than once. "
          f"Outputs are named after the program, so these runs overwrite "
          f"each other's binary and their collected trace, .list, "
          f"_report.txt and _stats.txt:")
    for stem in sorted(duplicates):
        print(f"[WARN]   '{stem}':")
        for path in duplicates[stem]:
            print(f"[WARN]     {os.path.relpath(path, folder)}")
    print("[WARN] They will all be run. Keep the last one's results only, or "
          "rename them.\n")


def driver_results_dir(runner):
    """The run_results/ folder run_gem5.py copies its keepers into."""
    return os.path.join(os.path.dirname(os.path.abspath(runner)),
                        "run_results")


def job_dirs(runner, label):
    """The private folders one run works in.

    Each job gets its own, so concurrent runs cannot overwrite each other's
    stats.txt, trace or binary."""
    return (os.path.join(GEM5_OUT_DIR, label),
            os.path.join(driver_results_dir(runner), label))


def collect(job_results, out_dir, want_trace):
    """Move a finished run's four files into the batch's out folder."""
    collected = []
    try:
        produced = sorted(os.listdir(job_results))
    except OSError:
        produced = []

    for name in produced:
        if "_trace." in name and not want_trace:
            continue
        try:
            shutil.move(os.path.join(job_results, name),
                        os.path.join(out_dir, name))
            collected.append(name)
        except OSError as e:
            print(f"[WARN] Could not collect {name}: {e}")

    if not collected:
        print(f"[WARN] Nothing to collect from {job_results}")
    return collected


def discard_run(job_gem5_out, job_results):
    """Delete a run's working folders, once it has been collected.

    A debug trace runs to hundreds of megabytes and one is produced per run,
    so keeping them would cost far more disk than the results are worth. Only
    this run's folders go, so a failed run's output survives the batch."""
    for path in (job_gem5_out, job_results):
        shutil.rmtree(path, ignore_errors=True)


def prune_empty(path):
    """Remove a folder the batch has emptied, leaving anything else alone.

    Deliberately not a recursive delete: a plain run_gem5.py run writes
    straight into these folders, and that output is not the batch's to
    destroy."""
    try:
        if os.path.isdir(path) and not os.listdir(path):
            os.rmdir(path)
    except OSError:
        pass


def extract_metrics(report_path):
    """The metrics section of a _report.txt, or None if it holds none.

    A _report.txt is the measured region of the disassembly followed by the
    metrics table, so everything from the rule above the table's title to the
    end of the file is the section wanted here."""
    try:
        with open(report_path) as f:
            lines = f.read().splitlines()
    except OSError as e:
        print(f"[WARN] Could not read {report_path}: {e}")
        return None

    for i, line in enumerate(lines):
        if line.startswith(METRICS_MARKER):
            # Take the rule above the title too, so the block arrives boxed.
            start = i - 1 if i and set(lines[i - 1]) == {"="} else i
            return "\n".join(lines[start:]).rstrip()

    return None


def write_metrics_file(out_dir, entries, info):
    """Gather every run's metrics table into one metrics.txt.

    entries is [(label, report file)] in the order the runs were listed, so the
    file reads in the same order as the summary above it. A run whose table is
    missing is named rather than skipped silently."""
    blocks, missing = [], []
    for label, report_path in entries:
        block = extract_metrics(report_path)
        if block is None:
            missing.append(label)
            continue
        blocks.append(f">>> {label}\n{block}")

    if missing:
        print(f"[WARN] No metrics table for: {', '.join(missing)}")
    if not blocks:
        print(f"[WARN] No metrics tables found, so no {METRICS_FILE} written")
        return None

    path = os.path.join(out_dir, METRICS_FILE)
    try:
        with open(path, "w") as f:
            f.write(f"{SEP}\nALL METRICS\n{SEP}\n")
            for line in info:
                f.write(line + "\n")
            f.write(f"{SEP}\n\n")
            f.write("\n\n".join(blocks) + "\n")
    except OSError as e:
        print(f"[WARN] Could not write {path}: {e}")
        return None

    print(f"[INFO] {len(blocks)} metrics table(s) gathered in {path}")
    return path


def format_duration(seconds):
    minutes, secs = divmod(int(seconds), 60)
    if minutes:
        return f"{minutes}m{secs:02d}s"
    return f"{seconds:.1f}s"


def print_summary(results, total_elapsed):
    print("\n" + SEP)
    print("BENCHMARK SUMMARY")
    print(SEP)
    print(f"{'TEST':<35} | {'STATUS':>10} | {'TIME':>10}")
    print(SEP)

    for name, code, elapsed in results:
        status = "OK" if code == 0 else f"FAILED ({code})"
        print(f"{name[:35]:<35} | {status:>10} | "
              f"{format_duration(elapsed):>10}")

    passed = sum(1 for _, code, _ in results if code == 0)
    failed = len(results) - passed

    print(SEP)
    print(f"{len(results)} run, {passed} passed, {failed} failed, "
          f"total {format_duration(total_elapsed)}")
    print(SEP + "\n")

    if failed:
        print("[WARN] Failed tests: " +
              ", ".join(n for n, c, _ in results if c != 0))
    return failed


def main():
    parser = argparse.ArgumentParser(
        description="Run every benchmark in a folder through run_gem5.py.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"Templates (any file with '{TEMPLATE_MARKER}' in its name) "
               f"are skipped.\nWith no folder given, {DEFAULT_TESTS_DIR}/ is "
               f"used, relative to the gem5 root.\n"
               f"\n"
               f"Any flag this script does not define is passed on to the "
               f"configuration,\nthrough run_gem5.py and the same for every "
               f"test in the batch:\n"
               f"\n"
               f"  run_all_gem5_benchmarks.py gem5_config_CVA6.py "
               f"--no-fill-phase\n"
               f"\n"
               f"Put them after a '--' when a flag takes a value or shares a "
               f"name with\none of ours:\n"
               f"\n"
               f"  run_all_gem5_benchmarks.py gem5_config_CVA6.py -- "
               f"--no-fill-phase")
    parser.add_argument("config_file",
                        help="gem5 configuration script (.py) passed to "
                             "run_gem5.py")
    parser.add_argument("folder", nargs="?", default=DEFAULT_TESTS_DIR,
                        help=f"Folder holding the tests. "
                             f"Defaults to {DEFAULT_TESTS_DIR}/")
    parser.add_argument("-j", "--jobs", type=int, default=DEFAULT_JOBS,
                        help=f"How many tests to run at a time. Defaults to "
                             f"{DEFAULT_JOBS} here. gem5 is single-threaded, "
                             f"so this scales with cores until memory or "
                             f"disk bandwidth binds. 1 runs them one by one "
                             f"and streams the output live")
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR,
                        help=f"Where to gather the results. Defaults to "
                             f"{DEFAULT_OUT_DIR}/")
    parser.add_argument("--no-trace", action="store_true",
                        help="Forwarded to run_gem5.py: no debug trace, "
                             "metrics only")
    parser.add_argument("-r", "--recursive", action="store_true",
                        help="Also pick up tests in subfolders")
    parser.add_argument("--dry-run", action="store_true",
                        help="List what would run, and the name clashes, "
                             "without running anything")
    own_argv, after_separator = split_own_args(sys.argv[1:])
    args, unrecognised = parser.parse_known_args(own_argv)

    # A bare word among the leftovers is a mistyped option far more often than
    # it is something the configuration wants: a flag that takes a value has to
    # go after the '--' anyway. Refuse it rather than run the whole batch with
    # it, since every run would fail the same way inside gem5.
    stray = [a for a in unrecognised if not a.startswith("-")]
    if stray:
        print(f"[ERROR] Unrecognised argument(s): {' '.join(stray)}. "
              f"Flags for the configuration are passed straight through; "
              f"anything that takes a value goes after a '--'.")
        sys.exit(2)
    config_args = unrecognised + after_separator

    # Keep our own output interleaved correctly with each run_gem5.py run.
    # Redirected to a file, stdout would otherwise be block-buffered here
    # while the children write straight through, scrambling the log.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)

    if not os.path.isfile(args.config_file):
        print(f"[ERROR] The configuration file '{args.config_file}' does not "
              f"exist")
        sys.exit(2)

    # run_gem5.py resolves the gem5 root from the cwd, so this has to be run
    # from there. Say so now instead of failing later on a missing binary.
    if not os.path.isfile(GEM5_BIN):
        print(f"[ERROR] {GEM5_BIN} not found in {os.getcwd()}. "
              f"Run this from the gem5 root.")
        sys.exit(2)

    folder = os.path.abspath(args.folder)
    if not os.path.isdir(folder):
        print(f"[ERROR] The folder {folder} does not exist")
        sys.exit(2)

    runner = find_runner()
    tests, templates = discover(folder, args.recursive)

    print(SEP)
    print("BENCHMARK BATCH")
    print(SEP)
    print(f"Folder   : {folder}")
    print(f"Config   : {args.config_file}")
    print(f"Runner   : {runner}")
    print(f"Out dir  : {os.path.abspath(args.out_dir)}")
    print(f"Jobs     : {max(1, args.jobs)}")
    print(f"Tracing  : "
          f"{'disabled (--no-trace)' if args.no_trace else 'enabled'}")
    if config_args:
        print(f"Cfg flags: {' '.join(config_args)}")
    print(SEP + "\n")

    if templates:
        print(f"[INFO] Skipping {len(templates)} template(s): " +
              ", ".join(os.path.basename(p) for p in templates))

    if not tests:
        print(f"[ERROR] No tests found in {folder}. Looked for: " +
              ", ".join(sorted(SOURCE_EXTS)))
        sys.exit(2)

    print(f"[INFO] {len(tests)} test(s) to run:")
    for path in tests:
        print(f"[INFO]   {os.path.relpath(path, folder)}")
    print()

    warn_duplicates(tests, folder)

    if args.dry_run:
        print("[INFO] Dry run, nothing executed.")
        return 0

    out_dir = os.path.abspath(args.out_dir)
    os.makedirs(out_dir, exist_ok=True)
    jobs = max(1, args.jobs)

    # One lock around the reporting, so a finished run's output arrives as one
    # block instead of interleaved with another's.
    report_lock = threading.Lock()
    results = []
    batch_start = time.time()

    def run_one(index, path):
        name = os.path.basename(path)
        test_name = os.path.splitext(name)[0]
        job_gem5_out, job_results = job_dirs(runner, test_name)
        # Anything left from an earlier batch would otherwise be collected.
        discard_run(job_gem5_out, job_results)

        cmd = [sys.executable, runner, args.config_file, path,
               "--gem5-out-dir", job_gem5_out,
               "--results-dir", job_results]
        if args.no_trace:
            cmd.append("--no-trace")
        # After a '--', so run_gem5.py hands them to the configuration whatever
        # they are named.
        if config_args:
            cmd.extend(["--"] + config_args)

        start = time.time()
        if jobs == 1:
            # Serial: let the run print as it goes.
            print("\n" + SEP)
            print(f"[{index}/{len(tests)}] {name}")
            print(SEP + "\n")
            code = subprocess.run(cmd).returncode
            output = None
        else:
            done = subprocess.run(cmd, capture_output=True, text=True)
            code, output = done.returncode, done.stdout + done.stderr
        elapsed = time.time() - start

        with report_lock:
            if output is not None:
                print("\n" + SEP)
                print(f"[{index}/{len(tests)}] {name}")
                print(SEP + "\n")
                print(output, end="" if output.endswith("\n") else "\n")
            if code != 0:
                # Leave this one where gem5 put it: its output is what there
                # is to debug with.
                print(f"[WARN] '{name}' failed with exit code {code}. Its "
                      f"output is left in {job_gem5_out}, including the whole "
                      f"of gem5's stdout and stderr as "
                      f"{os.path.splitext(name)[0]}_error.log. Continuing.")
            else:
                collected = collect(job_results, out_dir, not args.no_trace)
                if collected:
                    print(f"[INFO] Collected {len(collected)} file(s) into "
                          f"{out_dir}")
                discard_run(job_gem5_out, job_results)
            results.append((index, name, code, elapsed))

    try:
        if jobs == 1:
            for index, path in enumerate(tests, 1):
                run_one(index, path)
        else:
            print(f"[INFO] Running {jobs} tests at a time.\n")
            with concurrent.futures.ThreadPoolExecutor(jobs) as pool:
                for future in [pool.submit(run_one, i, p)
                               for i, p in enumerate(tests, 1)]:
                    future.result()
    except KeyboardInterrupt:
        print("\n[WARN] Interrupted. Stopping the batch.")

    # Report in the order the tests were listed, not the order they finished.
    ordered = [(n, c, e) for _, n, c, e in sorted(results)]
    failed = print_summary(ordered, time.time() - batch_start)

    # Only a run that passed left a table behind to gather.
    write_metrics_file(
        out_dir,
        [(name, os.path.join(out_dir,
                             f"{os.path.splitext(name)[0]}_report.txt"))
         for name, code, _ in ordered if code == 0],
        [f"Folder   : {folder}",
         f"Config   : {args.config_file}",
         f"Cfg flags: {' '.join(config_args) if config_args else '(none)'}",
         f"Runs     : {len(ordered)}, {len(ordered) - failed} passed"])

    print(f"[INFO] Results in {out_dir}")
    if failed:
        print(f"[INFO] The failed test(s) left their output under "
              f"{os.path.abspath(GEM5_OUT_DIR)}")
    # Whatever the batch emptied goes; anything a plain run_gem5.py run left
    # in there stays.
    prune_empty(driver_results_dir(runner))
    prune_empty(GEM5_OUT_DIR)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
