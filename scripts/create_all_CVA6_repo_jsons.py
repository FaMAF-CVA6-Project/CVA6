#!/usr/bin/env python3
"""Turn every gem5 trace and CVA6 VCD in this checkout into a JSON.

Two engines leave two kinds of input. gem5 writes a debug trace for MinorFlow,
CVA6 writes a VCD for CVA6Flow, and each viewer owns the tracer that turns its
input into the JSON it loads. This walks the fork, hands each input to the
right tracer, and then offers to run each submodule's own batch script over
that repository's tests/, where its generated inputs live. A VCD needs its
objdump listing beside it, as CVA6Flow's own batch requires, and one without
is skipped and named. -n stays beside --dry-run, as in the fork's other
scripts, though the viewers' own batches dropped it.

    python3 scripts/create_all_CVA6_repo_jsons.py              # whole checkout
    python3 scripts/create_all_CVA6_repo_jsons.py -j 8
    python3 scripts/create_all_CVA6_repo_jsons.py --force      # redo JSONs
    python3 scripts/create_all_CVA6_repo_jsons.py --dry-run    # list only
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


# SHARED BEGIN py-human-size

# Needs: none


def human(size):
    """A size in bytes as whole B, or as KiB, MiB or GiB with one decimal."""
    if size < 1024:
        return f"{size:.0f} B"
    for unit in ("KiB", "MiB", "GiB"):
        size /= 1024
        if size < 1024 or unit == "GiB":
            return f"{size:.1f} {unit}"

# SHARED END py-human-size


# One entry per engine: what its input looks like, which tracer reads it, and
# the submodule that owns that tracer. The JSON takes the input's name with
# the mark removed, the rename create_all_MinorFlow_jsons.py makes.
ENGINES = {
    "gem5": {
        # A sweep names its collected traces daxpy_trace.config1.txt, so the
        # mark is not a suffix, and its dot keeps x_traceback.txt out.
        "ext": ".txt",
        "mark": "_trace.",
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
# and the rest cannot hold an input this script should convert.
PRUNE = {".git", "build", "vendor", "node_modules", "install", "work-ver",
         "work-dpi", "__pycache__", "viewers", "docs"}


def json_for(path, mark, ext):
    """daxpy_trace.config1.txt -> daxpy.config1.json,
    daxpy.vcd -> daxpy.json

    Only the file name loses the mark, so a folder whose name happens to hold
    it keeps its own."""
    folder, name = os.path.split(path)
    if mark:
        at = name.rfind(mark)
        if at >= 0:
            name = name[:at] + "." + name[at + len(mark):]
    base = name[:-len(ext)] if name.endswith(ext) else name
    return os.path.join(folder, base + ".json")


def list_for(path, ext):
    """The objdump listing a VCD's instruction text comes from."""
    return (path[:-len(ext)] if path.endswith(ext) else path) + ".list"


def is_input(name, spec):
    """An input of this engine: the right extension, and the mark in the name
    when the engine uses one."""
    return name.endswith(spec["ext"]) and (not spec["mark"]
                                           or spec["mark"] in name)


def find_inputs(root):
    """[(engine, input path)] for everything under root, submodules aside."""
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in PRUNE]
        for name in sorted(filenames):
            for engine, spec in ENGINES.items():
                if is_input(name, spec):
                    found.append((engine, os.path.join(dirpath, name)))
                    break
    return found


def run_one(engine, source, out_json, quiet, strict):
    """Convert one input, returning its outcome, ok, degraded or failed, and
    the line that reports it."""
    spec = ENGINES[engine]
    tracer = os.path.join(REPO_ROOT, spec["tracer"])
    cmd = [sys.executable, tracer, source, "-o", out_json]
    if engine == "CVA6":
        cmd += ["--disasm-list", list_for(source, spec["ext"])]
    if quiet:
        cmd.append("--quiet")
    if strict:
        cmd.append("--strict")
    start = time.time()
    # Output is not captured, so the tracer's progress line shows an input
    # that takes minutes is not hung, and its warnings reach the log.
    code = subprocess.run(cmd).returncode
    took = time.time() - start
    name = os.path.relpath(out_json, REPO_ROOT)
    if code == 3:
        # The tracer's strict exit. The JSON was still written, so this is
        # reported as degraded rather than as a failure.
        return "degraded", (f"[WARN] {name} written, but the input is "
                            f"degraded (exit 3, see metadata.degraded).")
    if code != 0:
        return "failed", f"[ERROR] {name} failed with exit code {code}."
    return "ok", (f"[INFO] {name} written "
                  f"({human(os.path.getsize(out_json))}, {took:.0f}s)")


def missing_tracers():
    """Which engines cannot be converted here, because their submodule is not
    checked out. Named rather than skipped, since an empty run looks like
    success otherwise."""
    return [engine for engine, spec in ENGINES.items()
            if not os.path.isfile(os.path.join(REPO_ROOT, spec["tracer"]))]


def convert(inputs, args):
    """Convert every input whose JSON is missing or older than it. Returns
    (failed, degraded)."""
    todo, skipped, no_list = [], [], []
    for engine, source in inputs:
        spec = ENGINES[engine]
        out_json = json_for(source, spec["mark"], spec["ext"])
        if engine == "CVA6" and not os.path.isfile(list_for(source,
                                                            spec["ext"])):
            no_list.append(os.path.relpath(source, REPO_ROOT))
        elif (not args.force and os.path.isfile(out_json)
                and os.path.getmtime(out_json) >= os.path.getmtime(source)):
            skipped.append(os.path.relpath(out_json, REPO_ROOT))
        else:
            todo.append((engine, source, out_json))

    if no_list:
        print(f"[WARN] {len(no_list)} VCD(s) have no .list beside them, so "
              f"the viewer would refuse their JSONs. Skipped: "
              f"{', '.join(no_list)}")
    if skipped:
        print(f"[INFO] {len(skipped)} JSON(s) already up to date, --force "
              f"redoes them")
    if not todo:
        print("[INFO] Nothing to convert in the fork itself")
        return 0, 0

    for engine, source, out_json in todo:
        print(f"[INFO] {engine:5} {os.path.relpath(source, REPO_ROOT)}")
    if args.dry_run:
        print(f"\n[INFO] Dry run, {len(todo)} input(s) left alone")
        return 0, 0

    print(f"\n[INFO] Converting {len(todo)} input(s), {args.jobs} at a time\n")
    failed = degraded = 0
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        futures = [pool.submit(run_one, e, s, j, args.quiet,
                               not args.no_strict)
                   for e, s, j in todo]
        for future in as_completed(futures):
            outcome, line = future.result()
            failed += outcome == "failed"
            degraded += outcome == "degraded"
            print(line, file=sys.stderr if outcome == "failed"
                  else sys.stdout, flush=True)
    print(f"\n[INFO] {len(todo) - failed - degraded} of {len(todo)} "
          f"converted cleanly")
    if degraded:
        print(f"[WARN] {degraded} input(s) converted but degraded. The JSONs "
              f"are written and metadata.degraded names what is missing.")
    return failed, degraded


def run_submodules(args):
    """Each viewer has its own batch script, scoped to its own repository.
    Calling it rather than reaching in keeps that boundary intact, and it
    runs over the viewer's tests/, where its generated inputs live."""
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
        tests = os.path.join(REPO_ROOT, spec["submodule"], "tests")
        if os.path.isdir(tests):
            cmd.append(tests)
        if args.dry_run:
            cmd.append("--dry-run")
        if args.force:
            cmd.append("--force")
        if args.quiet:
            cmd.append("--quiet")
        if args.no_strict:
            cmd.append("--no-strict")
        code = subprocess.run(cmd).returncode
        # 3 is the batch's code for every input converted, some degraded.
        if code == 3:
            degraded += 1
        elif code != 0:
            failed += 1
    return failed, degraded


def main():
    parser = argparse.ArgumentParser(
        description="Convert every gem5 trace and CVA6 VCD in this checkout "
                    "into a JSON, then offer to do the same inside each "
                    "submodule.")
    parser.add_argument("folder", nargs="?", default=REPO_ROOT,
                        help="Where to look. Defaults to the whole "
                             "repository, submodules excluded")
    parser.add_argument("-j", "--jobs", type=int, default=DEFAULT_WORKERS,
                        metavar="N",
                        help=f"Inputs to convert at a time. Defaults to "
                             f"{DEFAULT_WORKERS}. Each holds a whole input's "
                             f"state, so memory binds before cores do")
    parser.add_argument("--force", action="store_true",
                        help="Convert an input even when its JSON already "
                             "exists and is newer")
    parser.add_argument("--quiet", action="store_true",
                        help="Pass --quiet to the tracers, dropping their "
                             "progress lines")
    parser.add_argument("-n", "--dry-run", action="store_true",
                        help="List what would be converted, convert nothing")
    parser.add_argument("--no-submodules", action="store_true",
                        help="Stop after the fork's own inputs")
    parser.add_argument("-y", "--yes", action="store_true",
                        help="Run the submodules without asking")
    parser.add_argument("--no-strict", action="store_true",
                        help="Do not pass --strict to the tracers or the "
                             "submodules' batch scripts. By default a "
                             "degraded input ends the run with exit 3, its "
                             "JSON still written")
    args = parser.parse_args()

    if not os.path.isdir(args.folder):
        print(f"[ERROR] Folder not found: {args.folder}", file=sys.stderr)
        return 2

    absent = missing_tracers()
    if absent:
        print(f"[WARN] No tracer for {', '.join(absent)}: the submodule is "
              f"not checked out, so those inputs are left alone.")

    inputs = [(e, s) for e, s in find_inputs(os.path.abspath(args.folder))
              if e not in absent]
    print(f"[INFO] {len(inputs)} input(s) in the fork itself, under "
          f"{os.path.relpath(os.path.abspath(args.folder), REPO_ROOT)}")
    failed, degraded = convert(inputs, args)

    if not args.no_submodules:
        more_failed, more_degraded = run_submodules(args)
        failed += more_failed
        degraded += more_degraded
    # 1 when anything failed, 3 when everything converted but some inputs are
    # degraded, the same codes the tracers and the batch scripts use.
    if failed:
        return 1
    return 3 if degraded else 0


if __name__ == "__main__":
    sys.exit(main())
