#!/usr/bin/env python3
"""Remove the heavy run artefacts from this project's own folders.

Deletes every .list, .vcd, .fst and debug-trace file, and every __pycache__
folder, under the folders this project owns.

Only PROJECT_DIRS below is ever looked at. That is the point of the script
rather than a detail: upstream CVA6 keeps hand-written .list manifests that
the build reads, in ci/ and under corev_apu/tb/, and a blanket sweep for
'*.list' would delete them.

The CARLA 2026 folder is kept whole.

  python3 clean_repo.py             # list, then ask
  python3 clean_repo.py -y          # delete without asking
  python3 clean_repo.py --dry-run   # list only
"""
import os
import sys
import shutil
import argparse

# The folders this project owns, relative to this script.
PROJECT_DIRS = [
    "gem5_config_CVA6",
    "verilator_changes",
    "viewers",
]

# Files removed, matched on the end of the name.
FILE_SUFFIXES = (".list", ".vcd", ".fst")

TRACE_MARK = "_trace."
TRACE_END = ".txt"

# Folders removed whole.
DIR_NAMES = {"__pycache__"}

# Kept, whatever is in them, relative to this script.
KEEP_DIRS = [os.path.join("viewers", "MinorFlow", "docs"),
             os.path.join("viewers", "CVA6Flow", "docs")]

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
    """Every artefact under the project's own folders, as a list of paths.

    A __pycache__ is taken whole and not descended into, since it is about to
    be deleted and nothing inside it can add a separate target."""
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
    args = parser.parse_args()

    searched = [d for d in PROJECT_DIRS
                if os.path.isdir(os.path.join(REPO_ROOT, d))]
    if not searched:
        print(f"[ERROR] None of {', '.join(PROJECT_DIRS)} found under "
              f"{REPO_ROOT}. Run this from the repository it lives in.")
        sys.exit(1)

    print(f"[INFO] Searching in: " +
          ", ".join(f"{d}/" for d in searched))
    print(f"[INFO] Keeping: " + ", ".join(f"{k}/" for k in KEEP_DIRS))

    targets = find_targets()
    if not targets:
        print("[INFO] Nothing to clean")
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
        return

    if not args.yes:
        try:
            reply = input("Delete these? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n[INFO] Cancelled")
            return
        if reply not in ("y", "yes"):
            print("[INFO] Cancelled")
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


if __name__ == "__main__":
    main()
