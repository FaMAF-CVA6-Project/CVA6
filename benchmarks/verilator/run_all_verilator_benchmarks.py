#!/usr/bin/env python3
"""
Run every benchmark in a folder through run_verilator.py.

Collects the C and assembly tests in a directory, drops the templates, and
runs them one by one against the same target, printing a pass/fail summary
at the end. Each test is handed to run_verilator.py untouched, so its
metrics table and its VCD are exactly what a single run would produce.

Only the first test pays for the Verilator build: the model does not depend
on the test, and the target and the trace setting are fixed for the whole
batch, so the rest run with run_verilator.py's --keep-build. Pass
--rebuild-each to go back to rebuilding the core before every test.
"""
import argparse
import os
import subprocess
import sys
import time

# ==============================================================================
# CONFIGURATION
# ==============================================================================
# Default folder, as laid out inside the manuel313/cva6 image.
DEFAULT_TESTS_DIR = "/cva6/verif/tests/custom/FaMAF"

# The driver this script delegates to, looked up next to it and then in cwd.
RUNNER_NAME = "run_verilator.py"

# Recognised test extensions, matching run_verilator.py. Case-sensitive: .S
# is assembly and .s is too, but .c is the only C spelling accepted.
SOURCE_EXTS = {".c", ".S", ".s", ".asm", ".sx"}

# A file whose name contains this is a starting point, not a benchmark.
TEMPLATE_MARKER = "template"

SEP = "=" * 70


def find_runner():
    """Locate run_verilator.py next to this script, then in the cwd."""
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
          f"run_verilator.py names its outputs after the test, so these runs "
          f"overwrite each other's log, binary, .list and _clean.txt:")
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
        description="Run every benchmark in a folder through "
                    "run_verilator.py.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"Templates (any file with '{TEMPLATE_MARKER}' in its name) "
               f"are skipped.\nWith no folder given, "
               f"{DEFAULT_TESTS_DIR} is used.")
    parser.add_argument("target",
                        help="Architecture target passed to run_verilator.py "
                             "(e.g. cv64a6_imafdc_sv39_hpdcache)")
    parser.add_argument("folder", nargs="?", default=DEFAULT_TESTS_DIR,
                        help=f"Folder holding the tests. "
                             f"Defaults to {DEFAULT_TESTS_DIR}")
    parser.add_argument("--no-vcd", action="store_true",
                        help="Forwarded to run_verilator.py: no .vcd trace, "
                             "metrics only")
    parser.add_argument("--rebuild-each", action="store_true",
                        help="Rebuild the Verilated core before every test. "
                             "By default only the first test builds it and "
                             "the rest reuse it with --keep-build, which is "
                             "safe here because the target and the trace "
                             "setting are the same for the whole batch")
    parser.add_argument("-r", "--recursive", action="store_true",
                        help="Also pick up tests in subfolders")
    parser.add_argument("--dry-run", action="store_true",
                        help="List what would run, and the name clashes, "
                             "without running anything")
    args = parser.parse_args()

    # Keep our own output interleaved correctly with each run_verilator.py
    # run. Redirected to a file, stdout would otherwise be block-buffered
    # here while the children write straight through, scrambling the log.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)

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
    print(f"Target   : {args.target}")
    print(f"Runner   : {runner}")
    print(f"Tracing  : {'disabled (--no-vcd)' if args.no_vcd else 'enabled'}")
    print(f"Build    : "
          f"{'rebuilt before every test' if args.rebuild_each else 'built once, then reused'}")
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

        cmd = [sys.executable, runner, args.target, path]
        if args.no_vcd:
            cmd.append("--no-vcd")
        # The Verilated model does not depend on the test, and the target and
        # the trace setting are fixed for the batch, so only the first test
        # pays for the build.
        if index > 1 and not args.rebuild_each:
            cmd.append("--keep-build")

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
