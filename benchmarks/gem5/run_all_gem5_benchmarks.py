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
          f"run_gem5.py names its outputs after the program, so these runs "
          f"overwrite each other's binary and their run_results/ trace, .list "
          f"and _clean.txt:")
    for stem in sorted(duplicates):
        print(f"[WARN]   '{stem}':")
        for path in duplicates[stem]:
            print(f"[WARN]     {os.path.relpath(path, folder)}")
    print("[WARN] They will all be run. Keep the last one's results only, or "
          "rename them.\n")


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

    results = []
    batch_start = time.time()

    for index, path in enumerate(tests, 1):
        name = os.path.basename(path)
        print("\n" + SEP)
        print(f"[{index}/{len(tests)}] {name}")
        print(SEP + "\n")

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
            print(f"\n[WARN] '{name}' failed with exit code {code}. "
                  f"Continuing with the rest.")
        results.append((name, code, elapsed))

    failed = print_summary(results, time.time() - batch_start)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
