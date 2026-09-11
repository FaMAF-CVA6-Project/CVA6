#!/usr/bin/env python3
"""Turn every trace in this checkout into a viewer JSON.

Two engines leave two kinds of trace. gem5 writes a debug trace that MinorFlow
reads, CVA6 writes a VCD that CVA6Flow reads, and each viewer owns its tracer.
This walks the fork, hands each trace to the right one, and then offers to run
each submodule's own batch script over its own repository.

    python3 scripts/create_all_CVA6_repo_jsons.py            # the whole checkout
    python3 scripts/create_all_CVA6_repo_jsons.py -j 8
    python3 scripts/create_all_CVA6_repo_jsons.py --force    # redo existing JSONs
    python3 scripts/create_all_CVA6_repo_jsons.py --dry-run  # list, convert nothing
    python3 scripts/create_all_CVA6_repo_jsons.py --no-strict  # degraded ok
    python3 scripts/create_all_CVA6_repo_jsons.py --no-submodules
"""
import argparse
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed


def repo_root():
    """The repository this script sits in, found by walking up to the nearest
    .git. The script lives in scripts/, so counting parents would be one more
    thing to fix the next time the tree moves."""
    here = os.path.dirname(os.path.abspath(__file__))
    path = here
    while True:
        if os.path.exists(os.path.join(path, ".git")):
            return path
        parent = os.path.dirname(path)
        if parent == path:
            return here
        path = parent


REPO_ROOT = repo_root()

DEFAULT_WORKERS = 4

# One entry per engine: what a trace of that kind looks like, which tracer
# reads it, and the submodule that owns that tracer. A trace is named after its
# test with '_trace' removed, which is the name the viewers and the sweeps use.
ENGINES = {
    "gem5": {
        # A sweep names its collected traces daxpy_trace.config1.txt, so the
        # mark is not a suffix and the two have to be tested separately.
        "ext": ".txt",
        "mark": "_trace",
        "tracer": "viewers/MinorFlow/MinorFlow_tracer.py",
        "submodule": "viewers/MinorFlow",
        "batch": "viewers/MinorFlow/scripts/create_all_MinorFlow_jsons.py",
    },
    "CVA6": {
        "ext": ".vcd",
        "mark": "",
        "tracer": "viewers/CVA6Flow/CVA6Flow_tracer.py",
        "submodule": "viewers/CVA6Flow",
        "batch": "viewers/CVA6Flow/scripts/create_all_CVA6Flow_jsons.py",
    },
}

# Never descended into. The submodules are covered by their own batch scripts,
# and the rest cannot hold a trace this script should convert.
PRUNE = {".git", "build", "vendor", "node_modules", "install", "work-ver",
         "work-dpi", "__pycache__", "viewers", "docs"}


def json_for(path, mark, ext):
    """daxpy_trace.config1.txt -> daxpy.config1.json,
    daxpy.vcd -> daxpy.json"""
    base = path[:-len(ext)] if path.endswith(ext) else path
    return (base.replace(mark, "") if mark else base) + ".json"


def is_trace(name, spec):
    """A trace of this engine: the right extension, and the mark in the name
    when the engine uses one."""
    return name.endswith(spec["ext"]) and (not spec["mark"]
                                           or spec["mark"] in name)


def find_traces(root):
    """[(engine, trace path)] for everything under root, submodules aside."""
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in PRUNE]
        for name in sorted(filenames):
            for engine, spec in ENGINES.items():
                if is_trace(name, spec):
                    found.append((engine, os.path.join(dirpath, name)))
                    break
    return found


def run_one(engine, trace, out_json, quiet, strict):
    tracer = os.path.join(REPO_ROOT, ENGINES[engine]["tracer"])
    cmd = [sys.executable, tracer, trace, "-o", out_json]
    if quiet:
        cmd.append("--quiet")
    if strict:
        cmd.append("--strict")
    start = time.time()
    # Output is not captured: the tracer's progress line is the only sign of
    # life on a trace that takes minutes.
    code = subprocess.run(cmd).returncode
    took = time.time() - start
    name = os.path.relpath(out_json, REPO_ROOT)
    if code == 3:
        # The tracer's strict exit. The JSON was still written, so this is
        # reported as degraded rather than as a failure.
        return (f"[DEGRADED] {name} written but the trace is degraded "
                f"(exit 3, see metadata.degraded)")
    if code != 0:
        return f"[ERROR]   {name} failed with exit code {code}"
    size = os.path.getsize(out_json) / (1024 * 1024)
    return f"[SUCCESS] {name} ({size:.1f} MB, {took:.0f}s)"


def missing_tracers():
    """Which engines cannot be converted here, because their submodule is not
    checked out. Named rather than skipped, since an empty run looks like
    success otherwise."""
    return [engine for engine, spec in ENGINES.items()
            if not os.path.isfile(os.path.join(REPO_ROOT, spec["tracer"]))]


def convert(traces, args):
    todo, skipped = [], []
    for engine, trace in traces:
        spec = ENGINES[engine]
        out_json = json_for(trace, spec["mark"], spec["ext"])
        if (not args.force and os.path.isfile(out_json)
                and os.path.getmtime(out_json) >= os.path.getmtime(trace)):
            skipped.append(os.path.relpath(out_json, REPO_ROOT))
        else:
            todo.append((engine, trace, out_json))

    if skipped:
        print(f"[INFO] {len(skipped)} JSON(s) already up to date, --force "
              f"redoes them")
    if not todo:
        print("[INFO] Nothing to convert in the fork itself")
        return 0, 0

    for engine, trace, out_json in todo:
        print(f"[INFO] {engine:5} {os.path.relpath(trace, REPO_ROOT)}")
    if args.dry_run:
        print(f"\n[INFO] Dry run, {len(todo)} trace(s) left alone")
        return 0, 0

    print(f"\n[INFO] Converting {len(todo)} trace(s), {args.jobs} at a time\n")
    failed = degraded = 0
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        futures = [pool.submit(run_one, e, t, j, args.quiet,
                               not args.no_strict)
                   for e, t, j in todo]
        for future in as_completed(futures):
            line = future.result()
            failed += line.startswith("[ERROR]")
            degraded += line.startswith("[DEGRADED]")
            print(line)
    print(f"\n[INFO] {len(todo) - failed - degraded} of {len(todo)} "
          f"converted cleanly")
    if degraded:
        print(f"[WARN] {degraded} trace(s) converted but degraded. The JSONs "
              f"are written and metadata.degraded names what is missing.")
    return failed, degraded


def run_submodules(args):
    """Each viewer has its own batch script, scoped to its own repository.
    Calling it rather than reaching in keeps that boundary intact."""
    failed = degraded = 0
    for engine, spec in ENGINES.items():
        batch = os.path.join(REPO_ROOT, spec["batch"])
        name = spec["submodule"]
        if not os.path.isfile(batch):
            print(f"[WARN] {name} has no batch script, is the submodule "
                  f"checked out?")
            continue
        if not args.yes:
            if not sys.stdin.isatty():
                print(f"[INFO] Skipping {name}: no terminal to ask. Use -y.")
                continue
            try:
                reply = input(f"\n  Run {os.path.relpath(batch, REPO_ROOT)} "
                              f"over {name}? [Y/n] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                return failed, degraded
            if reply in ("n", "no"):
                continue
        print(f"\n{'=' * 70}\n{name}\n{'=' * 70}")
        cmd = [sys.executable, batch, "-j", str(args.jobs)]
        if args.force:
            cmd.append("--force")
        if args.quiet:
            cmd.append("--quiet")
        if args.no_strict:
            cmd.append("--no-strict")
        code = subprocess.run(cmd).returncode
        # 3 is the batch's code for every trace converted, some degraded.
        if code == 3:
            degraded += 1
        elif code != 0:
            failed += 1
    return failed, degraded


def main():
    parser = argparse.ArgumentParser(
        description="Convert every trace in this checkout into a viewer JSON, "
                    "then offer to do the same inside each submodule.")
    parser.add_argument("folder", nargs="?", default=REPO_ROOT,
                        help="Where to look. Defaults to the whole "
                             "repository, submodules excluded")
    parser.add_argument("-j", "--jobs", type=int, default=DEFAULT_WORKERS,
                        metavar="N",
                        help=f"Traces to convert at a time. Defaults to "
                             f"{DEFAULT_WORKERS}. Each holds a whole trace's "
                             f"state, so memory binds before cores do")
    parser.add_argument("--force", action="store_true",
                        help="Convert a trace even when its JSON already "
                             "exists and is newer")
    parser.add_argument("--quiet", action="store_true",
                        help="Pass --quiet to the tracers, dropping their "
                             "progress lines")
    parser.add_argument("--dry-run", action="store_true",
                        help="List what would be converted, convert nothing")
    parser.add_argument("--no-submodules", action="store_true",
                        help="Stop after the fork's own traces")
    parser.add_argument("-y", "--yes", action="store_true",
                        help="Run the submodules without asking")
    parser.add_argument("--no-strict", action="store_true",
                        help="Do not pass --strict to the tracers or the "
                             "submodules' batch scripts. By default a "
                             "degraded trace ends the run with exit 3, its "
                             "JSON still written")
    args = parser.parse_args()

    if not os.path.isdir(args.folder):
        print(f"[ERROR] {args.folder} is not a folder")
        return 2

    absent = missing_tracers()
    if absent:
        print(f"[WARN] No tracer for {', '.join(absent)}: the submodule is "
              f"not checked out, so those traces are left alone.")

    traces = [(e, t) for e, t in find_traces(os.path.abspath(args.folder))
              if e not in absent]
    print(f"[INFO] {len(traces)} trace(s) in the fork itself, under "
          f"{os.path.relpath(os.path.abspath(args.folder), REPO_ROOT) or '.'}")
    failed, degraded = convert(traces, args)

    if not args.no_submodules and not args.dry_run:
        more_failed, more_degraded = run_submodules(args)
        failed += more_failed
        degraded += more_degraded
    # 1 when anything failed, 3 when everything converted but some traces are
    # degraded, the same codes the tracers and the batch scripts use.
    if failed:
        return 1
    return 3 if degraded else 0


if __name__ == "__main__":
    sys.exit(main())
