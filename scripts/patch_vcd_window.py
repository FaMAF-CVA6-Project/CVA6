#!/usr/bin/env python3
"""Apply or revert the windowed waveform dump kept in verilator_changes/.

Verilator writes about 63 KB of VCD per simulated cycle on this core, so a long
benchmark cannot be traced whole. The two modified copies under
verilator_changes/custom_size_vcds/ bound the dump to a window of simulation
time, and this puts them in place or takes them back out. Run it from the CVA6
root, which is /CVA6 inside the container.

    python3 scripts/patch_vcd_window.py status   # in place or not
    python3 scripts/patch_vcd_window.py apply    # window the dump
    python3 scripts/patch_vcd_window.py revert   # back to upstream

The window is a compile-time define, so applying it changes nothing until the
model is rebuilt:

    make verilate trace_start=100000 trace_end=200000

and the run after that needs run_CVA6.py --keep-build, or the driver deletes
the windowed model and rebuilds it without the defines.
"""
import argparse
import filecmp
import os
import shutil
import sys

# Each modified copy and the upstream file it stands in for, relative to the
# CVA6 root. The originals are left where they are, so nothing is lost.
SOURCE_DIR = os.path.join("verilator_changes", "custom_size_vcds")
PAIRS = (
    ("ariane_tb.cpp", os.path.join("corev_apu", "tb", "ariane_tb.cpp")),
    ("Makefile", "Makefile"),
)

# Where apply keeps the file it replaces. The container has no git to restore
# an upstream file from, so the copy is the only way back.
BACKUP_SUFFIX = ".upstream"


def default_root():
    """The checkout this script sits in, which is /CVA6 in the container."""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(here)


def usable(root):
    """Both halves have to be there: the modified copies and their targets."""
    if not os.path.isdir(os.path.join(root, SOURCE_DIR)):
        return f"no {SOURCE_DIR}/ in it"
    for name, dest in PAIRS:
        if not os.path.isfile(os.path.join(root, SOURCE_DIR, name)):
            return f"no {SOURCE_DIR}/{name}"
        if not os.path.isfile(os.path.join(root, dest)):
            return f"no {dest}"
    return None


def state(root, name, dest):
    """'windowed', 'upstream', or the reason neither can be said."""
    src = os.path.join(root, SOURCE_DIR, name)
    target = os.path.join(root, dest)
    if filecmp.cmp(src, target, shallow=False):
        return "windowed"
    return "upstream"


def do_status(root):
    print(f"[INFO] CVA6 root: {root}")
    for name, dest in PAIRS:
        where = state(root, name, dest)
        backup = os.path.join(root, dest + BACKUP_SUFFIX)
        kept = " (upstream copy kept)" if os.path.isfile(backup) else ""
        print(f"  {dest:34} {where}{kept}")
    windowed = [d for n, d in PAIRS if state(root, n, d) == "windowed"]
    if len(windowed) == len(PAIRS):
        print("[INFO] The dump is windowed. Rebuild with "
              "'make verilate trace_start=<t> trace_end=<t>'")
    elif windowed:
        print("[WARN] Half applied, which builds an unwindowed model from a "
              "Makefile that passes the defines. Run apply or revert.")
    else:
        print("[INFO] Upstream, so a dump runs from cycle zero to the end")
    return 0


def do_apply(root, dry_run):
    changed = 0
    for name, dest in PAIRS:
        src = os.path.join(root, SOURCE_DIR, name)
        target = os.path.join(root, dest)
        if state(root, name, dest) == "windowed":
            print(f"[INFO] Already in place: {dest}")
            continue
        backup = target + BACKUP_SUFFIX
        print(f"[INFO] {dest}: upstream copy to "
              f"{os.path.basename(backup)}, then the windowed one in")
        if dry_run:
            changed += 1
            continue
        if not os.path.isfile(backup):
            shutil.copy2(target, backup)
        shutil.copy2(src, target)
        changed += 1
    if dry_run:
        print(f"[INFO] Dry run, {changed} file(s) would change")
        return 0
    if changed:
        print("[INFO] Now rebuild the model with the window, in simulation "
              "time:\n           make verilate trace_start=100000 "
              "trace_end=200000")
        print("[INFO] Then run with run_CVA6.py --keep-build, or the driver "
              "rebuilds without the defines")
    return 0


def do_revert(root, dry_run):
    changed = 0
    for name, dest in PAIRS:
        target = os.path.join(root, dest)
        backup = target + BACKUP_SUFFIX
        if state(root, name, dest) == "upstream":
            print(f"[INFO] Already upstream: {dest}")
            continue
        if not os.path.isfile(backup):
            print(f"[ERROR] {dest} is the windowed copy and there is no "
                  f"{os.path.basename(backup)} to put back. On the host, "
                  f"'git checkout -- {dest}' restores it.")
            return 1
        print(f"[INFO] {dest}: upstream copy back in")
        if not dry_run:
            shutil.copy2(backup, target)
            os.remove(backup)
        changed += 1
    if dry_run:
        print(f"[INFO] Dry run, {changed} file(s) would change")
        return 0
    if changed:
        print("[INFO] Rebuild the model to lose the window: "
              "'make verilate'")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Apply or revert the windowed waveform dump.")
    parser.add_argument("action", choices=["status", "apply", "revert"],
                        help="status reports, apply windows the dump, revert "
                             "puts the upstream files back")
    parser.add_argument("--cva6-root", default=None, metavar="DIR",
                        help="The checkout to change. Defaults to the one "
                             "this script sits in, which is /CVA6 inside the "
                             "container")
    parser.add_argument("-n", "--dry-run", action="store_true",
                        help="Say what would change and stop")
    args = parser.parse_args()

    root = os.path.abspath(args.cva6_root or default_root())
    why = usable(root)
    if why:
        print(f"[ERROR] '{root}' is not a CVA6 checkout to patch: {why}. "
              f"Point --cva6-root at one.")
        return 2

    if args.action == "status":
        return do_status(root)
    if args.action == "apply":
        return do_apply(root, args.dry_run)
    return do_revert(root, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
