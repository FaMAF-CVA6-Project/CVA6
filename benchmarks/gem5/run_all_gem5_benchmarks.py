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
import os
import shutil
import subprocess
import sys
import time

# ==============================================================================
# CONFIGURATION
# ==============================================================================
# Default folder, relative to the gem5 root.
DEFAULT_TESTS_DIR = "programs"

# The driver this script delegates to, looked up next to it and then in cwd.
RUNNER_NAME = "run_gem5.py"

# What run_gem5.py needs from the gem5 root, used to check where we are.
GEM5_BIN = os.path.join("build", "RISCV", "gem5.opt")

# Where run_gem5.py has gem5 write, cleared after each collected run.
GEM5_OUT_DIR = "m5out"

# Where the batch gathers what it keeps, one folder for the whole run.
DEFAULT_OUT_DIR = "batch_results"

# Recognised test extensions, matching run_gem5.py. Case-sensitive: .S is
# assembly and .s is too, but .c is the only C spelling accepted.
SOURCE_EXTS = {".c", ".S", ".s", ".asm", ".sx"}

# A file whose name contains this is a starting point, not a benchmark.
TEMPLATE_MARKER = "template"

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
          f"each other's binary and their collected trace, .list and "
          f"_clean.txt:")
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


def output_paths(results_dir, test_name):
    """The three files run_gem5.py leaves in run_results/ for this test."""
    return {
        "trace": os.path.join(results_dir, f"{test_name}_trace.txt"),
        "clean": os.path.join(results_dir, f"{test_name}_clean.txt"),
        "list": os.path.join(results_dir, f"{test_name}.list"),
    }


def collect(results_dir, test_name, out_dir, want_trace):
    """Move this run's three files into the batch's out folder."""
    collected = 0
    for key, source in output_paths(results_dir, test_name).items():
        if key == "trace" and not want_trace:
            continue
        if not os.path.isfile(source):
            print(f"[WARN] Expected output missing: {source}")
            continue
        try:
            shutil.move(source, os.path.join(out_dir,
                                             os.path.basename(source)))
            collected += 1
        except OSError as e:
            print(f"[WARN] Could not collect {source}: {e}")

    if collected:
        print(f"[INFO] Collected {collected} file(s) into {out_dir}")
    return collected


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
               f"used, relative to the gem5 root.")
    parser.add_argument("config_file",
                        help="gem5 configuration script (.py) passed to "
                             "run_gem5.py")
    parser.add_argument("folder", nargs="?", default=DEFAULT_TESTS_DIR,
                        help=f"Folder holding the tests. "
                             f"Defaults to {DEFAULT_TESTS_DIR}/")
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
    args = parser.parse_args()

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
    print(f"Tracing  : "
          f"{'disabled (--no-trace)' if args.no_trace else 'enabled'}")
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

    results_dir = driver_results_dir(runner)
    out_dir = os.path.abspath(args.out_dir)
    os.makedirs(out_dir, exist_ok=True)

    results = []
    batch_start = time.time()

    for index, path in enumerate(tests, 1):
        name = os.path.basename(path)
        test_name = os.path.splitext(name)[0]
        print("\n" + SEP)
        print(f"[{index}/{len(tests)}] {name}")
        print(SEP + "\n")

        clear_stale_outputs(results_dir, test_name)

        cmd = [sys.executable, runner, args.config_file, path]
        if args.no_trace:
            cmd.append("--no-trace")

        start = time.time()
        try:
            code = subprocess.run(cmd).returncode
        except KeyboardInterrupt:
            print(f"\n[WARN] Interrupted during '{name}'. "
                  f"Stopping the batch.")
            results.append((name, 130, time.time() - start))
            break
        elapsed = time.time() - start

        if code != 0:
            # Leave this one where gem5 put it: its output is what there is
            # to debug with.
            print(f"\n[WARN] '{name}' failed with exit code {code}. "
                  f"Its output is left in place. Continuing with the rest.")
        else:
            collect(results_dir, test_name, out_dir, not args.no_trace)
            discard_run(results_dir, test_name)
        results.append((name, code, elapsed))

    failed = print_summary(results, time.time() - batch_start)
    print(f"[INFO] Results in {out_dir}")
    if failed:
        print(f"[INFO] The failed test(s) left their output in "
              f"{os.path.abspath(GEM5_OUT_DIR)}")
    else:
        # Nothing in there is worth keeping now, so take the folder with it.
        discard_gem5_out()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
