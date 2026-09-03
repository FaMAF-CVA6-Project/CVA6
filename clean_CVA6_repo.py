#!/usr/bin/env python3
"""Remove the heavy run artefacts from THIS repository's own folders: every
.list, .vcd, .fst and debug trace, and every __pycache__.

Only PROJECT_DIRS is looked at, since upstream CVA6 keeps hand-written .list
manifests the build reads.

The two viewers are separate repositories with their own artefacts and their
own rules, so this script does not reach into them. It offers to run their
scripts afterwards instead, and those decide what to keep on their own side.

  python3 clean_CVA6_repo.py               # list, then ask
  python3 clean_CVA6_repo.py -y            # delete without asking
  python3 clean_CVA6_repo.py --dry-run     # list only
  python3 clean_CVA6_repo.py --no-viewers  # skip the submodule offer

See also clean_gem5_runs.py and clean_CVA6_runs.py, which delete what a run
leaves behind rather than what is committed.
"""
import os
import sys
import shutil
import argparse
import subprocess

# The folders this repository owns, relative to this script.
PROJECT_DIRS = [
    "gem5_config_CVA6",
    "verilator_changes",
    "benchmarks",
]

# The submodules this script offers to clean after itself.
SUBMODULE_CLEANERS = [
    (os.path.join("viewers", "MinorFlow"), "clean_MinorFlow_repo.py"),
    (os.path.join("viewers", "CVA6Flow"), "clean_CVA6Flow_repo.py"),
]

# Files removed, matched on the end of the name.
FILE_SUFFIXES = (".list", ".vcd", ".fst")

TRACE_MARK = "_trace."
TRACE_END = ".txt"

# Folders removed whole.
DIR_NAMES = {"__pycache__"}

# Kept, whatever is in them, relative to this script.
KEEP_DIRS = []

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))


def kind_of(path):
    """The label a target is grouped under in the listing."""
    name = os.path.basename(path)
    if name in DIR_NAMES:
        return name
    for suffix in FILE_SUFFIXES:
        if name.endswith(suffix):
            return f"*{suffix}"
    return "*_trace*.txt" if is_trace(name) else "?"


def is_trace(name):
    """True for a debug trace, however the configuration is tagged into it."""
    return TRACE_MARK in name and name.endswith(TRACE_END)


def is_kept(path):
    """True for anything under a folder the script must not touch."""
    rel = os.path.relpath(path, REPO_ROOT)
    return any(rel == keep or rel.startswith(keep + os.sep)
               for keep in KEEP_DIRS)


def find_targets():
    """Every artefact under the project's own folders, as a list of paths. A
    __pycache__ is taken whole and not descended into, since it is about to be
    deleted and nothing inside it can add a separate target."""
    targets = []
    for name in PROJECT_DIRS:
        base = os.path.join(REPO_ROOT, name)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            keep = []
            for dirname in dirnames:
                full = os.path.join(dirpath, dirname)
                if dirname in DIR_NAMES and not is_kept(full):
                    targets.append(full)
                elif dirname != ".git":
                    keep.append(dirname)
            dirnames[:] = keep

            for filename in filenames:
                full = os.path.join(dirpath, filename)
                if ((filename.endswith(FILE_SUFFIXES) or is_trace(filename))
                        and not is_kept(full)):
                    targets.append(full)
    return sorted(targets)


def size_of(path):
    """Bytes held by a file or a folder. A race or a broken link counts zero."""
    if os.path.isfile(path) or os.path.islink(path):
        try:
            return os.lstat(path).st_size
        except OSError:
            return 0

    total = 0
    for dirpath, _, filenames in os.walk(path):
        for name in filenames:
            try:
                total += os.lstat(os.path.join(dirpath, name)).st_size
            except OSError:
                pass
    return total


def human(size):
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024 or unit == "GiB":
            return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024


def group(targets):
    """Collapse the targets into (folder, kind) rows, so a run that produced
    hundreds of files reads as a few lines rather than a wall of paths."""
    rows = {}
    for path in targets:
        key = (os.path.relpath(os.path.dirname(path), REPO_ROOT),
               kind_of(path))
        count, size = rows.get(key, (0, 0))
        rows[key] = (count + 1, size + size_of(path))
    return sorted(rows.items())


def clean_submodules(args):
    """Offer to run each viewer's own cleaner. They are separate repositories
    and decide what to keep, which is how the CARLA 2026 set stays put."""
    if args.no_viewers:
        return

    present = [(sub, script) for sub, script in SUBMODULE_CLEANERS
               if os.path.isfile(os.path.join(REPO_ROOT, sub, script))]
    missing = [(sub, script) for sub, script in SUBMODULE_CLEANERS
               if not os.path.isfile(os.path.join(REPO_ROOT, sub, script))]
    for sub, script in missing:
        print(f"[WARN] {sub}/{script} not found, so that submodule is not "
              f"cleaned. Run 'git submodule update --init' if it is empty.")
    if not present:
        return

    print()
    for sub, script in present:
        print(f"[INFO] {sub}/ is its own repository, cleaned by {script}")

    if not args.yes:
        try:
            reply = input("Clean the viewer submodules too? [y/N] ")
        except (EOFError, KeyboardInterrupt):
            print("\n[INFO] Submodules left alone")
            return
        if reply.strip().lower() not in ("y", "yes"):
            print("[INFO] Submodules left alone")
            return

    for sub, script in present:
        cmd = [sys.executable, script]
        if args.yes and not args.dry_run:
            cmd.append("-y")
        if args.dry_run:
            cmd.append("--dry-run")
        if args.verbose:
            cmd.append("-v")
        print("\n" + "=" * 70)
        print(f"{sub}/{script}")
        print("=" * 70)
        try:
            subprocess.run(cmd, cwd=os.path.join(REPO_ROOT, sub))
        except OSError as e:
            print(f"[WARN] Could not run {sub}/{script}: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Delete the .list, .vcd, .fst and trace files and "
                    "__pycache__ folders under this project's own folders.")
    parser.add_argument("-y", "--yes", action="store_true",
                        help="Delete without asking for confirmation")
    parser.add_argument("-n", "--dry-run", action="store_true",
                        help="List what would be deleted and stop")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="List every path instead of one row per folder")
    parser.add_argument("--no-viewers", action="store_true",
                        help="Do not offer to clean the viewer submodules")
    args = parser.parse_args()

    searched = [d for d in PROJECT_DIRS
                if os.path.isdir(os.path.join(REPO_ROOT, d))]
    if not searched:
        print(f"[ERROR] None of {', '.join(PROJECT_DIRS)} found under "
              f"{REPO_ROOT}. Run this from the repository it lives in.")
        sys.exit(1)

    print("[INFO] Searching in: " + ", ".join(f"{d}/" for d in searched))
    if KEEP_DIRS:
        print("[INFO] Keeping: " + ", ".join(f"{k}/" for k in KEEP_DIRS))

    targets = find_targets()
    if not targets:
        print("[INFO] Nothing to clean in this repository")
        clean_submodules(args)
        return

    print("\n" + "=" * 70)
    print("TO DELETE")
    print("=" * 70)

    total = 0
    if args.verbose:
        for path in targets:
            size = size_of(path)
            total += size
            print(f"{human(size):>10}  {os.path.relpath(path, REPO_ROOT)}")
    else:
        for (folder, kind), (count, size) in group(targets):
            total += size
            print(f"{human(size):>10}  {folder}/  "
                  f"{count} {kind}")
    print("=" * 70)
    print(f"{len(targets)} item(s), {human(total)}\n")

    if args.dry_run:
        print("[INFO] Dry run, nothing was deleted")
        clean_submodules(args)
        return

    if not args.yes:
        try:
            reply = input("Delete these? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n[INFO] Cancelled")
            return
        if reply not in ("y", "yes"):
            print("[INFO] Cancelled")
            clean_submodules(args)
            return

    deleted = 0
    for path in targets:
        try:
            if os.path.isdir(path) and not os.path.islink(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            deleted += 1
        except OSError as e:
            print(f"[WARN] Could not delete {path}: {e}")

    print(f"[INFO] Deleted {deleted} of {len(targets)} item(s), "
          f"{human(total)} freed")

    clean_submodules(args)


if __name__ == "__main__":
    main()
